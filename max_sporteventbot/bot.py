# -*- coding: utf-8 -*-
# ---------------------------------------------------------------------------
# Created By  : wavcheb 2025
# version ='1.0'
# ---------------------------------------------------------------------------
"""MAX Messenger BOT for organizing events with participant registration.
Adapted from Telegram Sport Event Bot for MAX messenger API.
"""

import sys
import os
import datetime
import re
import signal
import gettext
import asyncio
from typing import Optional, Callable, List
from functools import wraps
from loguru import logger
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from . import db_mysql as db

# MAX Bot API imports
from maxapi import Bot, Dispatcher
from maxapi.types import (
    MessageCreated,
    MessageCallback,
    BotStarted,
    Command,
    CallbackButton,
)
from maxapi.types.attachments import InlineKeyboard

# Bot directory paths
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCALE_DIR = os.path.join(BOT_DIR, 'locale')

# Translations setup
TRANSLATIONS = {}
try:
    TRANSLATIONS['uk'] = gettext.translation('ua', localedir=LOCALE_DIR, languages=['uk']).gettext
except FileNotFoundError:
    pass
try:
    TRANSLATIONS['pt-br'] = gettext.translation('pt', localedir=LOCALE_DIR, languages=['pt_BR']).gettext
except FileNotFoundError:
    pass
try:
    TRANSLATIONS['ar'] = gettext.translation('ar', localedir=LOCALE_DIR, languages=['ar']).gettext
except FileNotFoundError:
    pass
try:
    TRANSLATIONS['ru'] = gettext.translation('ru', localedir=LOCALE_DIR, languages=['ru']).gettext
except FileNotFoundError:
    pass


def get_translate_func(lang: str) -> Callable[[str], str]:
    """Get translation function for given language."""
    if lang in TRANSLATIONS:
        return TRANSLATIONS[lang]
    return lambda text: text


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


def new_chat_id_memoization(chat_id: int, lang: str, all_known_chat_ids=None):
    """Register new chat if not already known."""
    if all_known_chat_ids is None:
        all_known_chat_ids = db.get_all_chat_ids()
    if chat_id not in all_known_chat_ids:
        all_known_chat_ids.add(chat_id)
        db.register_new_chat_id(chat_id, lang or 'ru')
        logger.info(f'New chat_id: {chat_id}')


def build_message_markup(translate_func: Callable[[str], str]) -> List[List[CallbackButton]]:
    """Create inline keyboard buttons using translation function."""
    rows = [
        [CallbackButton(text=translate_func('+ Apply for participation'), payload='ADD')],
        [CallbackButton(text=translate_func('- Revoke application'), payload='REMOVE')],
        [CallbackButton(text=translate_func('+ Apply friend or legioneer'), payload='ADD_LEGIONEER')],
        [CallbackButton(text=translate_func('- Remove last friend or legioneer'), payload='REMOVE_LEGIONEER')],
    ]
    return rows


def create_event_full_text(this_chat_id: int, translate: Callable[[str], str],
                           payment_url: str = None) -> str:
    """Create full event text with players list."""
    def player_name_with_cards(games_registered, penalties, full_name, translator):
        printable_name = full_name
        games_played = games_registered - penalties
        if games_registered < 5 or not penalties:
            return printable_name
        ratio = games_played / games_registered
        if ratio < 0.9:
            return f'{printable_name} (Played {games_played} from {games_registered})'
        if ratio < 0.8:
            return f'{printable_name} (Played {games_played} from {games_registered})'
        if ratio < 0.7:
            return f'{printable_name} (Played {games_played} from {games_registered})'
        return printable_name

    event_title = db.get_event_text(this_chat_id) or ""
    text = '"' + event_title + '"\n'
    players_limit = db.get_event_limit(this_chat_id) or 0
    if players_limit:
        text += translate('Players limit') + f': {players_limit}\n'
    raw_dt = db.get_event_datetime(this_chat_id)
    event_datetime = _coerce_to_datetime(raw_dt)
    if event_datetime:
        text += translate('Event date and time') + f": {event_datetime.strftime('%Y-%m-%d, %H:%M')}\n"
        now = datetime.datetime.now()
        if event_datetime < now:
            text += translate('Event time out') + '.\n'
        else:
            delta = event_datetime - now
            hours = round(delta.seconds / 3600)
            text += translate('Time left') + f': {delta.days} ' + translate('days') + ' ' + translate('and') + f' {hours} ' + translate('hours') + '\n'

    # Payment link
    if payment_url:
        text += f'\n{translate("Payment link")}: {payment_url}\n'

    text += '\n' + translate('Players list') + ':\n'
    text_players = ''
    players = db.get_event_users(this_chat_id) or []
    for n, user_id in enumerate(players, start=1):
        if players_limit and n == players_limit + 1:
            text_players += '\n' + translate('Reserve') + ':\n'
        in_squad = '+' if not players_limit or n <= players_limit else '  '
        printable_name = db.compose_full_name(user_id)
        games_registered, penalties = db.get_chat_user_rp(this_chat_id, user_id)
        text_players += f'{in_squad} {n}. {player_name_with_cards(games_registered, penalties, printable_name, translate)}\n'

    text += text_players
    canceled_players = db.get_event_revoked_users(this_chat_id) or []
    if canceled_players:
        text += '\n' + translate('Revoked applications') + ':'
        for canceled_user_id in canceled_players:
            cancel_datetime = db.get_user_cancellation_datetime(this_chat_id, canceled_user_id)
            cd = _coerce_to_datetime(cancel_datetime)
            cd_txt = cd.strftime('%Y-%m-%d %H:%M') if cd else str(cancel_datetime)[:16]
            printable_name = db.compose_full_name(canceled_user_id)
            text += f'  {printable_name} - {cd_txt}\n'
    elif not players:
        text += '\n' + translate('No applications yet')
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
    translate = get_translate_func('ru')
    await event.bot.send_message(
        chat_id=event.chat_id,
        text=translate('Bot started! Use /help to see available commands.')
    )


@dp.message_created(Command('start'))
async def cmd_start(event: MessageCreated):
    """Handle /start command."""
    chat_id = event.chat.chat_id
    user = event.message.sender
    lang = 'ru'  # MAX doesn't provide language_code, default to Russian
    new_chat_id_memoization(chat_id, lang)
    translate = get_translate_func(lang)

    await event.message.answer(translate('Bot started! Use /help to see available commands.'))


@dp.message_created(Command('help'))
async def cmd_help(event: MessageCreated):
    """Handle /help command."""
    chat_id = event.chat.chat_id
    lang = db.get_chat_lang(chat_id) if chat_id in db.get_all_chat_ids() else 'ru'
    translate = get_translate_func(lang)

    help_text = translate("""
Available BOT commands:

/event_add TEXT
Register new event

/event_remove
Remove open event

/event_update TEXT
Change event description

/limit XX
Set players limit

/info
Show event details

/add
Register yourself to the event

/remove
Revoke your application

/add_leg
Register another player (legioneer) to the event

/rem_leg
Revoke register for legioneer

/fix
Fix event statistics (increment participants counters)

/penalty USERID
Increase someone's PENALTY counter

/stat
This group members statistics
""")
    await event.message.answer(help_text)


@dp.message_created(Command('event_add'))
async def cmd_event_add(event: MessageCreated):
    """Create new event."""
    chat_id = event.chat.chat_id
    user = event.message.sender
    lang = db.get_chat_lang(chat_id) if chat_id in db.get_all_chat_ids() else 'ru'
    new_chat_id_memoization(chat_id, lang)
    translate = get_translate_func(lang)
    db.set_chat_lang(chat_id, lang)

    event_text = parse_cmd_arg(event.message.body.text or '')
    if not event_text:
        await event.message.answer(translate('Error: Please provide an event description. Usage: /event_add TEXT'))
        return

    if db.get_event_text(chat_id):
        await event.message.answer(translate('Error: An active event already exists. Close it with /event_remove first.'))
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

    message_text = translate("New event created") + ":\n\n" + event_text
    if payment_url:
        message_text += f'\n\n{translate("Payment link")}: {payment_url}'

    keyboard = InlineKeyboard(buttons=build_message_markup(translate))
    sent_msg = await event.bot.send_message(
        chat_id=chat_id,
        text=message_text,
        attachments=[keyboard]
    )

    msg_id = sent_msg.message.body.mid if sent_msg and sent_msg.message else 0
    db.event_add(chat_id, event_text, datetime.datetime.now(), event_limit, msg_id, message_text)
    if payment_url:
        db.set_event_payment_url(chat_id, payment_url)


@dp.message_created(Command('event_remove'))
async def cmd_event_remove(event: MessageCreated):
    """Remove current event."""
    chat_id = event.chat.chat_id
    lang = db.get_chat_lang(chat_id) if chat_id in db.get_all_chat_ids() else 'ru'
    new_chat_id_memoization(chat_id, lang)
    translate = get_translate_func(lang)

    db.close_all_open_events_for_chat(chat_id)
    await event.message.answer(translate('Event removed.'))


@dp.message_created(Command('event_update'))
async def cmd_event_update(event: MessageCreated):
    """Update event description."""
    chat_id = event.chat.chat_id
    lang = db.get_chat_lang(chat_id) if chat_id in db.get_all_chat_ids() else 'ru'
    new_chat_id_memoization(chat_id, lang)

    new_event_text = parse_cmd_arg(event.message.body.text or '')
    if new_event_text:
        db.update_event_text(chat_id, new_event_text)
    await show_info_impl(event)


@dp.message_created(Command('limit'))
async def cmd_limit(event: MessageCreated):
    """Set players limit."""
    chat_id = event.chat.chat_id
    lang = db.get_chat_lang(chat_id) if chat_id in db.get_all_chat_ids() else 'ru'
    new_chat_id_memoization(chat_id, lang)

    try:
        new_limit = parse_cmd_arg(event.message.body.text or '')
        db.set_players_limit(chat_id, int(new_limit))
    except Exception as e:
        logger.exception(e)


@dp.message_created(Command('info'))
async def cmd_info(event: MessageCreated):
    """Show event info."""
    await show_info_impl(event)


async def show_info_impl(event: MessageCreated):
    """Implementation of show info."""
    chat_id = event.chat.chat_id
    lang = db.get_chat_lang(chat_id) if chat_id in db.get_all_chat_ids() else 'ru'
    new_chat_id_memoization(chat_id, lang)
    translate = get_translate_func(lang)

    if not db.get_event_text(chat_id):
        await event.message.answer(translate('No events'))
        return

    payment_url = db.get_event_payment_url(chat_id)
    event_text = create_event_full_text(chat_id, translate, payment_url).strip() or " "

    keyboard = InlineKeyboard(buttons=build_message_markup(translate))
    sent_msg = await event.bot.send_message(
        chat_id=chat_id,
        text=event_text,
        attachments=[keyboard]
    )

    msg_id = sent_msg.message.body.mid if sent_msg and sent_msg.message else 0
    db.save_latest_bot_message(chat_id, msg_id, event_text)


@dp.message_created(Command('add'))
async def cmd_add(event: MessageCreated):
    """Add player to event."""
    chat_id = event.chat.chat_id
    user = event.message.sender
    lang = db.get_chat_lang(chat_id) if chat_id in db.get_all_chat_ids() else 'ru'
    new_chat_id_memoization(chat_id, lang)

    if db.get_event_text(chat_id):
        db.add_or_update_user(user.user_id, user.name or '', '', user.username or '')
        db.apply_for_participation_in_the_event(chat_id, user.user_id)
        logger.info(f"Event - Player applied: {user.user_id}")
    await show_info_impl(event)


@dp.message_created(Command('remove'))
async def cmd_remove(event: MessageCreated):
    """Remove player from event."""
    chat_id = event.chat.chat_id
    user = event.message.sender
    lang = db.get_chat_lang(chat_id) if chat_id in db.get_all_chat_ids() else 'ru'
    new_chat_id_memoization(chat_id, lang)

    if db.get_event_text(chat_id):
        db.add_or_update_user(user.user_id, user.name or '', '', user.username or '')
        db.revoke_application_for_the_event(chat_id, user.user_id)
    await show_info_impl(event)


@dp.message_created(Command('add_leg'))
async def cmd_add_legioneer(event: MessageCreated):
    """Add legioneer to event."""
    chat_id = event.chat.chat_id
    user = event.message.sender
    lang = db.get_chat_lang(chat_id) if chat_id in db.get_all_chat_ids() else 'ru'
    new_chat_id_memoization(chat_id, lang)
    translate = get_translate_func(lang)

    if db.get_event_text(chat_id):
        db.apply_for_legioneer(chat_id, user.user_id)
        full_name = db.compose_full_name(user.user_id)
        legion_text = translate('Guest player applied by %(full_name)s') % {'full_name': full_name}
        await event.bot.send_message(chat_id=chat_id, text=legion_text)
        logger.info(f"Event - Legioneer applied in chat: {chat_id}")
    await show_info_impl(event)


@dp.message_created(Command('rem_leg'))
async def cmd_remove_legioneer(event: MessageCreated):
    """Remove legioneer from event."""
    chat_id = event.chat.chat_id
    user = event.message.sender
    lang = db.get_chat_lang(chat_id) if chat_id in db.get_all_chat_ids() else 'ru'
    new_chat_id_memoization(chat_id, lang)
    translate = get_translate_func(lang)

    if db.get_event_text(chat_id):
        try:
            event_id = db.get_event_id_by_chat_id(chat_id)
            if event_id and db.get_legioneer_user(event_id) > 9:
                full_name = db.compose_full_name(user.user_id)
                legion_text = translate('Guest player was revoked by %(full_name)s') % {'full_name': full_name}
                await event.bot.send_message(chat_id=chat_id, text=legion_text)
        except:
            pass
        db.revoke_for_legioneer(chat_id)
        logger.info(f"Event - Legioneer removed in chat: {chat_id}")
    await show_info_impl(event)


@dp.message_created(Command('fix'))
async def cmd_fix(event: MessageCreated):
    """Fix squad and record statistics."""
    chat_id = event.chat.chat_id
    lang = db.get_chat_lang(chat_id) if chat_id in db.get_all_chat_ids() else 'ru'
    new_chat_id_memoization(chat_id, lang)
    translate = get_translate_func(lang)

    if not db.get_event_text(chat_id):
        await event.message.answer(translate('No events to fix stat for'))
        return

    text = translate('Current statistics for this chat room members:') + '\n'
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
    db.fix_event(chat_id)


@dp.message_created(Command('penalty'))
async def cmd_penalty(event: MessageCreated):
    """Apply penalty to a user."""
    chat_id = event.chat.chat_id
    user = event.message.sender
    lang = db.get_chat_lang(chat_id) if chat_id in db.get_all_chat_ids() else 'ru'
    new_chat_id_memoization(chat_id, lang)
    translate = get_translate_func(lang)

    user_id_str = parse_cmd_arg(event.message.body.text or '')
    if not user_id_str:
        await event.message.answer(translate('Error: Please provide a user ID. Usage: /penalty USERID'))
        return

    try:
        user_id_int = int(user_id_str)
    except ValueError:
        await event.message.answer(translate('Error: User ID must be a number, not a username. Usage: /penalty USERID'))
        logger.warning(f"Invalid user_id format: {user_id_str}. Expected integer.")
        return

    try:
        db.penalty_for_user_in_chat(chat_id, user_id_int, user.user_id)
        full_name = db.compose_full_name(user_id_int)
        penalty_text = translate('The player %(full_name)s was handed a yellow card for non-appearance') % {'full_name': full_name}
        await event.bot.send_message(chat_id=chat_id, text=penalty_text)
        logger.info(f"Penalty applied to user {user_id_int} in chat {chat_id}")
    except Exception as e:
        logger.exception(e)
        await event.message.answer(translate('Error applying penalty.'))


@dp.message_created(Command('stat'))
async def cmd_stat(event: MessageCreated):
    """Show statistics."""
    chat_id = event.chat.chat_id
    lang = db.get_chat_lang(chat_id) if chat_id in db.get_all_chat_ids() else 'ru'
    new_chat_id_memoization(chat_id, lang)
    translate = get_translate_func(lang)

    all_userids = db.get_only_chat_participants(chat_id)
    if not all_userids:
        return

    text = translate('Current statistics for this chat room members:') + '\n'
    text += translate('Registrations / Penalties') + '\n'
    for userid in all_userids:
        if userid < 30:
            continue
        printable_name = db.compose_full_name(userid)
        registered, penalties = db.get_chat_user_rp(chat_id, userid)
        text += f"ID:{userid}, {registered:>2}/{penalties}, Full Name: {printable_name}\n"

    await event.bot.send_message(chat_id=chat_id, text=text)


@dp.message_callback()
async def handle_callback(event: MessageCallback):
    """Handle inline button callbacks."""
    chat_id = event.message.recipient.chat_id
    user = event.callback.user
    callback_data = event.callback.payload

    lang = db.get_chat_lang(chat_id) if chat_id in db.get_all_chat_ids() else 'ru'
    translate = get_translate_func(lang)

    db.add_or_update_user(user.user_id, user.name or '', '', user.username or '')

    if callback_data == "ADD":
        db.apply_for_participation_in_the_event(chat_id, user.user_id)
    elif callback_data == "REMOVE":
        db.revoke_application_for_the_event(chat_id, user.user_id)
    elif callback_data == "ADD_LEGIONEER":
        db.apply_for_legioneer(chat_id, user.user_id)
        full_name = db.compose_full_name(user.user_id)
        legion_text = translate('Guest player applied by %(full_name)s') % {'full_name': full_name}
        await event.bot.send_message(chat_id=chat_id, text=legion_text)
    elif callback_data == "REMOVE_LEGIONEER":
        db.revoke_for_legioneer(chat_id)
        try:
            full_name = db.compose_full_name(user.user_id)
            event_id = db.get_event_id_by_chat_id(chat_id)
            if event_id and db.get_legioneer_user(event_id) > 9:
                legion_text = translate('Guest player was revoked by %(full_name)s') % {'full_name': full_name}
                await event.bot.send_message(chat_id=chat_id, text=legion_text)
        except:
            pass

    # Update message with new player list
    payment_url = db.get_event_payment_url(chat_id)
    message_text = create_event_full_text(chat_id, translate, payment_url)
    safe_text = (message_text or "").strip() or " "

    keyboard = InlineKeyboard(buttons=build_message_markup(translate))

    try:
        await event.bot.edit_message(
            message_id=event.message.body.mid,
            text=safe_text,
            attachments=[keyboard]
        )
        db.save_latest_bot_message(chat_id, event.message.body.mid, safe_text)
    except Exception as e:
        logger.warning(f"Failed to edit message: {e}")
        # Send new message if edit fails
        sent_msg = await event.bot.send_message(
            chat_id=chat_id,
            text=safe_text,
            attachments=[keyboard]
        )
        msg_id = sent_msg.message.body.mid if sent_msg and sent_msg.message else 0
        db.save_latest_bot_message(chat_id, msg_id, safe_text)


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
