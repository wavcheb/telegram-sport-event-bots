# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Created By  : wavcheb 2025
# version ='1.0'
# ---------------------------------------------------------------------------
"""MAX Messenger BOT for organizing events with participant registration.
Adapted from Telegram Sport Event Bot for MAX messenger API.
Russian-only version.
"""

import sys
import os
import datetime
import re
import asyncio
import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Optional, List
from loguru import logger
from dotenv import load_dotenv
import parsedatetime
from recurrent.event_parser import RecurringEvent

# Load environment variables from .env file
load_dotenv()

# Support both package mode and standalone mode
try:
    from . import db_mysql as db
except ImportError:
    import db_mysql as db

# MAX Bot API imports
from maxapi import Bot, Dispatcher
from maxapi.types import (
    MessageCreated,
    MessageCallback,
    BotStarted,
    Command,
    CallbackButton,
)
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder
from maxapi.enums import ParseMode


def _escape_html(s: str) -> str:
    """Escape characters unsafe for MAX HTML parse mode."""
    if s is None:
        return ""
    return (
        str(s)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
    )

# Bot directory paths
BOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Payments page URL from environment
PAYMENTS_PAGE_URL = os.getenv('PAYMENTS_PAGE_URL', '').strip()

# Telegram bot token for cross-platform sync
TG_BOT_TOKEN = os.getenv('TG_BOT_TOKEN', '').strip()

# Optional proxy for Telegram API (regions where Telegram is blocked)
# Supported: socks5://user:pass@host:port, http://host:port, https://host:port
TELEGRAM_PROXY = os.getenv('TELEGRAM_PROXY', '').strip()


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


def parse_datetime(str_datetime_in_free_form: str) -> Optional[datetime.datetime]:
    """Parse datetime from free-form text in Russian."""
    consts = parsedatetime.Constants(localeID='ru_RU', usePyICU=False)
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


def _tg_request_sync(url: str, data: dict) -> Optional[bytes]:
    """Synchronous POST to Telegram API with optional proxy support.
    Uses `requests` when available (SOCKS via PySocks), otherwise urllib.
    """
    # Try requests first - supports SOCKS via requests[socks]
    try:
        import requests  # type: ignore
        proxies = None
        if TELEGRAM_PROXY:
            proxies = {'http': TELEGRAM_PROXY, 'https': TELEGRAM_PROXY}
        resp = requests.post(url, data=data, proxies=proxies, timeout=15)
        if resp.status_code != 200:
            logger.warning(f"Telegram sync HTTP {resp.status_code}: {resp.text[:300]}")
            return None
        return resp.content
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Telegram sync (requests) failed: {e}")
        return None

    # Fallback: urllib with HTTP/HTTPS proxy only (no SOCKS)
    try:
        payload = urllib.parse.urlencode(data).encode('utf-8')
        if TELEGRAM_PROXY and TELEGRAM_PROXY.startswith(('http://', 'https://')):
            proxy_handler = urllib.request.ProxyHandler({
                'http': TELEGRAM_PROXY,
                'https': TELEGRAM_PROXY,
            })
            opener = urllib.request.build_opener(proxy_handler)
        else:
            if TELEGRAM_PROXY:
                logger.warning("TELEGRAM_PROXY is SOCKS but `requests[socks]` not installed; skipping proxy")
            opener = urllib.request.build_opener()
        req = urllib.request.Request(url, data=payload, method='POST')
        req.add_header('Content-Type', 'application/x-www-form-urlencoded')
        with opener.open(req, timeout=15) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode('utf-8', errors='replace')[:300]
        except Exception:
            body = ''
        logger.warning(f"Telegram sync HTTP error: {e.code} {e.reason} {body}")
    except Exception as e:
        logger.warning(f"Telegram sync (urllib) failed: {e}")
    return None


async def sync_to_telegram(linked_chat_id: int, linked_message_id: int, text: str, keyboard_json: str = None):
    """Update message in linked Telegram chat."""
    if not TG_BOT_TOKEN:
        logger.debug("TG_BOT_TOKEN not set, skipping Telegram sync")
        return False

    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageText"
    data = {
        'chat_id': linked_chat_id,
        'message_id': linked_message_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': 'true',
    }
    if keyboard_json:
        data['reply_markup'] = keyboard_json

    result = await asyncio.to_thread(_tg_request_sync, url, data)
    if result:
        logger.info(f"Synced to Telegram chat {linked_chat_id}")
        return True
    return False


def create_telegram_message_text(chat_id: int, payment_url: str = None) -> str:
    """Create event text formatted for Telegram (HTML)."""
    event_title = db.get_event_text(chat_id) or ""
    text = '🎉"<b>' + _escape_html(event_title) + '</b>"🎉\n'

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

    # Links
    links = []
    if payment_url:
        links.append(f'<a href="{_escape_html(payment_url)}">💳 Ссылка для оплаты</a>')
    if PAYMENTS_PAGE_URL:
        try:
            event_id = db.get_event_id_by_chat_id(chat_id)
            primary_event_id = db.get_primary_event_id(event_id)
            payments_link = f'{PAYMENTS_PAGE_URL}?event={primary_event_id}'
            links.append(f'<a href="{_escape_html(payments_link)}">📊 Текущие платежи</a>')
        except:
            pass
    if links:
        text += '\n' + '\n'.join(links) + '\n'

    text += '\n<b>Список игроков:</b>\n'

    # Get all players from both platforms via linked events
    players = db.get_event_users(chat_id) or []

    # Get players from linked event
    linked_players = []
    try:
        event_id = db.get_event_id_by_chat_id(chat_id)
        linked_players = db.get_linked_event_users(event_id)
    except:
        pass

    # Show local players (MAX)
    for n, user_id in enumerate(players, start=1):
        if players_limit and n == players_limit + 1:
            text += '\n<i>Резерв:</i>\n'
        in_squad = '+' if not players_limit or n <= players_limit else '  '
        printable_name = _escape_html(db.compose_full_name(user_id))
        paid = db.get_payment_status(chat_id, user_id)
        payment_mark = ' 💰' if paid else ''
        platform_mark = ' [max]'
        text += f'{in_squad} {n}. {printable_name}{payment_mark}{platform_mark}\n'

    # Show linked players (Telegram)
    if linked_players:
        start_n = len(players) + 1
        for i, (user_id, platform, name) in enumerate(linked_players):
            n = start_n + i
            if players_limit and n == players_limit + 1:
                text += '\n<i>Резерв:</i>\n'
            in_squad = '+' if not players_limit or n <= players_limit else '  '
            safe_name = _escape_html(name)
            platform_mark = f' [{_escape_html(platform)}]' if platform != 'max' else ' [max]'
            text += f'{in_squad} {n}. {safe_name}{platform_mark}\n'

    # Cancelled applications with strikethrough
    canceled_players = db.get_event_revoked_users(chat_id) or []
    if canceled_players:
        text += '\n<i>Отказавшиеся:</i>\n'
        for canceled_user_id in canceled_players:
            cancel_datetime = db.get_user_cancellation_datetime(chat_id, canceled_user_id)
            cd = _coerce_to_datetime(cancel_datetime)
            cd_txt = cd.strftime('%Y-%m-%d %H:%M') if cd else str(cancel_datetime)[:16]
            printable_name = _escape_html(db.compose_full_name(canceled_user_id))
            text += f'  <s>{printable_name} - {_escape_html(cd_txt)}</s>\n'

    return text


def new_chat_id_memoization(chat_id: int, all_known_chat_ids=None):
    """Register new chat if not already known."""
    if all_known_chat_ids is None:
        all_known_chat_ids = db.get_all_chat_ids()
    if chat_id not in all_known_chat_ids:
        all_known_chat_ids.add(chat_id)
        db.register_new_chat_id(chat_id, 'ru')
        logger.info(f'New chat_id: {chat_id}')


def make_keyboard(*rows):
    """Create inline keyboard from button rows. Returns Attachment or None."""
    rows = [r for r in rows if r]
    if not rows:
        return None
    kb = InlineKeyboardBuilder()
    for row in rows:
        kb.row(*row)
    return kb.as_markup()


def build_event_keyboard():
    """Create inline keyboard buttons for event actions."""
    return make_keyboard(
        [CallbackButton(text='+ Записаться', payload='ADD')],
        [CallbackButton(text='- Отписаться', payload='REMOVE')],
        [CallbackButton(text='+ Добавить друга/легионера', payload='ADD_LEGIONEER')],
        [CallbackButton(text='- Убрать последнего легионера', payload='REMOVE_LEGIONEER')],
        [CallbackButton(text='Оплата подтверждена', payload='PAY')],
    )


def create_event_full_text(this_chat_id: int, payment_url: str = None, closed: bool = False) -> str:
    """Create full event text with players list (HTML, Russian)."""
    def player_name_with_cards(games_registered, penalties, full_name):
        printable_name = full_name
        games_played = games_registered - penalties
        if games_registered < 5 or not penalties:
            return printable_name
        ratio = games_played / games_registered
        if ratio < 0.9:
            return f'{printable_name} (Сыграл {games_played} из {games_registered})'
        return printable_name

    event_title = db.get_event_text(this_chat_id) or ""
    title_html = _escape_html(event_title)
    if closed:
        text = f'🎉 "<s><b>{title_html}</b></s>" 🎉  🔒 <i>Событие закрыто</i>\n'
    else:
        text = f'🎉 "<b>{title_html}</b>" 🎉\n'
    players_limit = db.get_event_limit(this_chat_id) or 0
    if players_limit:
        text += f'👥 Лимит игроков: {players_limit}\n'
    raw_dt = db.get_event_datetime(this_chat_id)
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

    # Links section (HTML hyperlinks)
    links = []
    if payment_url:
        links.append(f'<a href="{_escape_html(payment_url)}">💳 Ссылка для оплаты</a>')
    if PAYMENTS_PAGE_URL:
        try:
            event_id = db.get_event_id_by_chat_id(this_chat_id)
            # Use primary (original) event_id for linked events
            primary_event_id = db.get_primary_event_id(event_id)
            payments_link = f'{PAYMENTS_PAGE_URL}?event={primary_event_id}'
            links.append(f'<a href="{_escape_html(payments_link)}">📊 Текущие платежи</a>')
        except:
            pass
    if links:
        text += '\n' + '\n'.join(links) + '\n'

    text += '\n<b>Список игроков:</b>\n'
    text_players = ''
    players = db.get_event_users(this_chat_id) or []

    # Get players from linked event if exists
    linked_players = []
    try:
        event_id = db.get_event_id_by_chat_id(this_chat_id)
        linked_players = db.get_linked_event_users(event_id)
    except:
        pass

    def _wrap_closed(s: str) -> str:
        return f'<s>{s}</s>' if closed else s

    # Show local players
    for n, user_id in enumerate(players, start=1):
        if players_limit and n == players_limit + 1:
            text_players += '\n<i>Резерв:</i>\n'
        in_squad = '+' if not players_limit or n <= players_limit else '  '
        printable_name = _escape_html(db.compose_full_name(user_id))
        games_registered, penalties = db.get_chat_user_rp(this_chat_id, user_id)
        paid = db.get_payment_status(this_chat_id, user_id)
        payment_mark = ' [оплачено]' if paid else ''
        name_line = player_name_with_cards(games_registered, penalties, printable_name)
        text_players += f'{in_squad} {n}. {_wrap_closed(name_line + payment_mark)}\n'

    # Show linked players
    if linked_players:
        start_n = len(players) + 1
        for i, (user_id, platform, name) in enumerate(linked_players):
            n = start_n + i
            if players_limit and n == players_limit + 1:
                text_players += '\n<i>Резерв:</i>\n'
            in_squad = '+' if not players_limit or n <= players_limit else '  '
            safe_name = _escape_html(name)
            platform_mark = f' [{_escape_html(platform)}]'
            text_players += f'{in_squad} {n}. {_wrap_closed(safe_name + platform_mark)}\n'

    text += text_players
    total_players = len(players) + len(linked_players)
    canceled_players = db.get_event_revoked_users(this_chat_id) or []
    if canceled_players:
        text += '\n<i>Отказавшиеся:</i>\n'
        for canceled_user_id in canceled_players:
            cancel_datetime = db.get_user_cancellation_datetime(this_chat_id, canceled_user_id)
            cd = _coerce_to_datetime(cancel_datetime)
            cd_txt = cd.strftime('%Y-%m-%d %H:%M') if cd else str(cancel_datetime)[:16]
            printable_name = _escape_html(db.compose_full_name(canceled_user_id))
            # Strikethrough for all cancelled applications
            text += f'  <s>{printable_name} - {_escape_html(cd_txt)}</s>\n'
    elif total_players == 0:
        text += '\nПока нет заявок'
    safe = text.strip()
    return safe if safe else " "


def parse_cmd_arg(text: str) -> str:
    """Extract command argument from message text."""
    user_input = text.strip()
    space_index = user_input.find(' ')
    if space_index < 0:
        return ''
    return user_input[space_index + 1:].strip()


# Initialize bot and dispatcher
bot: Bot = None
dp = Dispatcher()


@dp.bot_started()
async def on_bot_started(event: BotStarted):
    """Handle bot start event - send welcome message."""
    await event.bot.send_message(
        chat_id=event.chat_id,
        text='Бот запущен! Используйте /help для списка команд.'
    )


@dp.message_created(Command('start'))
async def cmd_start(event: MessageCreated):
    """Handle /start command."""
    chat_id = event.chat.chat_id
    new_chat_id_memoization(chat_id)
    await event.message.answer('Бот запущен! Используйте /help для списка команд.')


@dp.message_created(Command('help'))
async def cmd_help(event: MessageCreated):
    """Handle /help command."""
    help_text = """
Доступные команды бота:

/event_add ТЕКСТ
Создать новое событие

/event_remove
Удалить текущее событие

/event_update ТЕКСТ
Изменить описание события

/limit XX
Установить лимит игроков

/info
Показать информацию о событии

/add
Записаться на событие

/remove
Отписаться от события

/add_leg
Добавить друга/легионера

/rem_leg
Убрать последнего легионера

/pay
Подтвердить оплату

/payments
Показать лог оплат

/fix
Зафиксировать статистику события

/penalty USERID
Добавить штраф игроку

/stat
Статистика участников чата

/link [КОД]
Связать чат с другим мессенджером. Без КОД - генерирует код.
С КОД - завершает связывание с чатом который сгенерировал код.

/unlink
Разорвать связь с другим чатом

/event_copy
Скопировать событие из связанного чата
"""
    await event.message.answer(help_text)


@dp.message_created(Command('event_add'))
async def cmd_event_add(event: MessageCreated):
    """Create new event."""
    chat_id = event.chat.chat_id
    user = event.message.sender
    new_chat_id_memoization(chat_id)

    event_text = parse_cmd_arg(event.message.body.text or '')
    if not event_text:
        await event.message.answer('Ошибка: укажите описание события. Пример: /event_add Футбол в среду')
        return

    if db.get_event_text(chat_id):
        await event.message.answer('Ошибка: уже есть активное событие. Сначала удалите его командой /event_remove')
        return

    # Extract payment URL from event text
    payment_url = None
    url_match = re.search(r'https?://\S+', event_text)
    if url_match:
        payment_url = url_match.group().rstrip('.,)')
        before = event_text[:url_match.start()].strip()
        after = event_text[url_match.end():].strip()
        event_text = ' '.join(filter(None, [before, after])).strip()

    # Parse player limit
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

    # Parse datetime from event text
    event_datetime = parse_datetime(event_text)

    # Create event in database
    db.event_add(chat_id, event_text, event_datetime, event_limit, 0, '')
    if payment_url:
        db.set_event_payment_url(chat_id, payment_url)

    # Build HTML message text with full event info and links
    message_text = create_event_full_text(chat_id, payment_url).strip() or " "

    keyboard = build_event_keyboard()
    sent_msg = await event.bot.send_message(
        chat_id=chat_id,
        text=message_text,
        attachments=[keyboard] if keyboard else None,
        parse_mode=ParseMode.HTML,
    )

    msg_id = sent_msg.message.body.mid if sent_msg and sent_msg.message else ""
    db.save_latest_bot_message(chat_id, msg_id, message_text)


@dp.message_created(Command('event_remove'))
async def cmd_event_remove(event: MessageCreated):
    """Remove current event."""
    chat_id = event.chat.chat_id
    new_chat_id_memoization(chat_id)

    if not db.get_event_text(chat_id):
        db.close_all_open_events_for_chat(chat_id)
        await event.message.answer('Событие удалено.')
        return

    # Build fresh closed-state text (regenerated, not fetched from DB) to
    # avoid any encoding glitches with stored text.
    payment_url = db.get_event_payment_url(chat_id)
    closed_text = create_event_full_text(chat_id, payment_url, closed=True).strip() or " "

    old_msg_id = db.get_latest_bot_message_id(chat_id)
    if old_msg_id:
        try:
            await event.bot.edit_message(
                message_id=old_msg_id,
                text=closed_text,
                attachments=[],
                parse_mode=ParseMode.HTML,
            )
            db.save_latest_bot_message(chat_id, old_msg_id, closed_text)
        except Exception as e:
            logger.info(f"Could not edit old message on event_remove: {e}")

    db.close_all_open_events_for_chat(chat_id)
    await event.message.answer('Событие удалено.')


@dp.message_created(Command('event_update'))
async def cmd_event_update(event: MessageCreated):
    """Update event description."""
    chat_id = event.chat.chat_id
    new_chat_id_memoization(chat_id)

    new_event_text = parse_cmd_arg(event.message.body.text or '')
    if new_event_text:
        db.update_event_text(chat_id, new_event_text)
    await show_info_impl(event)


@dp.message_created(Command('limit'))
async def cmd_limit(event: MessageCreated):
    """Set players limit."""
    chat_id = event.chat.chat_id
    new_chat_id_memoization(chat_id)

    try:
        new_limit = parse_cmd_arg(event.message.body.text or '')
        db.set_players_limit(chat_id, int(new_limit))
    except Exception as e:
        logger.exception(e)


@dp.message_created(Command('info'))
async def cmd_info(event: MessageCreated):
    """Show event info."""
    await show_info_impl(event)


async def show_info_impl(event: MessageCreated, bot=None):
    """Show/refresh event info.

    Strategy: edit the existing bot message in place if present.
    This keeps the event post at the top of the chat and avoids relying
    on button-removal (which is buggy in MAX desktop).
    """
    chat_id = event.chat.chat_id
    new_chat_id_memoization(chat_id)

    if not db.get_event_text(chat_id):
        await event.message.answer('Нет активных событий')
        return

    payment_url = db.get_event_payment_url(chat_id)
    event_text = create_event_full_text(chat_id, payment_url).strip() or " "
    keyboard = build_event_keyboard()

    _bot = bot or event.bot
    old_msg_id = db.get_latest_bot_message_id(chat_id)

    edited = False
    if old_msg_id:
        try:
            await _bot.edit_message(
                message_id=old_msg_id,
                text=event_text,
                attachments=[keyboard] if keyboard else [],
                parse_mode=ParseMode.HTML,
            )
            db.save_latest_bot_message(chat_id, old_msg_id, event_text)
            edited = True
        except Exception as e:
            logger.info(f"edit_message failed, will send new: {e}")

    if not edited:
        sent_msg = await _bot.send_message(
            chat_id=chat_id,
            text=event_text,
            attachments=[keyboard] if keyboard else None,
            parse_mode=ParseMode.HTML,
        )
        msg_id = sent_msg.message.body.mid if sent_msg and sent_msg.message else ""
        db.save_latest_bot_message(chat_id, msg_id, event_text)


@dp.message_created(Command('add'))
async def cmd_add(event: MessageCreated):
    """Add player to event."""
    chat_id = event.chat.chat_id
    user = event.message.sender
    new_chat_id_memoization(chat_id)

    if db.get_event_text(chat_id):
        db.add_or_update_user(user.user_id, user.first_name or '', user.last_name or '', user.username or '')
        db.apply_for_participation_in_the_event(chat_id, user.user_id)
        logger.info(f"Event - Player applied: {user.user_id}")
    await show_info_impl(event)


@dp.message_created(Command('remove'))
async def cmd_remove(event: MessageCreated):
    """Remove player from event."""
    chat_id = event.chat.chat_id
    user = event.message.sender
    new_chat_id_memoization(chat_id)

    if db.get_event_text(chat_id):
        db.add_or_update_user(user.user_id, user.first_name or '', user.last_name or '', user.username or '')
        db.revoke_application_for_the_event(chat_id, user.user_id)
    await show_info_impl(event)


@dp.message_created(Command('add_leg'))
async def cmd_add_legioneer(event: MessageCreated):
    """Add legioneer to event."""
    chat_id = event.chat.chat_id
    user = event.message.sender
    new_chat_id_memoization(chat_id)

    if db.get_event_text(chat_id):
        db.apply_for_legioneer(chat_id, user.user_id)
        full_name = db.compose_full_name(user.user_id)
        await event.bot.send_message(chat_id=chat_id, text=f'Гость добавлен пользователем {full_name}')
        logger.info(f"Event - Legioneer applied in chat: {chat_id}")
    await show_info_impl(event)


@dp.message_created(Command('rem_leg'))
async def cmd_remove_legioneer(event: MessageCreated):
    """Remove legioneer from event."""
    chat_id = event.chat.chat_id
    user = event.message.sender
    new_chat_id_memoization(chat_id)

    if db.get_event_text(chat_id):
        try:
            event_id = db.get_event_id_by_chat_id(chat_id)
            if event_id and db.get_legioneer_user(event_id) > 31:
                full_name = db.compose_full_name(user.user_id)
                await event.bot.send_message(chat_id=chat_id, text=f'Гость удалён пользователем {full_name}')
        except:
            pass
        db.revoke_for_legioneer(chat_id)
        logger.info(f"Event - Legioneer removed in chat: {chat_id}")
    await show_info_impl(event)


@dp.message_created(Command('fix'))
async def cmd_fix(event: MessageCreated):
    """Fix squad and record statistics."""
    chat_id = event.chat.chat_id
    new_chat_id_memoization(chat_id)

    if not db.get_event_text(chat_id):
        await event.message.answer('Нет событий для фиксации статистики')
        return

    text = 'Текущая статистика участников чата:\n'
    players_limit = db.get_event_limit(chat_id)
    for position, userid in enumerate(db.get_event_users(chat_id), start=1):
        if not players_limit or position <= players_limit:
            try:
                full_name = db.compose_full_name(userid)
                games, penalties = db.get_chat_user_rp(chat_id, userid)
                games += 1
                text += f"{full_name} {games}/{penalties}\n"
            except Exception as e:
                logger.exception(e)

    await event.bot.send_message(chat_id=chat_id, text=text)

    # Mark event message as closed (strikethrough, remove buttons) before
    # actually closing it in the DB so that create_event_full_text still
    # has access to event data.
    payment_url = db.get_event_payment_url(chat_id)
    closed_text = create_event_full_text(chat_id, payment_url, closed=True).strip() or " "
    old_msg_id = db.get_latest_bot_message_id(chat_id)
    if old_msg_id:
        try:
            await event.bot.edit_message(
                message_id=old_msg_id,
                text=closed_text,
                attachments=[],
                parse_mode=ParseMode.HTML,
            )
            db.save_latest_bot_message(chat_id, old_msg_id, closed_text)
        except Exception as e:
            logger.info(f"Could not edit old message on fix: {e}")

    db.fix_event(chat_id)


@dp.message_created(Command('pay'))
async def cmd_pay(event: MessageCreated):
    """Confirm payment for the event."""
    chat_id = event.chat.chat_id
    user = event.message.sender
    new_chat_id_memoization(chat_id)

    if not db.get_event_text(chat_id):
        await event.message.answer('Нет активного события.')
        return

    result = db.process_payment(chat_id, user.user_id)
    # Translate result message
    msg_map = {
        'You must be registered for the event to confirm payment.': 'Вы должны быть записаны на событие для подтверждения оплаты.',
        'Payment confirmed!': 'Оплата подтверждена!',
        'Payment for friend confirmed!': 'Оплата за друга подтверждена!',
        'Payment already confirmed.': 'Оплата уже подтверждена.',
    }
    await event.message.answer(msg_map.get(result['message'], result['message']))
    if result['success']:
        await show_info_impl(event)


@dp.message_created(Command('payments'))
async def cmd_payments(event: MessageCreated):
    """Show payment log for current event."""
    chat_id = event.chat.chat_id
    new_chat_id_memoization(chat_id)

    event_title = db.get_event_text(chat_id)
    if not event_title:
        await event.message.answer('Нет активного события.')
        return

    entries = db.get_payment_log(chat_id)
    if not entries:
        await event.message.answer('Пока нет записей об оплате.')
        return

    lines = ['Лог оплат:\n']
    for name, paid_at, for_friend in entries:
        if hasattr(paid_at, 'strftime'):
            time_str = paid_at.strftime('%H:%M')
        else:
            time_str = str(paid_at)[:5]
        note = ' (вероятно за друга)' if for_friend else ' (вероятно за себя)'
        lines.append(f'- {name} отметил оплату в {time_str}{note}')

    await event.message.answer('\n'.join(lines))


@dp.message_created(Command('penalty'))
async def cmd_penalty(event: MessageCreated):
    """Apply penalty to a user."""
    chat_id = event.chat.chat_id
    user = event.message.sender
    new_chat_id_memoization(chat_id)

    user_id_str = parse_cmd_arg(event.message.body.text or '')
    if not user_id_str:
        await event.message.answer('Ошибка: укажите ID пользователя. Пример: /penalty 123456')
        return

    try:
        user_id_int = int(user_id_str)
    except ValueError:
        await event.message.answer('Ошибка: ID пользователя должен быть числом. Пример: /penalty 123456')
        logger.warning(f"Invalid user_id format: {user_id_str}. Expected integer.")
        return

    try:
        db.penalty_for_user_in_chat(chat_id, user_id_int, user.user_id)
        full_name = db.compose_full_name(user_id_int)
        await event.bot.send_message(chat_id=chat_id, text=f'Игроку {full_name} выписан штраф за неявку')
        logger.info(f"Penalty applied to user {user_id_int} in chat {chat_id}")
    except Exception as e:
        logger.exception(e)
        await event.message.answer('Ошибка при добавлении штрафа.')


@dp.message_created(Command('stat'))
async def cmd_stat(event: MessageCreated):
    """Show statistics."""
    chat_id = event.chat.chat_id
    new_chat_id_memoization(chat_id)

    all_userids = db.get_only_chat_participants(chat_id)
    if not all_userids:
        return

    text = 'Текущая статистика участников чата:\n'
    text += 'Регистрации / Штрафы\n'
    for userid in all_userids:
        if userid < 50:  # Skip legioneer IDs (31-49 for MAX, 10-29 for Telegram)
            continue
        printable_name = db.compose_full_name(userid)
        registered, penalties = db.get_chat_user_rp(chat_id, userid)
        text += f"ID:{userid}, {registered:>2}/{penalties}, Имя: {printable_name}\n"

    await event.bot.send_message(chat_id=chat_id, text=text)


@dp.message_created(Command('link'))
async def cmd_link(event: MessageCreated):
    """Link this chat with another platform chat."""
    chat_id = event.chat.chat_id
    new_chat_id_memoization(chat_id)

    # Check if already linked
    linked = db.get_linked_chat(chat_id)
    if linked:
        linked_chat_id, linked_platform = linked
        await event.message.answer(
            f'Этот чат уже связан с {linked_platform} (чат {linked_chat_id}).\n'
            f'Используйте /unlink чтобы разорвать связь.'
        )
        return

    # Check for secret argument
    arg = parse_cmd_arg(event.message.body.text or '')
    if arg:
        secret = arg.strip().upper()
        result = db.complete_chat_link(chat_id, secret)
        if result:
            linked_chat_id, linked_platform = result
            await event.message.answer(
                f'✅ Чаты успешно связаны!\n'
                f'Связан с {linked_platform} (чат {linked_chat_id})'
            )
        else:
            await event.message.answer('❌ Неверный или устаревший код связки.')
        return

    # Generate new secret
    secret = db.create_chat_link(chat_id)
    await event.message.answer(
        f'🔗 Код для связки сгенерирован:\n\n'
        f'{secret}\n\n'
        f'Отправьте этот код в чат другого мессенджера командой /link'
    )


@dp.message_created(Command('unlink'))
async def cmd_unlink(event: MessageCreated):
    """Remove link with another platform chat."""
    chat_id = event.chat.chat_id
    new_chat_id_memoization(chat_id)

    if db.unlink_chat(chat_id):
        await event.message.answer('✅ Связь с другим чатом разорвана.')
    else:
        await event.message.answer('Этот чат не связан с другим чатом.')


@dp.message_created(Command('event_copy'))
async def cmd_event_copy(event: MessageCreated):
    """Copy event from linked chat."""
    chat_id = event.chat.chat_id
    new_chat_id_memoization(chat_id)

    # Check if linked
    linked = db.get_linked_chat(chat_id)
    if not linked:
        await event.message.answer('❌ Этот чат не связан с другим чатом. Используйте /link сначала.')
        return

    linked_chat_id, linked_platform = linked

    # Check if already have active event
    if db.get_event_text(chat_id):
        await event.message.answer('Ошибка: уже есть активное событие. Сначала удалите его командой /event_remove')
        return

    # Get event from linked chat
    linked_event = db.get_event_from_linked_chat(linked_chat_id, linked_platform)
    if not linked_event:
        await event.message.answer(f'❌ В связанном чате ({linked_platform}) нет активного события.')
        return

    linked_event_id, description, event_datetime_str, players_limit, payment_url = linked_event

    # Parse datetime from linked event (stored as string in DB)
    event_dt = _coerce_to_datetime(event_datetime_str) or datetime.datetime.now()

    # Create local event with original datetime
    db.event_add(chat_id, description, event_dt, players_limit, 0, '')

    # Copy payment URL if exists
    if payment_url:
        db.set_event_payment_url(chat_id, payment_url)

    # Get local event id and link events
    local_event_id = db.get_event_id_by_chat_id(chat_id)
    db.create_event_link(linked_event_id, local_event_id)

    # Show the full event (HTML formatted)
    message_text = create_event_full_text(chat_id, payment_url).strip() or " "
    keyboard = build_event_keyboard()
    sent_msg = await event.bot.send_message(
        chat_id=chat_id,
        text=message_text,
        attachments=[keyboard] if keyboard else None,
        parse_mode=ParseMode.HTML,
    )
    msg_id = sent_msg.message.body.mid if sent_msg and sent_msg.message else ""
    db.save_latest_bot_message(chat_id, msg_id, message_text)


@dp.message_callback()
async def handle_callback(event: MessageCallback):
    """Handle inline button callbacks."""
    # Get chat_id from message recipient
    chat_id = event.message.recipient.chat_id
    user = event.callback.user
    callback_data = event.callback.payload

    logger.info(f"Callback: chat_id={chat_id}, user={user.user_id}, action={callback_data}")

    try:
        db.add_or_update_user(user.user_id, user.first_name or '', user.last_name or '', user.username or '')

        if callback_data == "ADD":
            db.apply_for_participation_in_the_event(chat_id, user.user_id)
        elif callback_data == "REMOVE":
            db.revoke_application_for_the_event(chat_id, user.user_id)
        elif callback_data == "ADD_LEGIONEER":
            db.apply_for_legioneer(chat_id, user.user_id)
            full_name = db.compose_full_name(user.user_id)
            await event.bot.send_message(chat_id=chat_id, text=f'Гость добавлен пользователем {full_name}')
        elif callback_data == "REMOVE_LEGIONEER":
            db.revoke_for_legioneer(chat_id)
            try:
                full_name = db.compose_full_name(user.user_id)
                event_id = db.get_event_id_by_chat_id(chat_id)
                if event_id and db.get_legioneer_user(event_id) > 31:
                    await event.bot.send_message(chat_id=chat_id, text=f'Гость удалён пользователем {full_name}')
            except:
                pass
        elif callback_data == "PAY":
            result = db.process_payment(chat_id, user.user_id)
            msg_map = {
                'You must be registered for the event to confirm payment.': 'Вы должны быть записаны на событие для подтверждения оплаты.',
                'Payment confirmed!': 'Оплата подтверждена!',
                'Payment for friend confirmed!': 'Оплата за друга подтверждена!',
                'Payment already confirmed.': 'Оплата уже подтверждена.',
            }
            await event.bot.send_message(chat_id=chat_id, text=msg_map.get(result['message'], result['message']))
    except Exception as e:
        logger.exception(f"Error processing callback action: {e}")

    # Update message with new player list
    payment_url = db.get_event_payment_url(chat_id)
    message_text = create_event_full_text(chat_id, payment_url)
    safe_text = (message_text or "").strip() or " "

    keyboard = build_event_keyboard()

    try:
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text=safe_text,
            attachments=[keyboard] if keyboard else None,
            parse_mode=ParseMode.HTML,
        )
        db.save_latest_bot_message(chat_id, event.message.body.mid, safe_text)
    except Exception as e:
        logger.warning(f"Failed to edit message: {e}")
        # Send new message if edit fails
        sent_msg = await event.bot.send_message(
            chat_id=chat_id,
            text=safe_text,
            attachments=[keyboard] if keyboard else None,
            parse_mode=ParseMode.HTML,
        )
        msg_id = sent_msg.message.body.mid if sent_msg and sent_msg.message else ""
        db.save_latest_bot_message(chat_id, msg_id, safe_text)

    # Cross-platform sync: update linked Telegram chat
    try:
        linked_info = db.get_linked_chat_message_info(chat_id)
        if linked_info:
            linked_chat_id, linked_platform, linked_message_id = linked_info
            if linked_platform == 'telegram' and linked_message_id:
                # Generate Telegram-formatted message using original chat_id's event data
                tg_text = create_telegram_message_text(chat_id, payment_url)
                # Telegram inline keyboard JSON
                tg_keyboard = json.dumps({
                    "inline_keyboard": [
                        [{"text": "+ Записаться", "callback_data": "ADD"}],
                        [{"text": "- Отписаться", "callback_data": "REMOVE"}],
                        [{"text": "+ Добавить друга/легионера", "callback_data": "ADD_LEGIONEER"}],
                        [{"text": "- Убрать последнего легионера", "callback_data": "REMOVE_LEGIONEER"}],
                        [{"text": "💰 Оплата подтверждена", "callback_data": "PAY"}],
                    ]
                })
                await sync_to_telegram(linked_chat_id, linked_message_id, tg_text, tg_keyboard)
    except Exception as e:
        logger.warning(f"Cross-platform sync failed: {e}")


@dp.message_created()
async def log_all_messages(event: MessageCreated):
    """Log all incoming messages for debugging (catch-all fallback)."""
    chat = event.chat
    msg = event.message
    text = msg.body.text if msg and msg.body else ''
    sender = msg.sender if msg else None
    sender_name = f"{sender.first_name or ''} {sender.last_name or ''}".strip() if sender else 'unknown'
    chat_type = getattr(chat, 'type', 'unknown')
    logger.info(f"[DEBUG] Message: chat_id={chat.chat_id}, type={chat_type}, from={sender_name}, text={text[:100]}")


async def main():
    """Main entry point."""
    global bot

    logger.remove()
    logger.add(os.path.join(BOT_DIR, "logs", "logs.log"), level="INFO")
    logger.add(sys.stderr, level="WARNING")

    # Get bot token from environment
    api_token = os.getenv('MAX_BOT_TOKEN')
    if not api_token:
        try:
            with open(os.path.join(BOT_DIR, 'token.txt'), encoding='utf-8') as f:
                api_token = f.readline().strip()
        except Exception as err:
            logger.exception(err)
            print("Set MAX_BOT_TOKEN env variable or create token.txt")
            sys.exit(1)

    if not api_token:
        print("MAX_BOT_TOKEN is empty")
        sys.exit(1)

    bot = Bot(api_token)

    # Initialize database tables
    db.init_database()

    logger.info("MAX Sport Event Bot is starting...")

    # Delete any existing webhook before polling
    try:
        await bot.delete_webhook()
    except Exception as e:
        logger.warning(f"Could not delete webhook: {e}")

    # Start polling
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
