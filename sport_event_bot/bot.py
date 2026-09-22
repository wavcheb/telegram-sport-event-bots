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
import socket
import gettext
import json
import hmac
import hashlib
import decimal
import parsedatetime
import urllib.request
import urllib.parse
import urllib.error
from html.parser import HTMLParser
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Support both package mode and standalone mode
try:
    from . import db_mysql as db
    from . import telegraph as tph
except ImportError:
    import db_mysql as db
    import telegraph as tph
import asyncio
from typing import Optional, Callable
from functools import wraps
from loguru import logger
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from recurrent.event_parser import RecurringEvent
from telegram.error import BadRequest, NetworkError, TimedOut

# Bot directory paths
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCALE_DIR = os.path.join(BOT_DIR, 'locale')

# Payments page URL from environment (replaces Telegraph if set)
PAYMENTS_PAGE_URL = os.getenv('PAYMENTS_PAGE_URL', '').strip()

# Fallback label for the kitty when a chat has not used one yet. Each chat
# keeps its own currency, recorded with the amount — see /event_bank.
BANK_CURRENCY = os.getenv('BANK_CURRENCY', '₽').strip()


def payments_page_link(event_id: int, chat_id: int) -> str:
    """Link to the payments page, signed with this chat's own key.

    The key is per chat, so a link handed to one group cannot be edited into
    another group's event: their signatures come from different keys.
    """
    if not PAYMENTS_PAGE_URL:
        return ''
    link = f'{PAYMENTS_PAGE_URL}?event={event_id}'
    secret = db.get_or_create_page_secret(chat_id)
    if secret:
        token = hmac.new(
            secret.encode('utf-8'), str(event_id).encode('utf-8'), hashlib.sha256
        ).hexdigest()[:16]
        link += f'&t={token}'
    return link


# MAX bot token for cross-platform sync
MAX_BOT_TOKEN = os.getenv('MAX_BOT_TOKEN', '').strip()

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


# MAX inline keyboard JSON for cross-platform sync
# Matches the buttons defined in max_sporteventbot build_event_keyboard()
MAX_EVENT_KEYBOARD_ATTACHMENT = {
    'type': 'inline_keyboard',
    'payload': {
        'buttons': [
            [{'type': 'callback', 'text': '+ Записаться', 'payload': 'ADD'}],
            [{'type': 'callback', 'text': '- Отписаться', 'payload': 'REMOVE'}],
            [{'type': 'callback', 'text': '+ Добавить друга/легионера', 'payload': 'ADD_LEGIONEER'}],
            [{'type': 'callback', 'text': '- Убрать последнего легионера', 'payload': 'REMOVE_LEGIONEER'}],
            [{'type': 'callback', 'text': 'Оплата подтверждена', 'payload': 'PAY'}],
        ]
    }
}


async def send_message_to_max(linked_chat_id: int, text: str) -> bool:
    """Post a new (plain announcement) message into a linked MAX chat."""
    if not MAX_BOT_TOKEN:
        logger.debug("MAX_BOT_TOKEN not set, skipping MAX message")
        return False

    def do_request():
        try:
            url = f"https://platform-api.max.ru/messages?chat_id={linked_chat_id}"
            data = json.dumps({'text': text, 'format': 'html'}, ensure_ascii=False).encode('utf-8')
            req = urllib.request.Request(url, data=data, method='POST')
            req.add_header('Content-Type', 'application/json; charset=utf-8')
            req.add_header('Authorization', MAX_BOT_TOKEN)
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode('utf-8', errors='replace')[:300]
            except Exception:
                body = ''
            logger.warning(f"MAX message HTTP error: {e.code} {e.reason} {body}")
        except Exception as e:
            logger.warning(f"MAX message failed: {e}")
        return None

    return bool(await asyncio.to_thread(do_request))


async def sync_to_max(linked_chat_id: int, linked_message_id: str, text: str):
    """Update message in linked MAX chat (HTML formatted, preserving buttons)."""
    if not MAX_BOT_TOKEN:
        logger.debug("MAX_BOT_TOKEN not set, skipping MAX sync")
        return False

    try:
        url = f"https://platform-api.max.ru/messages?message_id={linked_message_id}"
        data = json.dumps({
            'text': text,
            'format': 'html',
            'attachments': [MAX_EVENT_KEYBOARD_ATTACHMENT],
        }, ensure_ascii=False).encode('utf-8')
        req = urllib.request.Request(url, data=data, method='PUT')
        req.add_header('Content-Type', 'application/json; charset=utf-8')
        req.add_header('Authorization', MAX_BOT_TOKEN)

        def do_request():
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.read()
            except urllib.error.HTTPError as e:
                try:
                    body = e.read().decode('utf-8', errors='replace')[:300]
                except Exception:
                    body = ''
                logger.warning(f"MAX sync HTTP error: {e.code} {e.reason} {body}")
                return None
            except urllib.error.URLError as e:
                logger.warning(f"MAX sync URL error: {e.reason}")
                return None
            except Exception as e:
                logger.warning(f"MAX sync request failed: {e}")
                return None

        result = await asyncio.to_thread(do_request)
        if result:
            logger.info(f"Synced to MAX successfully")
            return True
    except Exception as e:
        logger.warning(f"Failed to sync to MAX: {e}")
    return False


def _normalize_tg_api_url(url: str) -> str:
    """Normalize TG_API_URL (CF Worker proxy base).

    Accepts the URL with or without trailing '/' or '/bot'. Requires an
    http(s) scheme: without it (or with a wrong base) the token would be
    glued to the host part and httpx fails with "Invalid port: '<token>'".
    """
    url = (url or '').strip().rstrip('/')
    if not url:
        return ''
    if url.endswith('/bot'):
        url = url[:-4].rstrip('/')
    if not url.startswith(('http://', 'https://')):
        logger.warning(f"TG_API_URL must start with http:// or https://, ignoring: {url}")
        return ''
    return url


def _html_escape(s) -> str:
    """HTML-escape for MAX (html format)."""
    if s is None:
        return ""
    return (
        str(s)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )


def create_max_message_text(chat_id: int, payment_url: str = None) -> str:
    """Create event text formatted for MAX (HTML)."""
    event_title = db.get_event_text(chat_id) or ""
    text = f'🎉 "<b>{_html_escape(event_title)}</b>" 🎉\n'

    players_limit = db.get_event_limit(chat_id) or 0
    if players_limit:
        text += f'👥 Лимит игроков: {players_limit}\n'

    raw_dt = db.get_event_datetime(chat_id)
    event_datetime = _coerce_to_datetime(raw_dt)
    if event_datetime:
        text += f"📅 Дата и время: {event_datetime.strftime('%Y-%m-%d, %H:%M')}\n"
        now = datetime.datetime.now()
        if event_datetime < now:
            text += '⏰ Время события истекло.\n'
        else:
            delta = event_datetime - now
            hours = round(delta.seconds / 3600)
            text += f'⏳ Осталось: {delta.days} дн. и {hours} ч.\n'

    # Links (HTML hyperlinks)
    links = []
    if payment_url:
        links.append(f'<a href="{_html_escape(payment_url)}">💳 Ссылка для оплаты</a>')
    if PAYMENTS_PAGE_URL:
        try:
            event_id = db.get_event_id_by_chat_id(chat_id)
            primary_event_id = db.get_primary_event_id(event_id)
            payments_link = payments_page_link(primary_event_id, chat_id)
            links.append(f'<a href="{_html_escape(payments_link)}">📊 Текущие платежи</a>')
        except:
            pass
    if links:
        text += '\n' + '\n'.join(links) + '\n'

    text += '\n<b>Список игроков:</b>\n'

    # Get all players
    players = db.get_event_users(chat_id) or []

    # Get players from linked event
    linked_players = []
    try:
        event_id = db.get_event_id_by_chat_id(chat_id)
        linked_players = db.get_linked_event_users(event_id)
    except:
        pass

    # Duty player, matched across every account of that person
    duty = db.get_event_duty(chat_id)
    duty_accounts = set(
        db.get_person_accounts(db.get_person_key(duty[0], duty[1]))
    ) if duty else set()

    # Show local players (Telegram)
    for n, user_id in enumerate(players, start=1):
        if players_limit and n == players_limit + 1:
            text += '\n<i>Резерв:</i>\n'
        in_squad = '+' if not players_limit or n <= players_limit else '  '
        printable_name = _html_escape(db.compose_full_name(user_id))
        if (user_id, db.PLATFORM) in duty_accounts:
            payment_mark = ' 🧹'
        else:
            payment_mark = ' 💰' if db.get_payment_status(chat_id, user_id) else ''
        platform_mark = ' [telegram]'
        text += f'{in_squad} {n}. {printable_name}{payment_mark}{platform_mark}\n'

    # Show linked players (MAX)
    if linked_players:
        start_n = len(players) + 1
        for i, (user_id, platform, name, paid) in enumerate(linked_players):
            n = start_n + i
            if players_limit and n == players_limit + 1:
                text += '\n<i>Резерв:</i>\n'
            in_squad = '+' if not players_limit or n <= players_limit else '  '
            safe_name = _html_escape(name)
            if (user_id, platform) in duty_accounts:
                payment_mark = ' 🧹'
            else:
                payment_mark = ' 💰' if paid else ''
            platform_mark = f' [{_html_escape(platform)}]' if platform != 'telegram' else ' [telegram]'
            text += f'{in_squad} {n}. {safe_name}{payment_mark}{platform_mark}\n'

    # Cancelled applications with strikethrough
    canceled_players = db.get_event_revoked_users(chat_id) or []
    if canceled_players:
        text += '\n<i>Отказавшиеся:</i>\n'
        for canceled_user_id in canceled_players:
            cancel_datetime = db.get_user_cancellation_datetime(chat_id, canceled_user_id)
            cd = _coerce_to_datetime(cancel_datetime)
            cd_txt = cd.strftime('%Y-%m-%d %H:%M') if cd else str(cancel_datetime)[:16]
            printable_name = _html_escape(db.compose_full_name(canceled_user_id))
            text += f'  <s>{printable_name} - {_html_escape(cd_txt)}</s>\n'

    return text


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
    rows = []
    for row in kb.inline_keyboard:
        rows.append("|".join(f"{btn.text}::{btn.callback_data or btn.url or ''}" for btn in row))
    return "\n".join(rows)

def new_chat_id_memoization(chat_id: int, lang: str, all_known_chat_ids=db.get_all_chat_ids()):
    if chat_id not in all_known_chat_ids:
        all_known_chat_ids.add(chat_id)
        db.register_new_chat_id(chat_id, lang)
        logger.info(f'New chat_id: {chat_id}')

@logger.catch
def build_message_markup(translate_func: Callable[[str], str]):
    """Создание кнопок с использованием переданной функции перевода"""
    rows = [
        [InlineKeyboardButton(translate_func('+ Apply for participation'), callback_data='ADD')],
        [InlineKeyboardButton(translate_func('- Revoke application'), callback_data='REMOVE')],
        [InlineKeyboardButton(translate_func('+ Apply friend or legioneer'), callback_data='ADD_LEGIONEER')],
        [InlineKeyboardButton(translate_func('- Remove last friend or legioneer'), callback_data='REMOVE_LEGIONEER')],
        [InlineKeyboardButton(translate_func('💰 Payment confirmed'), callback_data='PAY')],
    ]
    return InlineKeyboardMarkup(rows)

@logger.catch
@make_translatable_user_id_context
async def button(update, context):
    """Обработка нажатий кнопок"""
    query = update.callback_query
    this_chat_id = query.message.chat_id
    user_id = query.from_user.id
    translate = context.user_data['translate']
    db.add_or_update_user(user_id, query.from_user.first_name, query.from_user.last_name, query.from_user.username)

    # Buttons may still sit under an older announcement whose event has since
    # been fixed or removed. Acting on them would redraw that message without
    # the strikethrough and hand the buttons back, so just say it is over.
    if not db.get_event_text(this_chat_id):
        await query.answer(translate('This event is already finished.'))
        return

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
        if result['success']:
            # Update Telegraph payment log page
            try:
                entries = db.get_payment_log(this_chat_id)
                event_title = db.get_event_text(this_chat_id) or ''
                existing_url = db.get_event_telegraph_url(this_chat_id)
                new_tph_url = await tph.publish_payment_log(event_title, entries, existing_url)
                db.set_event_telegraph_url(this_chat_id, new_tph_url)
            except Exception as e:
                logger.warning(f"Telegraph update failed: {e}")

    payment_url = db.get_event_payment_url(this_chat_id)
    telegraph_url = db.get_event_telegraph_url(this_chat_id)
    message_text = create_event_full_text(this_chat_id, translate, payment_url, telegraph_url)
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

    # Cross-platform sync: update linked MAX chat
    try:
        # Debug: check link first
        linked_chat = db.get_linked_chat(this_chat_id)
        logger.info(f"TG->MAX sync: this_chat_id={this_chat_id}, linked_chat={linked_chat}")

        linked_info = db.get_linked_chat_message_info(this_chat_id)
        logger.info(f"TG->MAX sync: linked_info={linked_info}")

        if linked_info:
            linked_chat_id, linked_platform, linked_message_id = linked_info
            if linked_platform == 'max' and linked_message_id:
                # Use this_chat_id (TG) to get event data, not linked_chat_id (MAX)
                max_text = create_max_message_text(this_chat_id, payment_url)
                logger.info(f"Syncing TG->MAX: tg_chat={this_chat_id} -> max_chat={linked_chat_id}, msg_id={linked_message_id}")
                await sync_to_max(linked_chat_id, linked_message_id, max_text)
        elif linked_chat:
            logger.warning(f"TG->MAX sync: chat linked but no message_id. Did you run /info in MAX chat?")
    except Exception as e:
        logger.warning(f"Cross-platform sync failed: {e}")

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

# Currency signs and ISO codes the bots recognise after an amount. Nothing is
# ever converted — the sign is only a label, so each chat can use its own.
CURRENCY_SIGNS = ('₽', '$', '€', '₸', '₴', '₾', '₺', '£', '¥', '₩', '₫', '₪',
                  'zł', 'Kč', 'Ft', 'лв', 'сом', 'сум', 'руб', 'грн', 'тг')
CURRENCY_WORDS = {
    'рублей': '₽', 'рубля': '₽', 'рубль': '₽', 'руб.': '₽',
    'тенге': '₸', 'гривен': '₴', 'гривны': '₴', 'гривна': '₴',
    'долларов': '$', 'доллара': '$', 'евро': '€', 'манат': '₼',
    'сомов': 'сом', 'сумов': 'сум', 'драм': '֏', 'лари': '₾',
}


def _split_currency(rest: str):
    """Pull a currency label off the front of what follows the amount.

    "5200 ₸ после зала" -> ('₸', 'после зала'); "5200 после зала" -> ('', ...).
    Recognises signs, three-letter ISO codes and a few Russian words, so a
    chat in any country can label its own kitty.
    """
    rest = (rest or '').strip()
    if not rest:
        return '', ''
    head, _, tail = rest.partition(' ')
    bare = head.strip().strip('.,')
    if bare in CURRENCY_WORDS:
        return CURRENCY_WORDS[bare], tail.strip()
    if bare.lower() in CURRENCY_WORDS:
        return CURRENCY_WORDS[bare.lower()], tail.strip()
    if bare in CURRENCY_SIGNS:
        return bare, tail.strip()
    if len(bare) == 3 and bare.isalpha() and bare.isupper():
        return bare, tail.strip()          # KZT, RUB, USD, ...
    return '', rest


def _parse_money(raw: str):
    """Split "5200 ₸ после аренды" into (Decimal, currency, comment).

    Accepts 5200, 5 200, 5200.50 and 5200,50; returns (None, '', '') when
    there is no number to read.
    """
    text = (raw or '').strip()
    m = re.match(r'^([-+]?[\d\s]+(?:[.,]\d{1,2})?)\s*(.*)$', text, re.S)
    if not m:
        return None, '', ''
    number = m.group(1).replace(' ', '').replace('\u00a0', '').replace(',', '.')
    try:
        amount = decimal.Decimal(number)
    except decimal.InvalidOperation:
        return None, '', ''
    currency, comment = _split_currency(m.group(2))
    return amount, currency, comment


def _format_money(amount, currency: str = '') -> str:
    """5200 -> "5 200 ₸", using the chat's own currency label."""
    sign = currency or BANK_CURRENCY
    try:
        value = decimal.Decimal(amount)
    except Exception:
        return f'{amount} {sign}'.strip()
    quantised = value.quantize(decimal.Decimal('0.01'))
    if quantised == quantised.to_integral_value():
        body = f'{int(quantised):,}'.replace(',', '\u00a0')
    else:
        body = f'{quantised:,.2f}'.replace(',', '\u00a0')
    return f'{body}\u00a0{sign}'.strip()


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
    if latest_bot_message_id and db.get_event_text(this_chat_id):
        # Render closed-state text (strikethrough) before actually closing the event
        lang = update.message.from_user.language_code or 'ru'
        translate = TRANSLATIONS.get(lang, lambda t: t)
        try:
            payment_url = db.get_event_payment_url(this_chat_id)
            telegraph_url = db.get_event_telegraph_url(this_chat_id)
            closed_text = create_event_full_text(
                this_chat_id, translate, payment_url, telegraph_url, closed=True
            ).strip() or " "
            await context.bot.edit_message_text(
                chat_id=this_chat_id,
                message_id=latest_bot_message_id,
                text=closed_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            db.save_latest_bot_message(this_chat_id, latest_bot_message_id, closed_text)
        except Exception as e:
            logger.warning(f"Failed to mark event as closed: {e}")
            # Fallback: at least clear the inline keyboard
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=this_chat_id, message_id=latest_bot_message_id
                )
            except Exception as e2:
                logger.warning(f"Failed to clear reply markup: {e2}")
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

    # Extract payment URL from event text and store separately
    payment_url = None
    url_match = re.search(r'https?://\S+', event_text)
    if url_match:
        payment_url = url_match.group().rstrip('.,)')
        before = event_text[:url_match.start()].strip()
        after = event_text[url_match.end():].strip()
        event_text = ' '.join(filter(None, [before, after])).strip()

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
    message_text = translate("New event created") + ":\n\n🎉<b> " + _html_escape(event_text) + " </b>🎉"
    if payment_url:
        message_text += f'\n\n<a href="{_html_escape(payment_url)}">{translate("💳 Payment link")}</a>'
    if not message_text.strip():
        message_text = " "
    new_message = await context.bot.send_message(
        this_chat_id, message_text,
        reply_markup=build_message_markup(translate),
        parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )
    db.event_add(this_chat_id, event_text, event_datetime, event_limit, new_message.message_id, message_text)
    if payment_url:
        db.set_event_payment_url(this_chat_id, payment_url)

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
def create_event_full_text(this_chat_id: int, translate: Callable[[str], str],
                           payment_url: str = None, telegraph_url: str = None,
                           closed: bool = False):
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

    def _wrap_closed(s: str) -> str:
        return f'<s>{s}</s>' if closed else s

    event_title = _html_escape(db.get_event_text(this_chat_id) or "")
    if closed:
        text = f'🎉"<s><b>{event_title}</b></s>"🎉  🔒 <i>{translate("Event closed")}</i>\n'
    else:
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

    # Payment links above players list
    links = []
    if payment_url:
        links.append(f'<a href="{_html_escape(payment_url)}">{translate("💳 Payment link")}</a>')
    # Use PAYMENTS_PAGE_URL if configured, otherwise fall back to Telegraph
    if PAYMENTS_PAGE_URL:
        try:
            event_id = db.get_event_id_by_chat_id(this_chat_id)
            primary_event_id = db.get_primary_event_id(event_id)
            payments_link = payments_page_link(primary_event_id, this_chat_id)
            links.append(
                f'<a href="{_html_escape(payments_link)}">{translate("Current payments")}</a>'
            )
        except:
            pass
    elif telegraph_url:
        links.append(f'<a href="{_html_escape(telegraph_url)}">{translate("Current payments")}</a>')
    if links:
        text += ' | '.join(links) + '\n\n'

    text += translate('Players list') + ':\n'
    text_players = ''
    players = db.get_event_users(this_chat_id) or []

    # Get players from linked event if exists
    linked_players = []
    try:
        event_id = db.get_event_id_by_chat_id(this_chat_id)
        linked_players = db.get_linked_event_users(event_id)
    except:
        pass

    # Duty player (plays for free) — marked with a broom. Compare against
    # every account of that person, so the mark lands on them whichever
    # messenger they signed up from.
    duty = db.get_event_duty(this_chat_id)
    duty_accounts = set(
        db.get_person_accounts(db.get_person_key(duty[0], duty[1]))
    ) if duty else set()

    # Show local players
    for n, user_id in enumerate(players, start=1):
        if players_limit and n == players_limit + 1:
            text_players += '\t\t\n' + translate('Reserve') + ':\n'
        in_squad = '➕' if not players_limit or n <= players_limit else '      '
        printable_name = _html_escape(db.compose_full_name(user_id))
        games_registered, penalties = db.get_chat_user_rp(this_chat_id, user_id)
        paid = db.get_payment_status(this_chat_id, user_id)
        is_duty = (user_id, db.PLATFORM) in duty_accounts
        payment_emoji = '🧹' if is_duty else ('💰' if paid else '')
        name_with_cards = player_name_with_cards(games_registered, penalties, printable_name, translate)
        text_players += in_squad + f'{n}. {_wrap_closed(name_with_cards + " " + payment_emoji)}\n'

    # Show linked players from other platform
    if linked_players:
        start_n = len(players) + 1
        for i, (user_id, platform, name, paid) in enumerate(linked_players):
            n = start_n + i
            if players_limit and n == players_limit + 1:
                text_players += '\t\t\n' + translate('Reserve') + ':\n'
            in_squad = '➕' if not players_limit or n <= players_limit else '      '
            platform_mark = f' [{_html_escape(platform)}]'
            if (user_id, platform) in duty_accounts:
                status_emoji = ' 🧹'
            else:
                status_emoji = ' 💰' if paid else ''
            text_players += in_squad + f'{n}. {_wrap_closed(_html_escape(name) + platform_mark + status_emoji)}\n'

    text += '\n' + text_players
    total_players = len(players) + len(linked_players)
    canceled_players = db.get_event_revoked_users(this_chat_id) or []
    if canceled_players:
        text += '\n' + translate('Revoked applications') + ':'
        for canceled_user_id in canceled_players:
            cancel_datetime = db.get_user_cancellation_datetime(this_chat_id, canceled_user_id)
            cd = _coerce_to_datetime(cancel_datetime)
            cd_txt = cd.strftime('%Y-%m-%d %H:%M') if cd else str(cancel_datetime)[:16]
            printable_name = _html_escape(db.compose_full_name(canceled_user_id))
            text += f'      <s>{printable_name} - {cd_txt}</s>\n'
    elif total_players == 0:
        text += '\n' + translate('No applications yet')
    if duty:
        duty_name = _html_escape(db.get_duty_display_name(duty[0], duty[1]))
        text += f'\n🧹 {translate("On duty")}: <b>{duty_name}</b> — {translate("plays for free")}\n'
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
    payment_url = db.get_event_payment_url(this_chat_id)
    telegraph_url = db.get_event_telegraph_url(this_chat_id)
    event_text = create_event_full_text(this_chat_id, translate, payment_url, telegraph_url).strip() or " "
    latest_bot_message_id = db.get_latest_bot_message_id(this_chat_id)
    if latest_bot_message_id:
        try:
            await context.bot.edit_message_reply_markup(chat_id=this_chat_id, message_id=latest_bot_message_id)
        except Exception as e:
            logger.warning(f"Failed to clear reply markup: {e}")
    new_message = await context.bot.send_message(
        this_chat_id, event_text,
        reply_markup=build_message_markup(translate),
        parse_mode=ParseMode.HTML, disable_web_page_preview=True
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
    full_name = _html_escape(db.compose_full_name(user_id))
    if db.get_event_text(chat_id):
        legion_text = translate('Guest player applied by %(full_name)s') % {'full_name': full_name}
        await context.bot.send_message(chat_id, legion_text, parse_mode=ParseMode.HTML)

@logger.catch
@make_translatable_user_id_context
async def legioneer_removed_message(update, context):
    translate = context.user_data['translate']
    user_id = update.message.from_user.id if update.message else update.callback_query.from_user.id
    chat_id = update.message.chat_id if update.message else update.callback_query.message.chat_id
    full_name = _html_escape(db.compose_full_name(user_id))
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
        full_name = _html_escape(db.compose_full_name(user_id_int))
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
                full_name = _html_escape(db.compose_full_name(userid))
                games, penalties = db.get_chat_user_rp(this_chat_id, userid)
                games += 1
                text += f"{full_name} {games}/{penalties}\n"
            except Exception as e:
                logger.exception(e)
    text += "</code>"
    latest_bot_message_id = db.get_latest_bot_message_id(this_chat_id)
    if latest_bot_message_id:
        # Mark existing event message as closed (strikethrough) before closing in DB
        try:
            payment_url = db.get_event_payment_url(this_chat_id)
            telegraph_url = db.get_event_telegraph_url(this_chat_id)
            closed_text = create_event_full_text(
                this_chat_id, translate, payment_url, telegraph_url, closed=True
            ).strip() or " "
            await context.bot.edit_message_text(
                chat_id=this_chat_id,
                message_id=latest_bot_message_id,
                text=closed_text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            db.save_latest_bot_message(this_chat_id, latest_bot_message_id, closed_text)
        except Exception as e:
            logger.warning(f"Failed to mark event as closed on /fix: {e}")
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=this_chat_id, message_id=latest_bot_message_id
                )
            except Exception as e2:
                logger.warning(f"Failed to clear reply markup: {e2}")
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
        printable_name = _html_escape(db.compose_full_name(userid))
        registered, penalties = db.get_chat_user_rp(update.message.chat_id, userid)
        text += f"ID:{userid}, {registered:>2}/{penalties}, Full Name: {printable_name}\n"
    text += '</code>'
    await context.bot.send_message(update.message.chat_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

@logger.catch
@make_translatable_user_id_context
async def show_payments(update, context):
    """Publish payment log to Telegraph and send the link (/payments command)."""
    this_chat_id = update.message.chat_id
    translate = context.user_data['translate']
    new_chat_id_memoization(this_chat_id, update.message.from_user.language_code)
    event_title = db.get_event_text(this_chat_id)
    if not event_title:
        await update.message.reply_text(translate('No active event found.'))
        return
    entries = db.get_payment_log(this_chat_id)
    try:
        existing_url = db.get_event_telegraph_url(this_chat_id)
        page_url = await tph.publish_payment_log(event_title, entries, existing_url)
        db.set_event_telegraph_url(this_chat_id, page_url)
        count = len(entries)
        await update.message.reply_text(
            f'💰 <b>{translate("Payment log")}</b> ({count} {translate("records")}):\n{page_url}',
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False
        )
    except Exception as e:
        logger.error(f"Telegraph publish failed: {e}")
        # Fallback: show inline
        if not entries:
            await update.message.reply_text(translate('No payment records yet.'))
            return
        lines = [f'💰 <b>{translate("Payment log")}:</b>\n']
        for user_id, paid_at, for_friend in entries:
            name = _html_escape(db.compose_full_name(user_id))
            time_str = paid_at.strftime('%H:%M') if isinstance(paid_at, datetime.datetime) else str(paid_at)[:5]
            note = f' ({translate("probably for friend")})' if for_friend else f' ({translate("probably for self")})'
            lines.append(f'• <b>{name}</b> {translate("marked payment at")} {time_str}{note}')
        await update.message.reply_text('\n'.join(lines), parse_mode=ParseMode.HTML)


@logger.catch
@make_translatable_user_id_context
async def link_chat(update, context):
    """Link this chat with another platform chat (/link command)."""
    translate = context.user_data['translate']
    this_chat_id = update.message.chat_id
    new_chat_id_memoization(this_chat_id, update.message.from_user.language_code)

    # Check if already linked
    linked = db.get_linked_chat(this_chat_id)
    if linked:
        linked_chat_id, linked_platform = linked
        await update.message.reply_text(
            f'{translate("This chat is already linked to")} {linked_platform} (chat {linked_chat_id}).\n'
            f'{translate("Use /unlink to remove the link first.")}',
            parse_mode=ParseMode.HTML
        )
        return

    # Check for secret argument
    args = context.args
    if args:
        secret = args[0].strip().upper()
        result = db.complete_chat_link(this_chat_id, secret)
        if result:
            linked_chat_id, linked_platform = result
            await update.message.reply_text(
                f'✅ {translate("Chat linked successfully!")}\n'
                f'{translate("Linked to")} {linked_platform} (chat {linked_chat_id})',
                parse_mode=ParseMode.HTML
            )
        else:
            await update.message.reply_text(
                f'❌ {translate("Invalid or expired link code.")}',
                parse_mode=ParseMode.HTML
            )
        return

    # Generate new secret
    secret = db.create_chat_link(this_chat_id)
    await update.message.reply_text(
        f'🔗 {translate("Link code generated:")}\n\n'
        f'<code>{secret}</code>\n\n'
        f'{translate("Send this code in the other messenger chat using /link command.")}',
        parse_mode=ParseMode.HTML
    )


@logger.catch
@make_translatable_user_id_context
async def unlink_chat(update, context):
    """Remove link with another platform chat (/unlink command)."""
    translate = context.user_data['translate']
    this_chat_id = update.message.chat_id
    new_chat_id_memoization(this_chat_id, update.message.from_user.language_code)

    if db.unlink_chat(this_chat_id):
        await update.message.reply_text(f'✅ {translate("Chat unlinked successfully.")}')
    else:
        await update.message.reply_text(f'{translate("This chat is not linked to any other chat.")}')


@logger.catch
@make_translatable_user_id_context
async def copy_event_from_linked(update, context):
    """Copy the open event from the linked chat into this one (/event_copy)."""
    translate = context.user_data['translate']
    this_chat_id = update.message.chat_id
    new_chat_id_memoization(this_chat_id, update.message.from_user.language_code)

    linked = db.get_linked_chat(this_chat_id)
    if not linked:
        await update.message.reply_text(
            f'{translate("This chat is not linked to any other chat.")} /link'
        )
        return
    linked_chat_id, linked_platform = linked

    if db.get_event_text(this_chat_id):
        await update.message.reply_text(
            translate('Error: An active event already exists. Close it with /event_remove first.')
        )
        return

    linked_event = db.get_event_from_linked_chat(linked_chat_id, linked_platform)
    if not linked_event:
        await update.message.reply_text(
            f'{translate("No active event in the linked chat")} ({linked_platform}).'
        )
        return

    linked_event_id, description, event_datetime_str, players_limit, payment_url = linked_event
    event_dt = _coerce_to_datetime(event_datetime_str) or datetime.datetime.now()

    db.event_add(this_chat_id, description, event_dt, players_limit or 0, 0, '')
    if payment_url:
        db.set_event_payment_url(this_chat_id, payment_url)

    local_event_id = db.get_event_id_by_chat_id(this_chat_id)
    db.create_event_link(linked_event_id, local_event_id)

    event_text = create_event_full_text(
        this_chat_id, translate, payment_url, None
    ).strip() or " "
    new_message = await context.bot.send_message(
        this_chat_id, event_text,
        reply_markup=build_message_markup(translate),
        parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )
    db.save_latest_bot_message(this_chat_id, new_message.message_id, event_text)
    logger.info(f"Event copied from {linked_platform} chat {linked_chat_id} to {this_chat_id}")


# ==================== Cross-platform identity ====================

@logger.catch
@make_translatable_user_id_context
async def show_or_set_bank(update, context):
    """Show or set how much the community has in the kitty (/event_bank)."""
    translate = context.user_data['translate']
    this_chat_id = update.message.chat_id
    user = update.message.from_user
    new_chat_id_memoization(this_chat_id, user.language_code)

    raw = parse_cmd_arg(update, context)
    if not raw:
        current = db.get_bank_amount(this_chat_id)
        if not current:
            await update.message.reply_text(
                translate('The kitty is empty so far.') + '\n/event_bank 5200'
            )
            return
        amount, updated_at, updated_by, comment, currency = current
        who = db.get_duty_display_name(updated_by, db.PLATFORM) if updated_by else ''
        when = _coerce_to_datetime(updated_at)
        when_txt = when.strftime('%d.%m.%Y %H:%M') if when else str(updated_at)[:16]
        text = f'💰 {translate("In the kitty")}: <b>{_format_money(amount, currency)}</b>'
        if comment:
            text += f'\n{_html_escape(comment)}'
        text += f'\n<i>{translate("updated")} {when_txt}'
        if who:
            text += f', {_html_escape(who)}'
        text += '</i>'
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        return

    amount, currency, comment = _parse_money(raw)
    if amount is None:
        await update.message.reply_text(
            translate('Could not read that amount. For example: /event_bank 5200')
        )
        return
    # Keep the label this chat already uses unless a new one was given
    currency = currency or db.get_bank_currency(this_chat_id)

    db.add_or_update_user(user.id, user.first_name, user.last_name, user.username)
    if db.set_bank_amount(this_chat_id, amount, user.id, comment, currency):
        text = f'💰 {translate("In the kitty")}: <b>{_format_money(amount, currency)}</b>'
        if comment:
            text += f'\n{_html_escape(comment)}'
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(translate('Could not store the amount, see the log.'))


@logger.catch
@make_translatable_user_id_context
async def link_identity(update, context):
    """Link your MAX and Telegram accounts into one person (/iam).

    Without a code: report the current state and issue a code to enter in the
    other messenger. With a code: complete the link."""
    translate = context.user_data['translate']
    this_chat_id = update.message.chat_id
    user = update.message.from_user
    new_chat_id_memoization(this_chat_id, user.language_code)
    db.add_or_update_user(user.id, user.first_name, user.last_name, user.username)

    code = parse_cmd_arg(update, context)
    if code:
        other = db.complete_identity_link(user.id, code)
        if not other:
            await update.message.reply_text(
                translate('This code is unknown or already used.')
            )
            return
        other_name = _html_escape(db.get_duty_display_name(other[0], other[1]))
        await update.message.reply_text(
            f'✅ {translate("Accounts linked")}: <b>{other_name}</b> [{_html_escape(other[1])}]\n'
            + translate('Duty history now counts as one person.'),
            parse_mode=ParseMode.HTML
        )
        return

    linked = db.get_linked_identity(user.id)
    if linked:
        names = ', '.join(
            f'<b>{_html_escape(db.get_duty_display_name(uid, plat))}</b> [{_html_escape(plat)}]'
            for uid, plat in linked
        )
        await update.message.reply_text(
            f'🔗 {translate("Your account is linked with")}: {names}\n'
            + translate('Use /iam_forget to unlink.'),
            parse_mode=ParseMode.HTML
        )
        return

    secret = db.create_identity_code(user.id)
    await update.message.reply_text(
        f'🔗 {translate("Your linking code")}:\n\n<code>{secret}</code>\n\n'
        + translate('Send "/iam CODE" in the other messenger from your own account.')
        + '\n' + translate('Anyone who enters this code will be linked to you, so do not share it.'),
        parse_mode=ParseMode.HTML
    )


@logger.catch
@make_translatable_user_id_context
async def unlink_identity_cmd(update, context):
    """Detach this account from its linked one (/iam_forget)."""
    translate = context.user_data['translate']
    user = update.message.from_user
    new_chat_id_memoization(update.message.chat_id, user.language_code)
    if db.unlink_identity(user.id):
        await update.message.reply_text(f'✅ {translate("Accounts unlinked.")}')
    else:
        await update.message.reply_text(translate('Your account is not linked to another one.'))


# ==================== Duty roster ====================

def _duty_mention(user_id: int, platform: str, name: str) -> str:
    """Mention the duty player. A real Telegram mention only works for
    Telegram users; a MAX user is named in plain text."""
    safe_name = _html_escape(name)
    if platform == db.PLATFORM:
        return f'<a href="tg://user?id={user_id}">{safe_name}</a>'
    return f'<b>{safe_name}</b> [{_html_escape(platform)}]'


async def _refresh_event_message(context, this_chat_id, translate) -> bool:
    """Redraw the existing announcement in place, keeping its buttons.

    Unlike show_info() this posts nothing new — the chat must not end up with
    two button-bearing announcements after a duty is assigned."""
    message_id = db.get_latest_bot_message_id(this_chat_id)
    if not message_id:
        return False
    payment_url = db.get_event_payment_url(this_chat_id)
    telegraph_url = db.get_event_telegraph_url(this_chat_id)
    text = create_event_full_text(
        this_chat_id, translate, payment_url, telegraph_url
    ).strip() or " "
    try:
        await context.bot.edit_message_text(
            chat_id=this_chat_id, message_id=message_id, text=text,
            reply_markup=build_message_markup(translate),
            parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )
        db.save_latest_bot_message(this_chat_id, message_id, text)
        return True
    except Exception as e:
        if "message is not modified" in str(e).lower():
            return True
        logger.warning(f"Could not refresh event message: {e}")
        return False


async def _announce_duty(update, context, translate, user_id, platform, name, volunteered):
    """Refresh the announcement in place, then announce the duty in both chats."""
    this_chat_id = update.message.chat_id

    # Redraw the existing announcement so the broom shows up there. If there is
    # no live announcement to edit, fall back to posting a fresh one.
    had_announcement = bool(db.get_latest_bot_message_id(this_chat_id))
    refreshed = await _refresh_event_message(context, this_chat_id, translate)

    mention = _duty_mention(user_id, platform, name)
    if volunteered:
        text = f'🧹 {mention} ' + translate('volunteered for duty. Thanks!')
    else:
        text = '🧹 ' + translate('On duty for this event') + f': {mention}'
    await context.bot.send_message(this_chat_id, text, parse_mode=ParseMode.HTML)

    if not refreshed and not had_announcement:
        await show_info(update, context)

    # Mirror into the linked MAX chat: update its event message and announce
    # get_linked_chat_message_info() returns None once the linked chat's event
    # is closed, so a fixed announcement is neither overwritten nor followed by
    # a duty note about an event that chat has already finished.
    try:
        linked_info = db.get_linked_chat_message_info(this_chat_id)
        if linked_info:
            linked_chat_id, linked_platform, linked_message_id = linked_info
            if linked_platform == 'max' and linked_message_id:
                payment_url = db.get_event_payment_url(this_chat_id)
                await sync_to_max(
                    linked_chat_id, linked_message_id,
                    create_max_message_text(this_chat_id, payment_url)
                )
                plain = (f'🧹 Дежурный: <b>{_html_escape(name)}</b>'
                         + ('' if platform == 'max' else ' [telegram]'))
                await send_message_to_max(linked_chat_id, plain)
    except Exception as e:
        logger.warning(f"Failed to announce duty in linked chat: {e}")


@logger.catch
@make_translatable_user_id_context
async def assign_duty(update, context):
    """Pick the duty player for the open event (/event_duty)."""
    translate = context.user_data['translate']
    this_chat_id = update.message.chat_id
    new_chat_id_memoization(this_chat_id, update.message.from_user.language_code)

    if not db.get_event_text(this_chat_id):
        await update.message.reply_text(translate('No active event found.'))
        return

    # Keep an existing duty unless that player has left the event since
    existing = db.get_event_duty(this_chat_id)
    if existing:
        still_playing = any(
            db.is_same_person(uid, plat, existing[0], existing[1])
            for uid, plat, _ in db.get_duty_candidates(this_chat_id)
        )
        if still_playing:
            name = _html_escape(db.get_duty_display_name(existing[0], existing[1]))
            await update.message.reply_text(
                f'🧹 {translate("Duty is already assigned")}: <b>{name}</b>\n'
                + translate('Someone else can take over with /mepls'),
                parse_mode=ParseMode.HTML
            )
            return
        logger.info(f"Duty {existing[0]}@{existing[1]} left event in chat {this_chat_id}, re-picking")

    choice = db.choose_duty(this_chat_id)
    if not choice:
        await update.message.reply_text(
            translate('No eligible participants for duty yet (guests do not count).')
        )
        return

    user_id, platform, name = choice
    db.set_event_duty(this_chat_id, user_id, platform, 'auto')
    logger.info(f"Duty assigned: {user_id}@{platform} in chat {this_chat_id}")
    await _announce_duty(update, context, translate, user_id, platform, name, volunteered=False)


@logger.catch
@make_translatable_user_id_context
async def volunteer_duty(update, context):
    """Volunteer yourself for duty (/mepls)."""
    translate = context.user_data['translate']
    this_chat_id = update.message.chat_id
    user = update.message.from_user
    new_chat_id_memoization(this_chat_id, user.language_code)

    if not db.get_event_text(this_chat_id):
        await update.message.reply_text(translate('No active event found.'))
        return

    db.add_or_update_user(user.id, user.first_name, user.last_name, user.username)
    if user.id not in (db.get_event_users(this_chat_id) or []):
        await update.message.reply_text(
            translate('Register for the event first, then volunteer for duty.')
        )
        return

    existing = db.get_event_duty(this_chat_id)
    if existing and db.is_same_person(existing[0], existing[1], user.id, db.PLATFORM):
        await update.message.reply_text(translate('You are already on duty for this event.'))
        return

    db.set_event_duty(this_chat_id, user.id, db.PLATFORM, 'volunteer')
    name = db.compose_full_name(user.id)
    logger.info(f"Duty volunteered: {user.id} in chat {this_chat_id}")
    await _announce_duty(update, context, translate, user.id, db.PLATFORM, name, volunteered=True)


@logger.catch
@make_translatable_user_id_context
async def show_duty_stats(update, context):
    """Show how many times each player has been on duty (/duty_stats)."""
    translate = context.user_data['translate']
    this_chat_id = update.message.chat_id
    new_chat_id_memoization(this_chat_id, update.message.from_user.language_code)

    stats = db.get_duty_stats(this_chat_id)
    duty_now = db.get_event_duty(this_chat_id)

    lines = [f'🧹 <b>{translate("Duty statistics")}</b>\n']
    if stats:
        for user_id, platform, name, count in stats:
            mark = '' if platform == db.PLATFORM else f' [{_html_escape(platform)}]'
            current = f' ← {translate("current")}' if duty_now and db.is_same_person(
                user_id, platform, duty_now[0], duty_now[1]) else ''
            lines.append(f'{_html_escape(name)}{mark} — {count}{current}')
    else:
        lines.append(f'<i>{translate("Nobody has been on duty yet.")}</i>')

    # Participants of the open event who have never been on duty are the
    # ones /event_duty will pick from next.
    try:
        served = {db.get_person_key(uid, plat) for uid, plat, _, _ in stats}
        never = [
            (name, plat) for uid, plat, name in db.get_duty_candidates(this_chat_id)
            if db.get_person_key(uid, plat) not in served
        ]
        if never:
            lines.append(f'\n<b>{translate("Never on duty")}</b> ({translate("among registered")}):')
            for name, plat in never:
                mark = '' if plat == db.PLATFORM else f' [{_html_escape(plat)}]'
                lines.append(f'{_html_escape(name)}{mark}')
    except Exception as e:
        logger.warning(f"Could not list never-on-duty players: {e}")

    await context.bot.send_message(
        this_chat_id, '\n'.join(lines),
        parse_mode=ParseMode.HTML, disable_web_page_preview=True
    )


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

/link [CODE]
Link this chat with another messenger. Without CODE - generates new code.
With CODE - completes linking with chat that generated the code.

/unlink
Remove link with another messenger chat.

/event_copy
Copy the open event from the linked messenger chat into this one.

/event_duty
Pick the duty player for this event: the one with the fewest past duties
(picked at random among ties). The duty player plays for free.

/mepls
Volunteer yourself for duty instead.

/duty_stats
Duty statistics: how many times each player has been on duty, and who never has.

/event_bank [AMOUNT] [CURRENCY] [NOTE]
Show what the community has in the kitty, or record a new amount. The currency
belongs to this chat and is remembered: /event_bank 5200 ₸, /event_bank 5200 KZT.
After that /event_bank 4800 keeps the same label.

/iam [CODE]
Link your accounts across messengers so duty history follows you, not the
account. Without CODE - issues a code. With CODE - completes the link.

/iam_forget
Unlink your accounts.
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

def _ipv6_advertised_but_dead(host: str, port: int = 443, timeout: float = 3.0) -> bool:
    """True when the host offers IPv6 but a connection over it does not work.

    That combination is what hangs a client: the resolver hands back an AAAA
    record, the client prefers it, and the packets go nowhere.
    """
    try:
        infos = socket.getaddrinfo(host, port, socket.AF_INET6, socket.SOCK_STREAM)
    except socket.gaierror:
        return False          # no IPv6 offered at all — nothing to avoid
    if not infos:
        return False
    for info in infos[:2]:
        # Creating the socket can fail outright on a host built without IPv6
        # ("Address family not supported"), which counts as unreachable.
        try:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        except OSError:
            break
        sock.settimeout(timeout)
        try:
            sock.connect(info[4])
            return False      # IPv6 works, leave the client alone
        except OSError:
            continue
        finally:
            sock.close()
    # IPv6 is advertised and none of it answers — only worth avoiding if v4 works
    try:
        return bool(socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM))
    except socket.gaierror:
        return False


async def on_error(update, context):
    """Report network hiccups as one line instead of a wall of stack trace.

    A timeout while answering a button is not a bug in the bot and should not
    read like one; everything else is still reported in full.
    """
    err = context.error
    # BadRequest subclasses NetworkError in python-telegram-bot, so it has to be
    # excluded explicitly — "message is not modified" and friends are our bugs,
    # not the network's.
    if isinstance(err, (NetworkError, TimedOut)) and not isinstance(err, BadRequest):
        logger.warning(f"Telegram is temporarily unreachable: {type(err).__name__}: {err}")
        return
    logger.opt(exception=err).error("Unhandled error while processing an update")


async def main():
    logger.remove()
    logger.add(os.path.join(BOT_DIR, "logs", "logs.log"), level="INFO")
    logger.add(sys.stderr, level="WARNING")

    # Try environment variable first, then fall back to token.txt
    api_token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not api_token:
        try:
            with open(os.path.join(BOT_DIR, 'token.txt'), encoding='utf-8') as f:
                api_token = f.readline().strip()
        except Exception as err:
            logger.exception(err)
            print("Set TELEGRAM_BOT_TOKEN env variable or create token.txt")
            sys.exit(1)
    if not api_token:
        print("TELEGRAM_BOT_TOKEN is empty")
        sys.exit(1)

    # Configure Telegram API access for blocked regions:
    # Option 1: CF Worker proxy (preferred) — set TG_API_URL to worker URL
    # Option 2: SOCKS/HTTP proxy — set TELEGRAM_PROXY
    proxy_url = os.getenv('TELEGRAM_PROXY')
    tg_api_url = _normalize_tg_api_url(os.getenv('TG_API_URL', ''))
    builder = Application.builder().token(api_token)

    # A host may publish IPv6 that this server cannot actually reach; the client
    # then picks v6 and hangs until the connect timeout. Decide once, at start.
    force_ipv4_env = os.getenv('TELEGRAM_FORCE_IPV4', '').strip().lower()
    if force_ipv4_env in ('1', 'true', 'yes'):
        force_ipv4 = True
    elif force_ipv4_env in ('0', 'false', 'no'):
        force_ipv4 = False
    else:
        api_host = (tg_api_url or 'https://api.telegram.org').split('://', 1)[-1].split('/')[0]
        force_ipv4 = _ipv6_advertised_but_dead(api_host)
        if force_ipv4:
            logger.warning(
                f"{api_host} publishes IPv6 this server cannot reach; using IPv4. "
                f"Set TELEGRAM_FORCE_IPV4=0 to disable this check."
            )

    # The default 5s connect timeout is tight when a proxy or a Worker sits in
    # front of the API. These go either on the builder or inside the request
    # object — python-telegram-bot rejects both at once.
    if force_ipv4:
        import httpx
        from telegram.request import HTTPXRequest

        def _ipv4_request():
            transport_kwargs = {'local_address': '0.0.0.0'}
            if proxy_url:
                transport_kwargs['proxy'] = proxy_url
            return HTTPXRequest(
                connect_timeout=20.0, read_timeout=30.0,
                write_timeout=30.0, pool_timeout=10.0,
                httpx_kwargs={'transport': httpx.AsyncHTTPTransport(**transport_kwargs)},
            )

        builder = builder.request(_ipv4_request()).get_updates_request(_ipv4_request())
        logger.info("Forcing IPv4 for Telegram API connections")
    else:
        builder = (builder
                   .connect_timeout(20.0)
                   .read_timeout(30.0)
                   .write_timeout(30.0)
                   .pool_timeout(10.0))

    api_target = 'api.telegram.org'
    if tg_api_url:
        base = tg_api_url
        api_target = base
        builder = builder.base_url(f'{base}/bot').base_file_url(f'{base}/file/bot')
        logger.info(f"Using Telegram API proxy: {base}")
    elif proxy_url:
        logger.info(f"Using proxy: {proxy_url.split('@')[-1] if '@' in proxy_url else proxy_url}")
        # A custom request object already carries the proxy; setting it again
        # on the builder is the same "two ways to say it" conflict.
        if not force_ipv4:
            builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)
    application = builder.build()

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
    application.add_handler(CommandHandler('link', link_chat))
    application.add_handler(CommandHandler('unlink', unlink_chat))
    application.add_handler(CommandHandler('event_copy', copy_event_from_linked))
    application.add_handler(CommandHandler('event_duty', assign_duty))
    application.add_handler(CommandHandler('mepls', volunteer_duty))
    application.add_handler(CommandHandler('duty_stats', show_duty_stats))
    application.add_handler(CommandHandler('event_bank', show_or_set_bank))
    application.add_handler(CommandHandler('iam', link_identity))
    application.add_handler(CommandHandler('iam_forget', unlink_identity_cmd))
    application.add_handler(CallbackQueryHandler(button))
    application.add_error_handler(on_error)
    application.add_handler(MessageHandler(filters.TEXT | filters.StatusUpdate.NEW_CHAT_MEMBERS, unknown_command_handler))

    logger.info("Telegram Futsal Bot is starting...")
    try:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
    except (NetworkError, TimedOut) as e:
        host = api_target.replace('https://', '').replace('http://', '')
        logger.error(
            f"Cannot reach the Telegram API via {api_target}: {type(e).__name__}: {e}. "
            f"Check that this server can actually reach it "
            f"(curl -sS -m 10 https://{host}/bot<TOKEN>/getMe). "
            f"Removing TG_API_URL from .env falls back to api.telegram.org."
        )
        raise SystemExit(1)

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