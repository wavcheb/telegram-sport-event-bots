# -*- coding: utf-8 -*-
"""
Tournament Bot - Telegram bot for managing sports tournaments
Supports round-robin tournaments with standings calculation
"""

import sys
import os
import signal
import asyncio
from loguru import logger
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
from telegram.constants import ParseMode

from . import db_tournament as db
from . import tournament_logic as logic

# Bot directory path
BOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Configure logging
logger.add(os.path.join(BOT_DIR, "logs", "tournament_bot.log"), rotation="10 MB", level="INFO")

# Translations dictionary
TRANSLATIONS_DICT = {
    'ru': {
        # Common
        'yes': 'Да',
        'no': 'Нет',
        'cancel': 'Отмена',
        'confirm': 'Подтвердить',
        'error': 'Ошибка',
        'success': 'Успех',

        # Tournament creation
        'tournament_creation': '🏆 Создание турнира',
        'how_many_teams': 'Сколько команд будет участвовать?\nВведите число от 2 до 20:',
        'team_count_error': '❌ Количество команд должно быть от 2 до 20.\nПопробуйте еще раз:',
        'teams_added': '✅ Отлично! <b>{count} команд</b>',
        'enter_team_names': 'Теперь введите названия {count} команд.',
        'team_names_format': '<b>Вы можете использовать:</b>\n• Точку с запятой: <code>Барселона; Реал; Бавария</code>\n• Пробел: <code>Барселона Реал Бавария</code>\n• С новой строки:\n<code>Барселона\nРеал\nБавария</code>',
        'teams_list_added': '✅ <b>Команды добавлены:</b>\n<code>{teams_list}</code>',
        'how_many_rounds': 'Сколько кругов будет в турнире?\nВведите число от 1 до 4:',
        'rounds_error': '❌ Количество кругов должно быть от 1 до 4.\nПопробуйте еще раз:',
        'tournament_configured': '🏆 <b>Турнир настроен!</b>\n\n👥 Команд: {num_teams}\n🔄 Кругов: {num_rounds}\n⚽ Всего матчей: {total_matches}\n\nГотовы создать турнирную сетку?',
        'create_grid': '✅ Создать сетку',
        'creation_cancelled': '❌ Создание турнира отменено.',

        # Tournament status
        'tournament_active': '🏆 ТУРНИР АКТИВЕН',
        'matches_played': '⚽ Матчей сыграно: {finished}/{total}',
        'teams_count': '📊 Команд: {count}',
        'rounds_count': '🔄 Кругов: {count}',
        'next_matches': '⚽ <b>Следующие матчи:</b>',
        'refresh_table': '📊 Обновить таблицу',
        'no_active_tournament': '❌ В этом чате нет активного турнира.',
        'create_new_tournament': 'Создайте новый командой /create',
        'tournament_finished': '🏆 ТУРНИР ЗАВЕРШЕН!',

        # Match entry
        'match_number': '⚽ <b>Матч #{number}</b>',
        'enter_score': 'Введите счет матча в формате:\n• <code>3:1</code>\n• <code>3-1</code>\n• <code>3 1</code>',
        'invalid_score_format': '❌ Неверный формат счета.\nИспользуйте: 3:1 или 3-1 или 3 1',
        'result_recorded': '✅ Результат записан!',
        'result_error': '❌ Ошибка при записи результата: {error}',

        # Match results
        'victory': '🏆 Победа: {team}',
        'draw': '🤝 Ничья',

        # Tournament finish
        'only_creator_can_finish': '❌ Только создатель турнира может его завершить досрочно.',
        'no_matches_played': '❌ Нельзя завершить турнир: не сыграно ни одного матча.\nИспользуйте /create для создания нового турнира.',
        'different_games_warning': '⚠️ <b>Внимание!</b>\n\nКоманды сыграли разное количество матчей:\n• Минимум: {min_games}\n• Максимум: {max_games}\n\nПри досрочном завершении в итоговой таблице будут учтены\nтолько команды, сыгравшие <b>{min_games}</b> матчей.\n\nПодтвердите завершение турнира:\n/stopnow confirm',
        'no_confirmation_pending': '❌ Нет ожидающего подтверждения завершения турнира.\nИспользуйте /stopnow для досрочного завершения.',

        # Edit match
        'only_creator_can_edit': '❌ Только создатель турнира может редактировать результаты.',
        'edit_format_error': '❌ Неверный формат.\nИспользуйте: /edit [номер_матча] [счет]\nПример: /edit 5 2:1',
        'match_not_found': '❌ Матч #{number} не найден.',
        'match_not_played': '❌ Матч #{number} еще не сыгран.\nИспользуйте кнопки для ввода результата.',
        'result_updated': '✅ Результат матча #{number} изменен!\n\n⚽ {team1} {score1}:{score2} {team2}\n(Было: {old_score1}:{old_score2})\n\nТаблица пересчитана.',

        # Commands help
        'welcome_message': '🏆 <b>Добро пожаловать в Tournament Bot!</b>\n\nЭтот бот поможет вам организовать турнир с автоматическим расчетом турнирной таблицы.\n\n<b>Как использовать:</b>\n1️⃣ Создайте турнир командой /create\n2️⃣ Укажите количество команд (2-20)\n3️⃣ Введите названия команд\n4️⃣ Выберите количество кругов (1-4)\n5️⃣ Нажмите "Создать сетку"\n6️⃣ Вводите результаты матчей\n7️⃣ Турнир автоматически завершится после всех игр\n\n<b>Основные команды:</b>\n/create - Создать новый турнир\n/status - Текущее состояние турнира\n/table - Показать таблицу\n/stopnow - Досрочно завершить турнир\n/help - Помощь\n\nНачните с команды /create!',
    },
    'en': {
        # Common
        'yes': 'Yes',
        'no': 'No',
        'cancel': 'Cancel',
        'confirm': 'Confirm',
        'error': 'Error',
        'success': 'Success',

        # Tournament creation
        'tournament_creation': '🏆 Tournament Creation',
        'how_many_teams': 'How many teams will participate?\nEnter a number from 2 to 20:',
        'team_count_error': '❌ Number of teams must be between 2 and 20.\nTry again:',
        'teams_added': '✅ Great! <b>{count} teams</b>',
        'enter_team_names': 'Now enter the names of {count} teams.',
        'team_names_format': '<b>You can use:</b>\n• Semicolon: <code>Barcelona; Real; Bayern</code>\n• Space: <code>Barcelona Real Bayern</code>\n• New line:\n<code>Barcelona\nReal\nBayern</code>',
        'teams_list_added': '✅ <b>Teams added:</b>\n<code>{teams_list}</code>',
        'how_many_rounds': 'How many rounds in the tournament?\nEnter a number from 1 to 4:',
        'rounds_error': '❌ Number of rounds must be between 1 and 4.\nTry again:',
        'tournament_configured': '🏆 <b>Tournament configured!</b>\n\n👥 Teams: {num_teams}\n🔄 Rounds: {num_rounds}\n⚽ Total matches: {total_matches}\n\nReady to create the grid?',
        'create_grid': '✅ Create Grid',
        'creation_cancelled': '❌ Tournament creation cancelled.',

        # Tournament status
        'tournament_active': '🏆 TOURNAMENT ACTIVE',
        'matches_played': '⚽ Matches played: {finished}/{total}',
        'teams_count': '📊 Teams: {count}',
        'rounds_count': '🔄 Rounds: {count}',
        'next_matches': '⚽ <b>Next matches:</b>',
        'refresh_table': '📊 Refresh Table',
        'no_active_tournament': '❌ No active tournament in this chat.',
        'create_new_tournament': 'Create a new one with /create',
        'tournament_finished': '🏆 TOURNAMENT FINISHED!',

        # Match entry
        'match_number': '⚽ <b>Match #{number}</b>',
        'enter_score': 'Enter match score in format:\n• <code>3:1</code>\n• <code>3-1</code>\n• <code>3 1</code>',
        'invalid_score_format': '❌ Invalid score format.\nUse: 3:1 or 3-1 or 3 1',
        'result_recorded': '✅ Result recorded!',
        'result_error': '❌ Error recording result: {error}',

        # Match results
        'victory': '🏆 Victory: {team}',
        'draw': '🤝 Draw',

        # Tournament finish
        'only_creator_can_finish': '❌ Only tournament creator can finish it early.',
        'no_matches_played': '❌ Cannot finish tournament: no matches played.\nUse /create for a new tournament.',
        'different_games_warning': '⚠️ <b>Warning!</b>\n\nTeams played different number of matches:\n• Minimum: {min_games}\n• Maximum: {max_games}\n\nWith early finish, only teams with <b>{min_games}</b> matches will be counted.\n\nConfirm tournament finish:\n/stopnow confirm',
        'no_confirmation_pending': '❌ No pending confirmation.\nUse /stopnow for early finish.',

        # Edit match
        'only_creator_can_edit': '❌ Only tournament creator can edit results.',
        'edit_format_error': '❌ Invalid format.\nUse: /edit [match_number] [score]\nExample: /edit 5 2:1',
        'match_not_found': '❌ Match #{number} not found.',
        'match_not_played': '❌ Match #{number} not yet played.\nUse buttons to enter result.',
        'result_updated': '✅ Match #{number} result updated!\n\n⚽ {team1} {score1}:{score2} {team2}\n(Was: {old_score1}:{old_score2})\n\nTable recalculated.',

        # Commands help
        'welcome_message': '🏆 <b>Welcome to Tournament Bot!</b>\n\nThis bot helps you organize tournaments with automatic standings calculation.\n\n<b>How to use:</b>\n1️⃣ Create tournament with /create\n2️⃣ Enter number of teams (2-20)\n3️⃣ Enter team names\n4️⃣ Choose number of rounds (1-4)\n5️⃣ Click "Create Grid"\n6️⃣ Enter match results\n7️⃣ Tournament finishes automatically\n\n<b>Main commands:</b>\n/create - Create new tournament\n/status - Current tournament status\n/table - Show standings\n/stopnow - Finish tournament early\n/help - Help\n\nStart with /create!',
    }
}

def get_translation_function(language_code):
    """Get translation function for given language"""
    lang = language_code if language_code else 'ru'

    # Map language codes
    if lang not in TRANSLATIONS_DICT:
        if lang.startswith('en'):
            lang = 'en'
        else:
            lang = 'ru'  # Default to Russian

    translations = TRANSLATIONS_DICT.get(lang, TRANSLATIONS_DICT['ru'])

    def translate(key, **kwargs):
        """Translate key with optional formatting"""
        text = translations.get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError:
                return text
        return text

    return translate

from functools import wraps

def make_translatable(func):
    """Decorator to add translation function to context"""
    @wraps(func)
    async def wrapped(update, context):
        try:
            # Get language from user
            if update.message:
                lang = update.message.from_user.language_code
            elif update.callback_query:
                lang = update.callback_query.from_user.language_code
            else:
                lang = 'ru'

            if not lang:
                lang = 'ru'

            # Store translation function
            context.user_data['translate'] = get_translation_function(lang)
            logger.info(f'lang={lang}')

        except Exception as e:
            logger.error(f"Language detection error: {e}")
            context.user_data['translate'] = get_translation_function('ru')

        return await func(update, context)
    return wrapped

# FSM States for tournament creation
(
    AWAITING_TEAM_COUNT,
    AWAITING_TEAM_NAMES,
    AWAITING_ROUND_COUNT,
    AWAITING_CONFIRMATION,
    AWAITING_MATCH_SCORE,
    AWAITING_EDIT_MATCH_NUMBER,
    AWAITING_EDIT_SCORE
) = range(7)

# Callback data prefixes
CALLBACK_CREATE_GRID = "create_grid"
CALLBACK_CANCEL = "cancel"
CALLBACK_MATCH_PREFIX = "match_"
CALLBACK_FINISH_EARLY = "finish_early"
CALLBACK_FINISH_CONFIRM = "finish_confirm"
CALLBACK_VIEW_TABLE = "view_table"

# ==================== Helper Functions ====================

def get_chat_id(update: Update) -> int:
    """Get chat_id from update (works for both messages and callbacks)"""
    if update.message:
        return update.message.chat_id
    elif update.callback_query:
        return update.callback_query.message.chat_id
    return None

def get_user_id(update: Update) -> int:
    """Get user_id from update"""
    if update.message:
        return update.message.from_user.id
    elif update.callback_query:
        return update.callback_query.from_user.id
    return None

def is_tournament_creator(user_id: int, tournament_info: dict) -> bool:
    """Check if user is tournament creator"""
    return tournament_info and user_id == tournament_info['creator_id']

async def send_or_edit(update: Update, text: str, reply_markup=None, parse_mode=None):
    """Send new message or edit existing (for callback queries)"""
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        except Exception as e:
            # If can't edit, send new message
            await update.callback_query.message.reply_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    else:
        await update.message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )

# ==================== Start and Help ====================

@make_translatable
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    translate = context.user_data.get('translate', lambda x, **kw: x)
    welcome_text = translate('welcome_message')
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

@make_translatable
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_text = """
📖 <b>Справка по Tournament Bot</b>

<b>🎯 Создание турнира:</b>
/create - Начать создание турнира
• Укажите количество команд (2-20)
• Введите названия через ; или пробел или с новой строки
• Выберите количество кругов (1-4)
• Подтвердите создание

<b>⚽ Проведение матчей:</b>
• Нажмите на кнопку матча
• Введите счет в формате: "3:1" или "3-1" или "3 1"
• Таблица обновится автоматически

<b>📊 Правила подсчета:</b>
• Победа: 3 очка
• Ничья: 1 очко
• Поражение: 0 очков
• При равенстве очков учитывается разница забитых/пропущенных мячей

<b>⚙️ Управление:</b>
/status - Текущее состояние турнира
/table - Показать турнирную таблицу
/stopnow - Досрочно завершить турнир
  ⚠️ При досрочном завершении учитываются только команды,
     сыгравшие одинаковое количество матчей

<b>📝 Редактирование:</b>
/edit [номер_матча] [счет] - Изменить результат матча
Пример: /edit 5 2:1

<b>💡 Полезно знать:</b>
• Один активный турнир одновременно
• Только создатель может управлять турниром
• Турнир автоматически завершается после всех матчей
• Алгоритм Round-Robin гарантирует справедливое расписание

Нужна помощь? Напишите /start для начала!
"""
    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)

# ==================== Tournament Creation (FSM) ====================

async def create_tournament(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start tournament creation process"""
    chat_id = get_chat_id(update)
    user_id = get_user_id(update)

    # Check if there's an active tournament
    active_tournament = db.get_active_tournament(chat_id)
    if active_tournament:
        await update.message.reply_text(
            "❌ В этом чате уже есть активный турнир.\n"
            "Завершите его командой /stopnow или дождитесь окончания."
        )
        return ConversationHandler.END

    # Start creation process
    await update.message.reply_text(
        "🏆 <b>Создание турнира</b>\n\n"
        "Сколько команд будет участвовать?\n"
        "Введите число от 2 до 20:",
        parse_mode=ParseMode.HTML,
        reply_markup=ForceReply(selective=True)
    )

    # Store user_id in context for later
    context.user_data['creator_id'] = user_id
    context.user_data['chat_id'] = chat_id

    return AWAITING_TEAM_COUNT

async def receive_team_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive number of teams"""
    text = update.message.text.strip()

    try:
        count = int(text)
        if not logic.validate_team_count(count):
            await update.message.reply_text(
                "❌ Количество команд должно быть от 2 до 20.\n"
                "Попробуйте еще раз:",
                reply_markup=ForceReply(selective=True)
            )
            return AWAITING_TEAM_COUNT

        # Store count
        context.user_data['num_teams'] = count

        await update.message.reply_text(
            f"✅ Отлично! <b>{count} команд</b>\n\n"
            f"Теперь введите названия {count} команд.\n\n"
            f"<b>Вы можете использовать:</b>\n"
            f"• Точку с запятой: <code>Барселона; Реал; Бавария</code>\n"
            f"• Пробел: <code>Барселона Реал Бавария</code>\n"
            f"• С новой строки:\n<code>Барселона\nРеал\nБавария</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=ForceReply(selective=True)
        )

        return AWAITING_TEAM_NAMES

    except ValueError:
        await update.message.reply_text(
            "❌ Пожалуйста, введите число от 2 до 20:",
            reply_markup=ForceReply(selective=True)
        )
        return AWAITING_TEAM_COUNT

async def receive_team_names(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive team names"""
    text = update.message.text
    expected_count = context.user_data['num_teams']

    # Parse team names
    team_names = logic.parse_team_names(text)

    # Validate
    is_valid, error_msg = logic.validate_team_names(team_names, expected_count)

    if not is_valid:
        await update.message.reply_text(
            f"❌ {error_msg}\n\n"
            f"Попробуйте еще раз. Нужно {expected_count} команд:",
            reply_markup=ForceReply(selective=True)
        )
        return AWAITING_TEAM_NAMES

    # Store team names
    context.user_data['team_names'] = team_names

    # Show teams and ask for rounds
    teams_list = "\n".join(f"{i}. {name}" for i, name in enumerate(team_names, 1))

    await update.message.reply_text(
        f"✅ <b>Команды добавлены:</b>\n"
        f"<code>{teams_list}</code>\n\n"
        f"Сколько кругов будет в турнире?\n"
        f"Введите число от 1 до 4:",
        parse_mode=ParseMode.HTML,
        reply_markup=ForceReply(selective=True)
    )

    return AWAITING_ROUND_COUNT

async def receive_round_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive number of rounds"""
    text = update.message.text.strip()

    try:
        count = int(text)
        if not logic.validate_round_count(count):
            await update.message.reply_text(
                "❌ Количество кругов должно быть от 1 до 4.\n"
                "Попробуйте еще раз:",
                reply_markup=ForceReply(selective=True)
            )
            return AWAITING_ROUND_COUNT

        # Store count
        context.user_data['num_rounds'] = count

        # Show confirmation
        num_teams = context.user_data['num_teams']
        total_matches = logic.calculate_total_matches(num_teams, count)

        keyboard = [
            [InlineKeyboardButton("✅ Создать сетку", callback_data=CALLBACK_CREATE_GRID)],
            [InlineKeyboardButton("❌ Отмена", callback_data=CALLBACK_CANCEL)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"🏆 <b>Турнир настроен!</b>\n\n"
            f"👥 Команд: {num_teams}\n"
            f"🔄 Кругов: {count}\n"
            f"⚽ Всего матчей: {total_matches}\n\n"
            f"Готовы создать турнирную сетку?",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )

        return AWAITING_CONFIRMATION

    except ValueError:
        await update.message.reply_text(
            "❌ Пожалуйста, введите число от 1 до 4:",
            reply_markup=ForceReply(selective=True)
        )
        return AWAITING_ROUND_COUNT

async def confirm_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle grid creation confirmation"""
    query = update.callback_query
    await query.answer()

    if query.data == CALLBACK_CANCEL:
        await query.edit_message_text("❌ Создание турнира отменено.")
        context.user_data.clear()
        return ConversationHandler.END

    if query.data == CALLBACK_CREATE_GRID:
        # Create tournament in database
        chat_id = context.user_data['chat_id']
        creator_id = context.user_data['creator_id']
        num_teams = context.user_data['num_teams']
        num_rounds = context.user_data['num_rounds']
        team_names = context.user_data['team_names']

        try:
            # Create tournament
            tournament_id = db.create_tournament(chat_id, creator_id, num_teams, num_rounds)

            # Add teams
            team_ids = db.add_teams(tournament_id, team_names)

            # Generate matches
            matches = logic.generate_round_robin_schedule(team_ids, num_rounds)
            db.add_matches(tournament_id, matches)

            # Initialize standings
            db.init_standings(tournament_id, team_ids)

            # Activate tournament
            db.activate_tournament(tournament_id)

            # Show initial status
            await show_tournament_status(query, context, tournament_id)

            # Clear context
            context.user_data.clear()

            return ConversationHandler.END

        except Exception as e:
            logger.exception(e)
            await query.edit_message_text(
                f"❌ Ошибка при создании турнира: {str(e)}\n"
                f"Попробуйте еще раз командой /create"
            )
            context.user_data.clear()
            return ConversationHandler.END

async def cancel_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel tournament creation"""
    await update.message.reply_text("❌ Создание турнира отменено.")
    context.user_data.clear()
    return ConversationHandler.END

# ==================== Tournament Status ====================

async def show_tournament_status(update_or_query, context: ContextTypes.DEFAULT_TYPE, tournament_id: int = None):
    """Show current tournament status with next matches"""
    # Determine if this is Update or CallbackQuery
    if isinstance(update_or_query, Update):
        update = update_or_query
        chat_id = get_chat_id(update)
        is_callback = False
    else:
        query = update_or_query
        chat_id = query.message.chat_id
        is_callback = True

    # Get tournament if not provided
    if tournament_id is None:
        tournament = db.get_active_tournament(chat_id)
        if not tournament:
            text = "❌ В этом чате нет активного турнира.\n" \
                   "Создайте новый командой /create"
            if is_callback:
                await query.edit_message_text(text)
            else:
                await update.message.reply_text(text)
            return

        tournament_id = tournament[0]

    # Get tournament info
    tournament_info = db.get_tournament_info(tournament_id)
    if not tournament_info:
        return

    # Get standings
    standings = db.get_standings(tournament_id)

    # Get pending matches
    pending_matches = db.get_pending_matches(tournament_id, limit=4)

    # Count matches
    pending_count, finished_count = db.count_matches_status(tournament_id)
    total_matches = pending_count + finished_count

    # Build message
    lines = []
    lines.append("🏆 <b>ТУРНИР АКТИВЕН</b>\n")
    lines.append(f"⚽ Матчей сыграно: {finished_count}/{total_matches}")
    lines.append(f"📊 Команд: {tournament_info['num_teams']}")
    lines.append(f"🔄 Кругов: {tournament_info['num_rounds']}\n")

    # Standings
    lines.append(logic.format_standings_table(standings))

    # Pending matches as buttons
    keyboard = []
    if pending_matches:
        lines.append(f"\n\n⚽ <b>Следующие матчи:</b>")
        for match_id, round_num, match_num, team1_id, team2_id in pending_matches:
            team1_name = db.get_team_name(team1_id)
            team2_name = db.get_team_name(team2_id)
            button_text = logic.format_match_button_text(team1_name, team2_name)
            keyboard.append([InlineKeyboardButton(
                f"{button_text} (#{match_num})",
                callback_data=f"{CALLBACK_MATCH_PREFIX}{match_id}"
            )])

    # Add view table button
    keyboard.append([InlineKeyboardButton("📊 Обновить таблицу", callback_data=CALLBACK_VIEW_TABLE)])

    reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
    text = "\n".join(lines)

    if is_callback:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    await show_tournament_status(update, context)

async def table_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /table command - show only standings"""
    chat_id = get_chat_id(update)

    tournament = db.get_active_tournament(chat_id)
    if not tournament:
        await update.message.reply_text(
            "❌ В этом чате нет активного турнира."
        )
        return

    tournament_id = tournament[0]
    standings = db.get_standings(tournament_id)

    text = logic.format_standings_table(standings)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

# ==================== Match Handling ====================

async def handle_match_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle match button press"""
    query = update.callback_query
    await query.answer()

    # Handle view table button
    if query.data == CALLBACK_VIEW_TABLE:
        chat_id = query.message.chat_id
        tournament = db.get_active_tournament(chat_id)
        if tournament:
            await show_tournament_status(query, context, tournament[0])
        return

    # Extract match_id from callback data
    if not query.data.startswith(CALLBACK_MATCH_PREFIX):
        return

    match_id = int(query.data[len(CALLBACK_MATCH_PREFIX):])

    # Get match info
    chat_id = query.message.chat_id
    tournament = db.get_active_tournament(chat_id)
    if not tournament:
        await query.edit_message_text("❌ Турнир не найден")
        return

    tournament_id = tournament[0]

    # Get match details from database using match_id
    conn = db.reconnect()
    cur = db._exec(conn, '''
        SELECT match_id, round, match_number, team1_id, team2_id
        FROM Matches
        WHERE match_id = %s AND tournament_id = %s
    ''', (match_id, tournament_id))
    match = cur.fetchone()
    conn.close()

    if not match:
        await query.edit_message_text("❌ Матч не найден")
        return

    match_id, round_num, match_num, team1_id, team2_id = match

    team1_name = db.get_team_name(team1_id)
    team2_name = db.get_team_name(team2_id)

    # Store match info in context for score input
    context.user_data['awaiting_score_for_match'] = match_id
    context.user_data['match_team1_name'] = team1_name
    context.user_data['match_team2_name'] = team2_name

    # Remove inline buttons from the original message
    await query.edit_message_reply_markup(reply_markup=None)

    # Send a new message with ForceReply so the bot can receive
    # the user's response in group chats (privacy mode)
    await query.message.reply_text(
        f"⚽ <b>Матч #{match_num}</b>\n\n"
        f"<b>{team1_name}</b> vs <b>{team2_name}</b>\n\n"
        f"Введите счет матча в формате:\n"
        f"• <code>3:1</code>\n"
        f"• <code>3-1</code>\n"
        f"• <code>3 1</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=ForceReply(selective=True)
    )

async def receive_match_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and process match score"""
    # Check if we're waiting for a score
    if 'awaiting_score_for_match' not in context.user_data:
        return

    match_id = context.user_data['awaiting_score_for_match']
    team1_name = context.user_data['match_team1_name']
    team2_name = context.user_data['match_team2_name']

    text = update.message.text.strip()

    # Parse score
    score = logic.parse_score(text)

    if score is None:
        await update.message.reply_text(
            "❌ Неверный формат счета.\n"
            "Используйте: 3:1 или 3-1 или 3 1",
            reply_markup=ForceReply(selective=True)
        )
        return

    team1_score, team2_score = score

    try:
        # Record match result
        db.record_match_result(match_id, team1_score, team2_score)

        # Recalculate standings
        chat_id = get_chat_id(update)
        tournament = db.get_active_tournament(chat_id)
        tournament_id = tournament[0]
        db.recalculate_standings(tournament_id)

        # Clear context
        context.user_data.pop('awaiting_score_for_match', None)
        context.user_data.pop('match_team1_name', None)
        context.user_data.pop('match_team2_name', None)

        # Show result
        result_text = logic.format_match_result(team1_name, team2_name, team1_score, team2_score)
        await update.message.reply_text(f"✅ Результат записан!\n\n{result_text}")

        # Check if tournament finished
        pending_count, finished_count = db.count_matches_status(tournament_id)

        if pending_count == 0:
            # Tournament finished!
            await finish_tournament_complete(update, context, tournament_id)
        else:
            # Show updated status
            await show_tournament_status(update, context, tournament_id)

    except Exception as e:
        logger.exception(e)
        await update.message.reply_text(f"❌ Ошибка при записи результата: {str(e)}")

# ==================== Tournament Finish ====================

async def stopnow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stopnow command - early tournament finish"""
    chat_id = get_chat_id(update)
    user_id = get_user_id(update)

    tournament = db.get_active_tournament(chat_id)
    if not tournament:
        await update.message.reply_text("❌ В этом чате нет активного турнира.")
        return

    tournament_id, creator_id, num_teams, num_rounds, status = tournament

    # Check if user is creator
    if user_id != creator_id:
        await update.message.reply_text(
            "❌ Только создатель турнира может его завершить досрочно."
        )
        return

    # Check if there are any finished matches
    pending_count, finished_count = db.count_matches_status(tournament_id)

    if finished_count == 0:
        await update.message.reply_text(
            "❌ Нельзя завершить турнир: не сыграно ни одного матча.\n"
            "Используйте /create для создания нового турнира."
        )
        return

    # Check if teams played different numbers of games
    standings = db.get_standings(tournament_id)
    games_played = [row[2] for row in standings]  # played is index 2

    if len(set(games_played)) > 1:
        # Teams played different numbers of games
        min_games = min(games_played)
        max_games = max(games_played)

        # Create confirmation buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"stopnow_confirm_{tournament_id}"),
                InlineKeyboardButton("❌ Отмена", callback_data=f"stopnow_cancel_{tournament_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"⚠️ <b>Внимание!</b>\n\n"
            f"Команды сыграли разное количество матчей:\n"
            f"• Минимум: {min_games}\n"
            f"• Максимум: {max_games}\n\n"
            f"При досрочном завершении в итоговой таблице будут учтены\n"
            f"только команды, сыгравшие <b>{min_games}</b> матчей.\n\n"
            f"<b>Подтвердите завершение турнира:</b>",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        return

    # All teams played same number of games, need confirmation anyway
    keyboard = [
        [
            InlineKeyboardButton("✅ Завершить турнир", callback_data=f"stopnow_confirm_{tournament_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"stopnow_cancel_{tournament_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🏁 <b>Завершить турнир?</b>\n\n"
        f"Сыграно матчей: {finished_count}\n"
        f"Осталось матчей: {pending_count}\n\n"
        f"<b>Подтвердите завершение:</b>",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def handle_stopnow_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle stopnow confirmation buttons"""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id

    logger.info(f"Stopnow callback received: {data} from user {user_id}")

    if data.startswith("stopnow_confirm_"):
        tournament_id = int(data.split("_")[2])

        logger.info(f"Processing stopnow confirm for tournament {tournament_id}")

        # Check creator permission
        tournament = db.get_tournament_info(tournament_id)
        if not tournament:
            await query.answer("❌ Турнир не найден", show_alert=True)
            await query.edit_message_text("❌ Турнир не найден.")
            return

        if tournament['creator_id'] != user_id:
            await query.answer("❌ Только создатель турнира может завершить его", show_alert=True)
            return

        # Answer callback first
        await query.answer("✅ Завершаем турнир...")

        # Finish tournament
        await query.edit_message_text("⏳ Завершаем турнир...")

        logger.info(f"Finishing tournament {tournament_id}")
        await finish_tournament_complete(query.message, context, tournament_id)

    elif data.startswith("stopnow_cancel_"):
        await query.answer("❌ Отменено")
        await query.edit_message_text(
            "❌ Досрочное завершение турнира отменено.\n"
            "Турнир продолжается."
        )

async def finish_tournament_complete(message_or_update, context: ContextTypes.DEFAULT_TYPE, tournament_id: int):
    """Complete tournament finish"""
    logger.info(f"Finishing tournament {tournament_id} - db update")

    try:
        # Finish tournament
        db.finish_tournament(tournament_id)

        # Get current standings to check if normalization is needed
        standings = db.get_standings(tournament_id)
        tournament_info = db.get_tournament_info(tournament_id)

        logger.info(f"Got {len(standings)} standings entries")

        # Check if teams played different numbers of games
        games_played = [row[2] for row in standings]  # row[2] is 'played'
        min_games = min(games_played)
        max_games = max(games_played)

        normalization_note = ""
        if min_games != max_games:
            # Teams played different numbers - use normalized standings
            logger.info(f"Tournament {tournament_id} - teams played different numbers of games ({min_games}-{max_games}), normalizing to {min_games} games")
            standings = db.get_normalized_standings(tournament_id, min_games)
            logger.info(f"Normalized standings received: {len(standings)} entries")
            normalization_note = f"\n\n⚠️ <i>Команды сыграли разное количество матчей ({min_games}-{max_games}). Итоговая таблица рассчитана по первым {min_games} {'играм' if min_games > 1 else 'игре'} каждой команды.</i>"

        logger.info(f"Tournament {tournament_id} - formatting summary")

        # Format summary
        summary = logic.format_tournament_summary(tournament_info, standings)

        # Add normalization note if needed
        if normalization_note:
            summary += normalization_note

        logger.info(f"Tournament {tournament_id} - sending summary")

        # Send summary
        if isinstance(message_or_update, Update):
            await message_or_update.message.reply_text(summary, parse_mode=ParseMode.HTML)
        else:
            # It's a message object from callback query
            await message_or_update.reply_text(summary, parse_mode=ParseMode.HTML)

        logger.info(f"Tournament {tournament_id} finished successfully")

    except Exception as e:
        logger.error(f"Error finishing tournament {tournament_id}: {e}", exc_info=True)
        error_msg = f"❌ Ошибка при завершении турнира: {str(e)}"
        if isinstance(message_or_update, Update):
            await message_or_update.message.reply_text(error_msg)
        else:
            await message_or_update.reply_text(error_msg)

# ==================== Edit Match Result ====================

async def edit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /edit command to modify match result"""
    chat_id = get_chat_id(update)
    user_id = get_user_id(update)

    # Check active tournament
    tournament = db.get_active_tournament(chat_id)
    if not tournament:
        await update.message.reply_text("❌ В этом чате нет активного турнира.")
        return

    tournament_id, creator_id, _, _, _ = tournament

    # Check if user is creator
    if user_id != creator_id:
        await update.message.reply_text(
            "❌ Только создатель турнира может редактировать результаты."
        )
        return

    # Parse command: /edit 5 2:1
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Неверный формат.\n"
            "Используйте: /edit [номер_матча] [счет]\n"
            "Пример: /edit 5 2:1"
        )
        return

    try:
        match_number = int(args[0])
        score_text = args[1]

        # Parse score
        score = logic.parse_score(score_text)
        if score is None:
            await update.message.reply_text(
                "❌ Неверный формат счета.\n"
                "Используйте: 3:1 или 3-1 или 3 1"
            )
            return

        team1_score, team2_score = score

        # Get match
        match = db.get_match_by_number(tournament_id, match_number)
        if not match:
            await update.message.reply_text(f"❌ Матч #{match_number} не найден.")
            return

        match_id, round_num, match_num, team1_id, team2_id, old_score1, old_score2, status = match

        if status != 'finished':
            await update.message.reply_text(
                f"❌ Матч #{match_number} еще не сыгран.\n"
                "Используйте кнопки для ввода результата."
            )
            return

        # Update result
        db.update_match_result(match_id, team1_score, team2_score)

        # Recalculate standings
        db.recalculate_standings(tournament_id)

        # Get team names
        team1_name = db.get_team_name(team1_id)
        team2_name = db.get_team_name(team2_id)

        await update.message.reply_text(
            f"✅ Результат матча #{match_number} изменен!\n\n"
            f"⚽ {team1_name} {team1_score}:{team2_score} {team2_name}\n"
            f"(Было: {old_score1}:{old_score2})\n\n"
            f"Таблица пересчитана."
        )

        # Show updated table
        await show_tournament_status(update, context, tournament_id)

    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат.\n"
            "Используйте: /edit [номер_матча] [счет]\n"
            "Пример: /edit 5 2:1"
        )
    except Exception as e:
        logger.exception(e)
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")

# ==================== PID File Lock ====================

PID_FILE = os.path.join(BOT_DIR, "tournament_bot.pid")

def check_pid_lock():
    """Check if another instance is already running. Exit if so."""
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, 'r') as f:
                old_pid = int(f.read().strip())
            # Check if process is still alive
            os.kill(old_pid, 0)
            # Process exists — another instance is running
            logger.error(f"Another instance is already running (PID {old_pid}). Exiting.")
            print(f"❌ Another instance is already running (PID {old_pid}). Exiting.")
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            # Process is dead or PID file is corrupt — safe to continue
            pass
        except PermissionError:
            # Process exists but we can't signal it — assume it's running
            logger.error("Another instance may be running (permission denied). Exiting.")
            sys.exit(1)

    # Write our PID
    with open(PID_FILE, 'w') as f:
        f.write(str(os.getpid()))

def remove_pid_lock():
    """Remove PID file on exit."""
    try:
        os.remove(PID_FILE)
    except OSError:
        pass

# ==================== Main ====================

async def main():
    """Main function"""
    # Prevent duplicate instances
    check_pid_lock()

    try:
        with open(os.path.join(BOT_DIR, 'token.txt'), encoding='utf-8') as f:
            api_token = f.readline().strip()
    except Exception as err:
        logger.exception(err)
        print("Can not read api_token from token.txt")
        sys.exit(1)

    # Initialize database
    db.init_database()

    # Create application
    application = Application.builder().token(api_token).build()

    # Tournament creation conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('create', create_tournament)],
        states={
            AWAITING_TEAM_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_team_count)],
            AWAITING_TEAM_NAMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_team_names)],
            AWAITING_ROUND_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_round_count)],
            AWAITING_CONFIRMATION: [CallbackQueryHandler(confirm_creation)],
        },
        fallbacks=[CommandHandler('cancel', cancel_creation)],
    )

    # Add handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CommandHandler('table', table_command))
    application.add_handler(CommandHandler('stopnow', stopnow_command))
    application.add_handler(CommandHandler('edit', edit_command))
    # Stopnow confirmation buttons handler (must be before general callback handler)
    application.add_handler(CallbackQueryHandler(handle_stopnow_callback, pattern="^stopnow_"))
    # General callback handler for match buttons
    application.add_handler(CallbackQueryHandler(handle_match_button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_match_score))

    logger.info("Tournament Bot starting...")
    print("🏆 Tournament Bot is running...")

    # Initialize and start bot manually
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    logger.info("Bot is running...")

    # Create stop event for graceful shutdown
    stop_event = asyncio.Event()

    # Setup signal handlers
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

async def shutdown(application, loop):
    """Gracefully shutdown the bot"""
    logger.info("Shutting down bot...")
    remove_pid_lock()
    await application.updater.stop()
    await application.stop()
    await application.shutdown()
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        remove_pid_lock()
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
