# -*- coding: utf-8 -*-
#----------------------------------------------------------------------------
# Created By  : KMiNT21 edited wavcheb 2024, updated by Grok 2025
# Created Date: 2022.
# Updated Date: April 2025
# version ='2.0'
# ---------------------------------------------------------------------------
"""Telegram BOT for organizing events with participant registration.
Updated to python-telegram-bot v22.x with asyncio.
Supports payment confirmation with 💰 emoji.
"""

import sys
import os
import datetime
import re
import signal
import gettext
import parsedatetime
import urllib.request
from html.parser import HTMLParser
from . import db_mysql as db
import asyncio
from typing import Optional, Callable
from functools import wraps
from loguru import logger
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from recurrent.event_parser import RecurringEvent
from telegram.error import BadRequest

# Bot directory paths
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCALE_DIR = os.path.join(BOT_DIR, 'locale')

# ==================== URL Metadata Parser ====================

class _MetaExtractor(HTMLParser):
    """Minimal HTML parser that extracts og:title or <title>."""
    def __init__(self):
        super().__init__()
        self.og_title = None
        self.title = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == 'title':
            self._in_title = True
        elif tag == 'meta':
            prop = d.get('property', '') or d.get('name', '')
            content = d.get('content', '')
            if prop == 'og:title' and content:
                self.og_title = content

    def handle_data(self, data):
        if self._in_title and not self.title:
            self.title = data.strip()

    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False

def _parse_url_title_sync(url: str) -> str:
    """Fetch URL and return og:title or <title>. Runs synchronously."""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            content_type = resp.headers.get_content_type()
            if 'html' not in content_type:
                return ''
            raw = resp.read(65536)
            html = raw.decode('utf-8', errors='replace')
    except Exception:
        return ''
    parser = _MetaExtractor()
    try:
        parser.feed(html)
    except Exception:
        pass
    return (parser.og_title or parser.title or '').strip()

async def _fetch_url_title(url: str) -> str:
    """Async wrapper for URL title fetching (runs in thread pool)."""
    return await asyncio.to_thread(_parse_url_title_sync, url)

TRANSLATIONS = {
    'uk': gettext.translation('ua', localedir=LOCALE_DIR, languages=['uk']).gettext,
    'pt-br': gettext.translation('pt', localedir=LOCALE_DIR, languages=['pt_BR']).gettext,
    'ar': gettext.translation('ar', localedir=LOCALE_DIR, languages=['ar']).gettext,
    'ru': gettext.translation('ru', localedir=LOCALE_DIR, languages=['ru']).gettext
}

def _coerce_to_datetime(val: object) -> Optional[datetime.datetime]:
    """Accept datetime or str; return datetime or None."""
    if isinstance(val, datetime.datetime):
        return val
    if isinstance(val, str) and val.strip():
        s = val.strip()
        try:
            return datetime.datetime.fromisoformat(s)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return datetime.datetime.strptime(s, fmt)
                except ValueError:
                    pass
    return None

def make_translatable_user_id_context(func):
    """Декоратор для установки функции перевода в context.user_data"""
    @wraps(func)
    async def wrapped(update, context):
        try:
            lang = update.message.from_user.language_code if update.message else update.callback_query.from_user.language_code
            # Если language_code равен None, используем русский по умолчанию
            if not lang:
                lang = 'ru'
            logger.info(f'lang={lang}')
        except Exception:
            lang = 'ru'
            logger.info("Failed to detect language, defaulting to 'ru'")
        if lang in TRANSLATIONS:
            context.user_data['translate'] = TRANSLATIONS[lang]
        else:
            # Английский и другие неподдерживаемые языки используют оригинальный текст (без перевода)
            context.user_data['translate'] = lambda text: text
            # Не логируем для 'en' - это базовый язык интерфейса
            if lang != 'en':
                logger.info(f"No translation available for language: {lang}, using English (original text)")
        return await func(update, context)
    return wrapped
	
def _serialize_inline_kb(kb: InlineKeyboardMarkup) -> str:
    if not kb or not kb.inline_keyboard:
        return ""
    # Сериализуем только текст кнопок и callback_data (достаточно для эквивалентности)
    rows = []
    for row in kb.inline_keyboard:
        rows.append("|".join(f"{btn.text}::{btn.callback_data or ''}" for btn in row))
    return "\n".join(rows)

def new_chat_id_memoization(chat_id: int, lang: str, all_known_chat_ids=db.get_all_chat_ids()):
    if chat_id not in all_known_chat_ids:
        all_known_chat_ids.add(chat_id)
        db.register_new_chat_id(chat_id, lang)
        logger.info(f'New chat_id: {chat_id}')

@logger.catch
def build_message_markup(translate_func: Callable[[str], str]):
    """Создание кнопок с использованием переданной функции перевода"""
    button_list = [
        InlineKeyboardButton(translate_func('+ Apply for participation'), callback_data='ADD'),
        InlineKeyboardButton(translate_func('- Revoke application'), callback_data='REMOVE'),
        InlineKeyboardButton(translate_func('+ Apply friend or legioneer'), callback_data='ADD_LEGIONEER'),
        InlineKeyboardButton(translate_func('- Remove last friend or legioneer'), callback_data='REMOVE_LEGIONEER'),
        InlineKeyboardButton(translate_func('💰 Payment confirmed'), callback_data='PAY'),
    ]
    return InlineKeyboardMarkup(build_menu(button_list, n_cols=1))

@logger.catch
@make_translatable_user_id_context
async def button(update, context):
    """Обработка нажатий кнопок"""
    query = update.callback_query
    this_chat_id = query.message.chat_id
    user_id = query.from_user.id
    translate = context.user_data['translate']
    db.add_or_update_user(user_id, query.from_user.first_name, query.from_user.last_name, query.from_user.username)

    if query.data == "ADD":
        db.apply_for_participation_in_the_event(this_chat_id, user_id)
    elif query.data == "REMOVE":
        db.revoke_application_for_the_event(this_chat_id, user_id)
    elif query.data == "ADD_LEGIONEER":
        db.apply_for_legioneer(this_chat_id, user_id)
        await legioneer_added_message(update, context)
    elif query.data == "REMOVE_LEGIONEER":
        db.revoke_for_legioneer(this_chat_id)
        await legioneer_removed_message(update, context)
    elif query.data == "PAY":
        result = db.process_payment(this_chat_id, user_id)
        await query.answer(translate(result['message']))

    message_text = create_event_full_text(this_chat_id, translate)
    safe_text = (message_text or "").strip() or " "
    new_kb = build_message_markup(translate)
    new_kb_sig = _serialize_inline_kb(new_kb)

    # Текущее сохранённое состояние
    prev_text = (db.get_latest_bot_message_text(this_chat_id) or "").strip()
    # Получить текущую разметку у сообщения
    try:
        current_msg = query.message
        cur_kb = current_msg.reply_markup
    except Exception:
        cur_kb = None
    cur_kb_sig = _serialize_inline_kb(cur_kb)

    text_changed = safe_text != prev_text
    kb_changed = new_kb_sig != cur_kb_sig

    if text_changed or kb_changed:
        try:
            await query.edit_message_text(
                text=safe_text,
                reply_markup=new_kb,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            db.save_latest_bot_message(this_chat_id, query.message.message_id, safe_text)
        except Exception as e:
            # Игнорировать "message is not modified"
            if "message is not modified" in str(e).lower():
                pass
            else:
                logger.exception(e)
    await query.answer()

@logger.catch
def parse_datetime(str_datetime_in_free_form: str, translate: Callable[[str], str]) -> Optional[datetime.datetime]:
    consts = parsedatetime.Constants(localeID=translate('en_US'), usePyICU=False)
    consts.use24 = True
    r_event = RecurringEvent(parse_constants=consts)
    found_date = r_event.parse(str_datetime_in_free_form)
    if not found_date:
        return None
    delta = found_date - datetime.datetime.now()
    if delta.days < 0 or delta.days > 31:
        logger.info(f"Invalid time delta: {delta.days} days")
        return None
    return found_date

@logger.catch
def parse_cmd_arg(update, _context) -> str:
    user_input = update.message.text.strip()
    space_index = user_input.find(' ')
    if space_index < 0:
        return ''
    cmd_arg = user_input[space_index + 1:].strip()
    return cmd_arg.replace('@nashfootballbot', '').strip()

@logger.catch
async def remove_all_chat_events(update, context):
    this_chat_id = update.message.chat_id
    new_chat_id_memoization(this_chat_id, update.message.from_user.language_code)
    latest_bot_message_id = db.get_latest_bot_message_id(this_chat_id)
    if latest_bot_message_id:
        try:
            await context.bot.edit_message_reply_markup(chat_id=this_chat_id, message_id=latest_bot_message_id)
        except Exception as e:
            logger.warning(f"Failed to clear reply markup: {e}")
    db.close_all_open_events_for_chat(this_chat_id)

@logger.catch
@make_translatable_user_id_context
async def create_new_event(update, context):
    """Создание нового события с проверкой аргументов и активных событий"""
    this_chat_id = update.message.chat_id
    lang = update.message.from_user.language_code
    translate = context.user_data['translate']
    if lang:
        db.set_chat_lang(this_chat_id, lang)

    event_text = parse_cmd_arg(update, context)
    if not event_text:
        await update.message.reply_text(translate('Error: Please provide an event description. Usage: /event_add TEXT'))
        return

    if db.get_event_text(this_chat_id):
        await update.message.reply_text(translate('Error: An active event already exists. Close it with /event_remove first.'))
        return

    # If event_text is (or contains) a URL, fetch the page title
    url_match = re.search(r'https?://\S+', event_text)
    if url_match:
        url = url_match.group().rstrip('.,)')
        title = await _fetch_url_title(url)
        if title:
            if event_text.strip() == url:
                # User provided only a URL — use the fetched title as description
                event_text = f"{title}\n{url}"
            else:
                # User provided text + URL — append fetched title as annotation
                event_text = event_text.replace(url, f"{url} [{title}]")

    txt = event_text.lower()
    limit_markers = ['maximum', 'max', 'limit', 'максимум', 'максимальн', 'макс', 'лимит', 'ограничени', 'до']
    event_limit = 15
    for marker in limit_markers:
        if marker in txt:
            try:
                number = re.search(marker + r'[\s\S]*?(\d+)', txt).group(1)
                event_limit = int(number)
            except:
                continue
    event_datetime = parse_datetime(event_text, translate)
    message_text = translate("New event created") + ":\n\n🎉<b> " + event_text + " </b>🎉"
    if not message_text.strip():
        message_text = " "
    new_message = await context.bot.send_message(
        this_chat_id, message_text, reply_markup=build_message_markup(translate), parse_mode=ParseMode.HTML
    )
    db.event_add(this_chat_id, event_text, event_datetime, event_limit, new_message.message_id, message_text)

@logger.catch
async def update_event(update, context):
    new_chat_id_memoization(update.message.chat_id, update.message.from_user.language_code)
    new_event_text = parse_cmd_arg(update, context)
    db.update_event_text(update.message.chat_id, new_event_text)
    await show_info(update, context)

@logger.catch
async def set_event_datetime(update, context):
    new_chat_id_memoization(update.message.chat_id, update.message.from_user.language_code)
    str_datetime_in_free_form = parse_cmd_arg(update, context)
    translate = context.user_data['translate']
    event_datetime = parse_datetime(str_datetime_in_free_form, translate)
    if event_datetime:
        db.set_event_datetime(update.message.chat_id, event_datetime)
    await show_info(update, context)

@logger.catch
async def set_players_limit(update, context):
    new_chat_id_memoization(update.message.chat_id, update.message.from_user.language_code)
    try:
        new_limit = parse_cmd_arg(update, context)
        db.set_players_limit(update.message.chat_id, int(new_limit))
    except Exception as e:
        logger.exception(e)

@logger.catch
def create_event_full_text(this_chat_id: int, translate: Callable[[str], str]):
    def player_name_with_cards(games_registered, penalties, full_name, translator):
        printable_name = full_name
        games_played = games_registered - penalties
        if games_registered < 5 or not penalties:
            return printable_name
        ratio = games_played / games_registered
        if ratio < 0.9:
            return f'{printable_name}🟨 (Played {games_played} from {games_registered})'
        if ratio < 0.8:
            return f'{printable_name}🟨🟨 (Played {games_played} from {games_registered})'
        if ratio < 0.7:
            return f'{printable_name}🟨🟨🟨 (Played {games_played} from {games_registered})'
        return printable_name

    event_title = db.get_event_text(this_chat_id) or ""
    text = '🎉"<b>' + event_title + '</b>"🎉\n'
    players_limit = db.get_event_limit(this_chat_id) or 0
    if players_limit:
        text += translate('Players limit') + f': {players_limit}\n'
    raw_dt = db.get_event_datetime(this_chat_id)
    event_datetime = _coerce_to_datetime(raw_dt)
    if event_datetime:
        text += '📅 ' + translate('Event date and time') + f": {event_datetime.strftime('%Y-%m-%d, %H:%M')}\n"
        now = datetime.datetime.now()
        if event_datetime < now:
            text += '⏳ ' + translate('Event time out') + '.\n'
        else:
            delta = event_datetime - now
            hours = round(delta.seconds / 3600)
            text += '⏳ ' + translate('Time left') + f': {delta.days} ' + translate('days') + ' ' + translate('and') + f' {hours} ' + translate('hours') + '\n'

    text += translate('Players list') + ':\n'
    text_players = ''
    players = db.get_event_users(this_chat_id) or []
    for n, user_id in enumerate(players, start=1):
        if players_limit and n == players_limit + 1:
            text_players += '\t\t\n' + translate('Reserve') + ':\n'
        in_squad = '➕' if not players_limit or n <= players_limit else '      '
        printable_name = db.compose_full_name(user_id)
        games_registered, penalties = db.get_chat_user_rp(this_chat_id, user_id)
        paid = db.get_payment_status(this_chat_id, user_id)
        payment_emoji = '💰' if paid else ''
        text_players += in_squad + f'{n}. {player_name_with_cards(games_registered, penalties, printable_name, translate)} {payment_emoji}\n'

    text += '\n' + text_players
    canceled_players = db.get_event_revoked_users(this_chat_id) or []
    if canceled_players:
        text += '\n' + translate('Revoked applications') + ':'
        for canceled_user_id in canceled_players:
            cancel_datetime = db.get_user_cancellation_datetime(this_chat_id, canceled_user_id)
            cd = _coerce_to_datetime(cancel_datetime)
            cd_txt = cd.strftime('%Y-%m-%d %H:%M') if cd else str(cancel_datetime)[:16]
            printable_name = db.compose_full_name(canceled_user_id)
            text += f'      <s>{printable_name} - {cd_txt}</s>\n'
    elif not players:
        text += '\n' + translate('No applications yet')
    safe = text.strip()
    return safe if safe else " "

@logger.catch
@make_translatable_user_id_context
async def show_info(update, context):
    this_chat_id = update.message.chat_id
    translate = context.user_data['translate']
    new_chat_id_memoization(this_chat_id, update.message.from_user.language_code)
    if not db.get_event_text(this_chat_id):
        await update.message.reply_text(translate('No events'))
        return
    event_text = create_event_full_text(this_chat_id, translate).strip() or " "
    latest_bot_message_id = db.get_latest_bot_message_id(this_chat_id)
    if latest_bot_message_id:
        try:
            await context.bot.edit_message_reply_markup(chat_id=this_chat_id, message_id=latest_bot_message_id)
        except Exception as e:
            logger.warning(f"Failed to clear reply markup: {e}")
    new_message = await context.bot.send_message(
        this_chat_id, event_text, reply_markup=build_message_markup(translate), parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )
    db.save_latest_bot_message(this_chat_id, new_message.message_id, event_text)

@logger.catch
@make_translatable_user_id_context
async def add_player(update, context):
    translate = context.user_data['translate']
    new_chat_id_memoization(update.message.chat_id, update.message.from_user.language_code)
    user = update.message.from_user
    if db.get_event_text(update.message.chat_id):
        db.add_or_update_user(user.id, user.first_name, user.last_name, user.username)
        db.apply_for_participation_in_the_event(update.message.chat_id, user.id)
        logger.info(f"Event - Player applied: {user.id}")
    await show_info(update, context)

@logger.catch
@make_translatable_user_id_context
async def remove_player(update, context):
    translate = context.user_data['translate']
    new_chat_id_memoization(update.message.chat_id, update.message.from_user.language_code)
    user = update.message.from_user
    if db.get_event_text(update.message.chat_id):
        db.add_or_update_user(user.id, user.first_name, user.last_name, user.username)
        db.revoke_application_for_the_event(update.message.chat_id, user.id)
    await show_info(update, context)

@logger.catch
@make_translatable_user_id_context
async def add_legioneer(update, context):
    translate = context.user_data['translate']
    new_chat_id_memoization(update.message.chat_id, update.message.from_user.language_code)
    chat_id = update.message.chat_id
    if db.get_event_text(chat_id):
        await legioneer_added_message(update, context)
        db.apply_for_legioneer(chat_id, update.message.from_user.id)
        logger.info(f"Event - Legioneer applied in chat: {chat_id}")
    await show_info(update, context)

@logger.catch
@make_translatable_user_id_context
async def remove_legioneer(update, context):
    translate = context.user_data['translate']
    new_chat_id_memoization(update.message.chat_id, update.message.from_user.language_code)
    chat_id = update.message.chat_id
    if db.get_event_text(chat_id):
        await legioneer_removed_message(update, context)
        db.revoke_for_legioneer(chat_id)
        logger.info(f"Event - Legioneer removed in chat: {chat_id}")
    await show_info(update, context)

@logger.catch
@make_translatable_user_id_context
async def legioneer_added_message(update, context):
    translate = context.user_data['translate']
    user_id = update.message.from_user.id if update.message else update.callback_query.from_user.id
    chat_id = update.message.chat_id if update.message else update.callback_query.message.chat_id
    full_name = db.compose_full_name(user_id)
    if db.get_event_text(chat_id):
        legion_text = translate('Guest player applied by %(full_name)s') % {'full_name': full_name}
        await context.bot.send_message(chat_id, legion_text, parse_mode=ParseMode.HTML)

@logger.catch
@make_translatable_user_id_context
async def legioneer_removed_message(update, context):
    translate = context.user_data['translate']
    user_id = update.message.from_user.id if update.message else update.callback_query.from_user.id
    chat_id = update.message.chat_id if update.message else update.callback_query.message.chat_id
    full_name = db.compose_full_name(user_id)
    event_id = db.get_event_id_by_chat_id(chat_id)
    if event_id and db.get_legioneer_user(event_id) > 9 and db.get_event_text(chat_id):
        legion_text = translate('Guest player was revoked by %(full_name)s') % {'full_name': full_name}
        await context.bot.send_message(chat_id, legion_text, parse_mode=ParseMode.HTML)

@logger.catch
@make_translatable_user_id_context
async def confirm_payment(update, context):
    translate = context.user_data['translate']
    this_chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    new_chat_id_memoization(this_chat_id, update.message.from_user.language_code)
    if not db.get_event_text(this_chat_id):
        await update.message.reply_text(translate('No active event found.'))
        return
    result = db.process_payment(this_chat_id, user_id)
    await update.message.reply_text(translate(result['message']))
    if result['success']:
        await show_info(update, context)

@logger.catch
@make_translatable_user_id_context
async def penalty_player(update, context):
    translate = context.user_data['translate']
    new_chat_id_memoization(update.message.chat_id, update.message.from_user.language_code)
    user_id = parse_cmd_arg(update, context)
    if not user_id:
        await update.message.reply_text(translate('Error: Please provide a user ID. Usage: /penalty USERID'))
        return

    # Валидация: проверяем, что user_id - это число
    try:
        user_id_int = int(user_id)
    except ValueError:
        await update.message.reply_text(translate('Error: User ID must be a number, not a username. Usage: /penalty USERID'))
        logger.warning(f"Invalid user_id format: {user_id}. Expected integer.")
        return

    try:
        db.penalty_for_user_in_chat(update.message.chat_id, user_id_int, update.message.from_user.id)
        full_name = db.compose_full_name(user_id_int)
        penalty_text = translate('The player %(full_name)s was handed a yellow card for non-appearance') % {'full_name': full_name}
        await context.bot.send_message(update.message.chat_id, penalty_text, parse_mode=ParseMode.HTML)
        logger.info(f"Penalty applied to user {user_id_int} in chat {update.message.chat_id}")
    except Exception as e:
        logger.exception(e)
        await update.message.reply_text(translate('Error applying penalty.'))

@logger.catch
@make_translatable_user_id_context
async def fix_squad(update, context):
    translate = context.user_data['translate']
    new_chat_id_memoization(update.message.chat_id, update.message.from_user.language_code)
    this_chat_id = update.message.chat_id
    if not db.get_event_text(this_chat_id):
        await update.message.reply_text(translate('No events to fix stat for'))
        return
    text = translate('Current statistics for this chat room members:') + '\n<code>'
    squad = []
    players_limit = db.get_event_limit(this_chat_id)
    for position, userid in enumerate(db.get_event_users(this_chat_id), start=1):
        if not players_limit or position <= players_limit:
            try:
                squad.append(userid)
                full_name = db.compose_full_name(userid)
                games, penalties = db.get_chat_user_rp(this_chat_id, userid)
                games += 1
                text += f"{full_name} {games}/{penalties}\n"
            except Exception as e:
                logger.exception(e)
    text += "</code>"
    latest_bot_message_id = db.get_latest_bot_message_id(this_chat_id)
    if latest_bot_message_id:
        try:
            await context.bot.edit_message_reply_markup(chat_id=this_chat_id, message_id=latest_bot_message_id)
        except Exception as e:
            logger.warning(f"Failed to clear reply markup: {e}")
    await context.bot.send_message(this_chat_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    db.fix_event(this_chat_id)

@logger.catch
@make_translatable_user_id_context
async def show_stat(update, context):
    translate = context.user_data['translate']
    new_chat_id_memoization(update.message.chat_id, update.message.from_user.language_code)
    all_userids = db.get_only_chat_participants(update.message.chat_id)
    if not all_userids:
        return
    text = translate('Current statistics for this chat room members:') + '\n'
    text += translate('Registrations / Penalties') + '\n<code>'
    for userid in all_userids:
        if userid < 30:
            continue
        printable_name = db.compose_full_name(userid)
        registered, penalties = db.get_chat_user_rp(update.message.chat_id, userid)
        text += f"ID:{userid}, {registered:>2}/{penalties}, Full Name: {printable_name}\n"
    text += '</code>'
    await context.bot.send_message(update.message.chat_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

@logger.catch
@make_translatable_user_id_context
async def show_payments(update, context):
    """Show payment log for the active event (/payments command)."""
    this_chat_id = update.message.chat_id
    new_chat_id_memoization(this_chat_id, update.message.from_user.language_code)
    if not db.get_event_text(this_chat_id):
        await update.message.reply_text('No active event.')
        return
    entries = db.get_payment_log(this_chat_id)
    if not entries:
        await update.message.reply_text('💰 No payment records yet.')
        return
    lines = ['💰 <b>Отчёт об оплатах:</b>\n']
    for user_id, paid_at, for_friend in entries:
        name = db.compose_full_name(user_id)
        if isinstance(paid_at, datetime.datetime):
            time_str = paid_at.strftime('%H:%M')
        else:
            time_str = str(paid_at)[:5]
        note = ' (скорее всего за друга)' if for_friend else ' (скорее всего за себя)'
        lines.append(f'• <b>{name}</b> сообщил об оплате в {time_str}{note}')
    await update.message.reply_text('\n'.join(lines), parse_mode=ParseMode.HTML)

@logger.catch
@make_translatable_user_id_context
async def show_help(update, context):
    translate = context.user_data['translate']
    new_chat_id_memoization(update.message.chat_id, update.message.from_user.language_code)
    event_text = translate("""
Available BOT commands:

/event_add TEXT
Register new event

/event_remove
Remove open event

/event_update TEXT
Change event description

/limit XX
Set players limit

/event_datetime DATE TIME
Set event date and time in any format. It will parsed automatically.
Example 1: 2023-01-30, 18:00
Example2: tomorrow, 14:30

/info
Show event details

/add
Register yourself to the event

/remove
Revoke your application

/add_leg
Register another player (not participates in this chat) to the event

/rem_leg
Revoke register for another player

/pay
Confirm payment for the event

/payments
Show payment log for the current event

/fix
Fix event statistics (increment participants counters)

/penalty USERID
Increase someone's PENALTY counter for unreasonable skipping of the event without notification others.
You can find USERID by command /stat

/stat
This group members statistics (registrations and penalties)
""")
    await context.bot.send_message(update.message.chat_id, event_text, parse_mode=ParseMode.HTML)

@logger.catch
@make_translatable_user_id_context
async def unknown_command_handler(update, context):
    translate = context.user_data['translate']
    if not update.message:
        logger.warning("No message in update handler.")
        return
    this_chat_id = update.message.chat_id
    if update.message.new_chat_members:
        await show_info(update, context)
    text = (update.message.text or "").strip()
    if not text:
        return
    new_chat_id_memoization(this_chat_id, update.message.from_user.language_code)
    # Логируем только действительно неизвестные команды (начинающиеся с /)
    if text.startswith('/'):
        logger.info(f'Unknown command typed: {text}')

def build_menu(buttons, n_cols, header_buttons=None, footer_buttons=None):
    menu = [buttons[i:i + n_cols] for i in range(0, len(buttons), n_cols)]
    if header_buttons:
        menu.insert(0, [header_buttons])
    if footer_buttons:
        menu.append([footer_buttons])
    return menu

async def shutdown(application, loop):
    logger.info("Shutting down bot...")
    await application.updater.stop()
    await application.stop()
    await application.shutdown()
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

async def main():
    logger.remove()
    logger.add(os.path.join(BOT_DIR, "logs", "logs.log"), level="INFO")
    logger.add(sys.stderr, level="WARNING")

    try:
        with open(os.path.join(BOT_DIR, 'token.txt'), encoding='utf-8') as f:
            api_token = f.readline().strip()
    except Exception as err:
        logger.exception(err)
        print("Can not read api_token from token.txt")
        sys.exit(1)

    application = Application.builder().token(api_token).build()

    # Initialize database tables and run migrations
    db.init_database()

    # Добавление обработчиков команд
    application.add_handler(CommandHandler('add', add_player))
    application.add_handler(CommandHandler('remove', remove_player))
    application.add_handler(CommandHandler('add_leg', add_legioneer))
    application.add_handler(CommandHandler('rem_leg', remove_legioneer))
    application.add_handler(CommandHandler('info', show_info))
    application.add_handler(CommandHandler('help', show_help))
    application.add_handler(CommandHandler('stat', show_stat))
    application.add_handler(CommandHandler('fix', fix_squad))
    application.add_handler(CommandHandler('event_add', create_new_event))
    application.add_handler(CommandHandler('event_remove', remove_all_chat_events))
    application.add_handler(CommandHandler('event_update', update_event))
    application.add_handler(CommandHandler('limit', set_players_limit))
    application.add_handler(CommandHandler('penalty', penalty_player))
    application.add_handler(CommandHandler('event_datetime', set_event_datetime))
    application.add_handler(CommandHandler('pay', confirm_payment))
    application.add_handler(CommandHandler('payments', show_payments))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT | filters.StatusUpdate.NEW_CHAT_MEMBERS, unknown_command_handler))

    logger.info("Telegram Futsal Bot is starting...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    logger.info("Bot is running...")

    # Создаём событие для ожидания
    stop_event = asyncio.Event()

    # Настройка обработки сигналов
    loop = asyncio.get_running_loop()
    def signal_handler():
        logger.info("Received shutdown signal (Ctrl+C or SIGTERM)")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        logger.info("Main task was cancelled, initiating shutdown...")

    await shutdown(application, loop)

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close