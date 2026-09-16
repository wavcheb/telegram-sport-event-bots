# -*- coding: utf-8 -*-
"""This module works with MySQL database with 5 tables: Users, Chats, Events, Participants, Revoked, Penalties
Updated to support payment status for participants. Migrated from sqlite3 to MySQL.
"""

import os
import sys
import random
import datetime
from typing import List, Optional, Set, Tuple
from loguru import logger
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Platform identifier for multi-bot support in shared database
# Each bot sets this to distinguish its data
PLATFORM = 'max'

# Connection settings from environment
MYSQL_CFG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'database': os.getenv('MYSQL_DATABASE', 'futsal_bot'),
    'user': os.getenv('MYSQL_USER', 'futsal_bot'),
    'password': os.getenv('MYSQL_PASSWORD', ''),
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
    'autocommit': True,
    'raise_on_warnings': False,  # Don't raise on warnings like "table already exists"
    'use_unicode': True,
}

# Note: logger is configured by bot.py, don't reconfigure here

def reconnect():
    """Open a new MySQL connection with provided settings"""
    conn = mysql.connector.connect(
        host=MYSQL_CFG['host'],
        database=MYSQL_CFG['database'],
        user=MYSQL_CFG['user'],
        password=MYSQL_CFG['password'],
        autocommit=MYSQL_CFG['autocommit'],
        charset=MYSQL_CFG['charset'],
        collation=MYSQL_CFG['collation'],
        use_unicode=MYSQL_CFG['use_unicode'],
        raise_on_warnings=MYSQL_CFG['raise_on_warnings'],
    )
    # Ensure session has desired charset/collation
    cur = conn.cursor()
    cur.execute("SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;")
    cur.execute("SET CHARACTER SET utf8mb4;")
    cur.close()
    return conn

def _exec(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(sql, params or ())
    return cur

def _exec_many(conn, sql, seq_of_params):
    cur = conn.cursor()
    cur.executemany(sql, seq_of_params)
    return cur

def create_table_users():
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Users (
            user_id BIGINT NOT NULL,
            platform VARCHAR(16) NOT NULL DEFAULT 'max',
            first_name VARCHAR(255) DEFAULT "",
            last_name  VARCHAR(255) DEFAULT "",
            username   VARCHAR(255) DEFAULT "",
            birth_date VARCHAR(32)  DEFAULT "",
            phone      VARCHAR(64)  DEFAULT "",
            facebook   VARCHAR(255) DEFAULT "",
            extra      TEXT,
            PRIMARY KEY (user_id, platform)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')
    conn.commit()
    # Insert or update legioneer users for MAX platform (Друг 1, Друг 2, etc.)
    # MAX uses user_id 31-49, Telegram uses 10-29
    rows = [(uid, PLATFORM, f'Друг {uid - 30}') for uid in range(31, 50)]
    _exec_many(conn, '''
        INSERT INTO Users (user_id, platform, first_name) VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE first_name = VALUES(first_name);
    ''', rows)
    conn.commit()
    conn.close()

def create_table_chats():
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Chats (
            chat_id BIGINT NOT NULL,
            platform VARCHAR(16) NOT NULL DEFAULT 'max',
            lang VARCHAR(8),
            priority_members TEXT,
            latest_event_id BIGINT DEFAULT 0,
            latest_bot_message_id VARCHAR(64),
            latest_bot_message_text TEXT,
            extra1 TEXT,
            extra2 TEXT,
            extra3 TEXT,
            PRIMARY KEY (chat_id, platform)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')
    conn.commit()
    conn.close()

def create_table_events():
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Events (
            event_id BIGINT NOT NULL AUTO_INCREMENT,
            chat_id BIGINT,
            platform VARCHAR(16) NOT NULL DEFAULT 'max',
            status VARCHAR(32) DEFAULT "Open",
            description TEXT,
            datetime VARCHAR(64) DEFAULT "",
            players_limit INT DEFAULT 0,
            payment_url TEXT DEFAULT NULL,
            telegraph_url TEXT DEFAULT NULL,
            extra1 TEXT,
            extra2 TEXT,
            extra3 TEXT,
            PRIMARY KEY (event_id),
            KEY idx_events_chat_platform (chat_id, platform),
            CONSTRAINT fk_events_chat
              FOREIGN KEY (chat_id, platform) REFERENCES Chats(chat_id, platform)
              ON DELETE SET NULL ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')
    conn.commit()
    conn.close()

def create_table_participants():
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Participants (
            event_id BIGINT NOT NULL,
            user_id BIGINT,
            operation_datetime DATETIME NOT NULL,
            paid BOOLEAN DEFAULT FALSE,
            paid_at DATETIME DEFAULT NULL,
            invited_by BIGINT DEFAULT NULL,
            UNIQUE KEY uq_event_user (event_id, user_id),
            KEY idx_participants_event (event_id),
            CONSTRAINT fk_part_event
              FOREIGN KEY (event_id) REFERENCES Events(event_id)
              ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')
    conn.commit()
    conn.close()

def create_table_revoked():
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Revoked (
            event_id BIGINT NOT NULL,
            user_id BIGINT,
            operation_datetime DATETIME NOT NULL,
            UNIQUE KEY uq_rev_event_user (event_id, user_id),
            KEY idx_revoked_event (event_id),
            CONSTRAINT fk_rev_event
              FOREIGN KEY (event_id) REFERENCES Events(event_id)
              ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')
    conn.commit()
    conn.close()

def create_table_chat_penalties():
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Penalties (
            chat_id BIGINT,
            platform VARCHAR(16) NOT NULL DEFAULT 'max',
            user_id BIGINT,
            operation_datetime DATETIME NOT NULL,
            operator_id BIGINT,
            KEY idx_pen_chat_platform (chat_id, platform),
            KEY idx_pen_user_platform (user_id, platform),
            KEY idx_pen_operator_platform (operator_id, platform),
            CONSTRAINT fk_pen_chat
              FOREIGN KEY (chat_id, platform) REFERENCES Chats(chat_id, platform)
              ON DELETE CASCADE ON UPDATE CASCADE,
            CONSTRAINT fk_pen_user
              FOREIGN KEY (user_id, platform) REFERENCES Users(user_id, platform)
              ON DELETE CASCADE ON UPDATE CASCADE,
            CONSTRAINT fk_pen_operator
              FOREIGN KEY (operator_id, platform) REFERENCES Users(user_id, platform)
              ON DELETE CASCADE ON UPDATE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')
    conn.commit()
    conn.close()

def close_all_open_events_for_chat(chat_id: int):
    conn = reconnect()
    _exec(conn, '''UPDATE Events SET status = "Closed" WHERE chat_id = %s AND platform = %s AND status = "Open";''', (chat_id, PLATFORM))
    conn.commit()
    conn.close()

def event_add(chat_id: int, text: str, dtm: datetime.datetime, players_limit: int, latest_bot_message_id: int, latest_bot_message_text: str):
    # Если дата не указана, используем текущую дату/время
    event_datetime = dtm if dtm else datetime.datetime.now()
    conn = reconnect()
    cur = _exec(conn, '''INSERT INTO Events (chat_id, platform, description, datetime, players_limit) VALUES (%s, %s, %s, %s, %s);''',
                (chat_id, PLATFORM, text, event_datetime, players_limit))
    event_id = cur.lastrowid
    _exec(conn, '''UPDATE Chats SET latest_event_id = %s, latest_bot_message_id = %s, latest_bot_message_text = %s WHERE chat_id = %s AND platform = %s;''',
          (event_id, latest_bot_message_id, latest_bot_message_text, chat_id, PLATFORM))
    conn.commit()
    conn.close()

def update_event_text(chat_id, new_text):
    conn = reconnect()
    _exec(conn, '''UPDATE Events SET description = %s WHERE status = "Open" AND chat_id = %s AND platform = %s;''', (new_text, chat_id, PLATFORM))
    conn.commit()
    conn.close()

def get_event_text(chat_id) -> str:
    conn = reconnect()
    cur = _exec(conn, '''SELECT description FROM Events WHERE status="Open" AND chat_id = %s AND platform = %s LIMIT 1;''', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    if not row:
        logger.info("get_event_text -> No events!")
        return ''
    return row[0]

def set_players_limit(chat_id, players_limit: int):
    conn = reconnect()
    _exec(conn, '''UPDATE Events SET players_limit = %s WHERE status = "Open" AND chat_id = %s AND platform = %s;''', (players_limit, chat_id, PLATFORM))
    conn.commit()
    conn.close()

def get_event_limit(chat_id) -> int:
    conn = reconnect()
    cur = _exec(conn, '''SELECT players_limit FROM Events WHERE status="Open" AND chat_id = %s AND platform = %s LIMIT 1;''', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    if not row or row[0] is None:
        logger.warning("get_event_limit -> No events or no limit!")
        return 0
    return int(row[0])

def set_event_datetime(chat_id: int, dtm: datetime.datetime):
    conn = reconnect()
    _exec(conn, '''UPDATE Events SET datetime = %s WHERE status = "Open" AND chat_id = %s AND platform = %s;''', (str(dtm), chat_id, PLATFORM))
    conn.commit()
    conn.close()

def get_event_datetime(chat_id: int) -> str:
    conn = reconnect()
    cur = _exec(conn, '''SELECT datetime FROM Events WHERE status="Open" AND chat_id = %s AND platform = %s LIMIT 1;''', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    if not row:
        logger.warning("get_event_datetime -> No events!")
        return ''
    return row[0]

def get_event_payment_url(chat_id: int) -> Optional[str]:
    conn = reconnect()
    cur = _exec(conn, '''SELECT payment_url FROM Events WHERE status="Open" AND chat_id = %s AND platform = %s LIMIT 1;''', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else None

def set_event_payment_url(chat_id: int, url: Optional[str]):
    conn = reconnect()
    _exec(conn, '''UPDATE Events SET payment_url = %s WHERE status = "Open" AND chat_id = %s AND platform = %s;''', (url, chat_id, PLATFORM))
    conn.commit()
    conn.close()

def get_event_telegraph_url(chat_id: int) -> Optional[str]:
    conn = reconnect()
    cur = _exec(conn, '''SELECT telegraph_url FROM Events WHERE status="Open" AND chat_id = %s AND platform = %s LIMIT 1;''', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else None

def set_event_telegraph_url(chat_id: int, url: Optional[str]):
    conn = reconnect()
    _exec(conn, '''UPDATE Events SET telegraph_url = %s WHERE status = "Open" AND chat_id = %s AND platform = %s;''', (url, chat_id, PLATFORM))
    conn.commit()
    conn.close()

def fix_event(chat_id):
    conn = reconnect()
    _exec(conn, '''UPDATE Events SET status = "Fixed" WHERE status = "Open" AND chat_id = %s AND platform = %s;''', (chat_id, PLATFORM))
    conn.commit()
    conn.close()

def get_latest_bot_message_id(chat_id) -> str:
    """Returns message ID as string (MAX uses string IDs like 'mid.xxx')."""
    conn = reconnect()
    cur = _exec(conn, '''SELECT latest_bot_message_id FROM Chats WHERE chat_id = %s AND platform = %s LIMIT 1;''', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    return str(row[0]) if row and row[0] else ""

def get_latest_bot_message_text(chat_id) -> str:
    conn = reconnect()
    cur = _exec(conn, '''SELECT latest_bot_message_text FROM Chats WHERE chat_id = %s AND platform = %s LIMIT 1;''', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else ""

def save_latest_bot_message(chat_id, message_id, message_text):
    """Remember the announcement the bot can later edit.

    Uses an upsert: a plain UPDATE silently does nothing when the chat has no
    row yet, which would leave the bot unable to edit its own announcement.
    """
    conn = reconnect()
    try:
        cur = _exec(conn, '''
            INSERT INTO Chats (chat_id, platform, latest_bot_message_id, latest_bot_message_text)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                latest_bot_message_id = VALUES(latest_bot_message_id),
                latest_bot_message_text = VALUES(latest_bot_message_text);
        ''', (chat_id, PLATFORM, message_id, message_text))
        conn.commit()
        rows = getattr(cur, 'rowcount', -1)
    except Exception as e:
        logger.error(f"Could not store message id {message_id!r} for chat {chat_id}: {e}")
        conn.close()
        return

    # MAX ids are strings like "mid.abc123". Read the value back: if it did not
    # survive, editing this announcement will fail later with no clue why.
    if message_id:
        try:
            cur = _exec(conn, '''
                SELECT latest_bot_message_id FROM Chats WHERE chat_id = %s AND platform = %s LIMIT 1;
            ''', (chat_id, PLATFORM))
            row = cur.fetchone()
            stored = str(row[0]) if row and row[0] is not None else ''
            if stored != str(message_id):
                logger.error(
                    f"Message id did not persist for chat {chat_id} (platform={PLATFORM}, "
                    f"database={MYSQL_CFG['database']}, rows affected={rows}): "
                    f"sent {message_id!r}, stored {stored!r}. Check the column type with "
                    f"SHOW COLUMNS FROM Chats LIKE 'latest_bot_message_id'; it must be "
                    f"VARCHAR(64), not a numeric type."
                )
        except Exception as e:
            logger.warning(f"Could not verify stored message id for chat {chat_id}: {e}")
    conn.close()

def add_or_update_user(user_id, first_name="", last_name="", username=""):
    first_name = first_name or ""
    last_name = last_name or ""
    username = username or ""
    conn = reconnect()
    cur = _exec(conn, 'SELECT first_name, last_name, username FROM Users WHERE user_id = %s AND platform = %s;', (user_id, PLATFORM))
    row = cur.fetchone()
    if not row:
        logger.debug('Adding NEW user record')
        _exec(conn, 'INSERT INTO Users(user_id, platform, first_name, last_name, username) VALUES (%s, %s, %s, %s, %s)',
              (user_id, PLATFORM, first_name, last_name, username))
    elif row != (first_name, last_name, username):
        logger.debug('Updating user record')
        _exec(conn, 'UPDATE Users SET first_name = %s, last_name = %s, username = %s WHERE user_id = %s AND platform = %s;',
              (first_name, last_name, username, user_id, PLATFORM))
    else:
        logger.debug('    no new data')
    conn.commit()
    conn.close()

def compose_full_name(user_id: int) -> str:
    conn = reconnect()
    cur = _exec(conn, '''SELECT first_name, last_name, username FROM Users WHERE user_id = %s AND platform = %s;''', (user_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    if not row:
        return 'USER_ID NOT FOUND!'
    fnm = row[0] or ''
    lnm = row[1] or ''
    unm = row[2] or ''
    res = " ".join([fnm, lnm]).strip()
    if res and unm:
        res = f"{res} ({unm})"
    if not res and unm:
        res = unm
    if not res:
        return str(user_id)
    return res

def penalty_for_user_in_chat(chat_id, user_id, operator_id: int):
    conn = reconnect()
    dtm = datetime.datetime.now()
    _exec(conn, '''INSERT INTO Penalties(chat_id, platform, user_id, operation_datetime, operator_id) VALUES (%s, %s, %s, %s, %s);''',
          (chat_id, PLATFORM, user_id, dtm, operator_id))
    conn.commit()
    conn.close()

def get_all_userids() -> List[int]:
    conn = reconnect()
    cur = _exec(conn, '''SELECT user_id FROM Users WHERE platform = %s;''', (PLATFORM,))
    all_rows = cur.fetchall()
    conn.close()
    return [int(row[0]) for row in all_rows]

def get_all_chat_ids() -> Set[int]:
    conn = reconnect()
    cur = _exec(conn, '''SELECT chat_id FROM Chats WHERE platform = %s;''', (PLATFORM,))
    all_rows = cur.fetchall()
    conn.close()
    return set(int(row[0]) for row in all_rows)

def register_new_chat_id(chat_id: int, lang: str):
    """Create the chat's row. INSERT IGNORE used to hide real failures here —
    e.g. a NOT NULL column added to Chats outside the bot's schema — leaving
    the chat with no row at all, so nothing about it could be remembered."""
    language_code = lang or ''
    conn = reconnect()
    try:
        _exec(conn, '''
            INSERT INTO Chats (chat_id, platform, lang) VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE lang = VALUES(lang);
        ''', (chat_id, PLATFORM, language_code))
        conn.commit()
    except Exception as e:
        logger.error(f"Could not register chat {chat_id} (platform={PLATFORM}): {e}")
    conn.close()

def get_only_chat_participants(chat_id: int) -> List[int]:
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT DISTINCT p.user_id
        FROM Participants p
        WHERE p.event_id = (SELECT e.event_id FROM Events e WHERE e.chat_id = %s AND e.platform = %s ORDER BY e.event_id DESC LIMIT 1);
    ''', (chat_id, PLATFORM))
    rows = cur.fetchall()
    conn.close()
    return [int(r[0]) for r in rows] if rows else []

def get_chat_lang(chat_id: int) -> str:
    conn = reconnect()
    cur = _exec(conn, 'SELECT lang FROM Chats WHERE chat_id = %s AND platform = %s;', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    if not row or not row[0]:
        logger.info(f'Can not get LANG for this chat_id: {chat_id}')
        return 'en'
    return row[0]

def set_chat_lang(chat_id: int, lang: str):
    conn = reconnect()
    _exec(conn, "UPDATE Chats SET lang = %s WHERE chat_id = %s AND platform = %s;", (lang, chat_id, PLATFORM))
    conn.commit()
    conn.close()

def get_event_users(chat_id: int) -> List[int]:
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT p.user_id
        FROM Participants p
        WHERE p.event_id IN (
            SELECT e.event_id FROM Events e WHERE e.status = "Open" AND e.chat_id = %s AND e.platform = %s
        )
        ORDER BY p.operation_datetime;
    ''', (chat_id, PLATFORM))
    rows = cur.fetchall()
    conn.close()
    return [int(r[0]) for r in rows] if rows else []

def get_event_revoked_users(chat_id: int) -> List[int]:
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT r.user_id
        FROM Revoked r
        WHERE r.event_id IN (
            SELECT e.event_id FROM Events e WHERE e.status = "Open" AND e.chat_id = %s AND e.platform = %s
        )
        ORDER BY r.operation_datetime;
    ''', (chat_id, PLATFORM))
    rows = cur.fetchall()
    conn.close()
    return [int(r[0]) for r in rows] if rows else []

def apply_for_participation_in_the_event(chat_id: int, user_id: int):
    logger.info(f"Event - New player request: {user_id}")
    conn = reconnect()

    # Проверяем наличие активного события
    cur = _exec(conn, '''
        SELECT e.event_id FROM Events e WHERE e.status = "Open" AND e.chat_id = %s AND e.platform = %s ORDER BY e.event_id DESC LIMIT 1
    ''', (chat_id, PLATFORM))
    event = cur.fetchone()

    if not event:
        logger.warning(f"No active event found for chat {chat_id}. Cannot register user {user_id}.")
        conn.close()
        return

    event_id = event[0]
    dtm = datetime.datetime.now()

    _exec(conn, '''
        INSERT INTO Participants (event_id, user_id, operation_datetime, paid)
        VALUES (%s, %s, %s, FALSE)
        ON DUPLICATE KEY UPDATE operation_datetime = VALUES(operation_datetime);
    ''', (event_id, user_id, dtm))
    _exec(conn, '''
        DELETE FROM Revoked WHERE event_id = %s AND user_id = %s;
    ''', (event_id, user_id))
    conn.commit()
    conn.close()

def revoke_application_for_the_event(chat_id: int, user_id: int):
    logger.info(f"Event - Player canceled request: {user_id}")
    conn = reconnect()

    # Проверяем наличие активного события
    cur = _exec(conn, '''
        SELECT e.event_id FROM Events e WHERE e.status = "Open" AND e.chat_id = %s AND e.platform = %s ORDER BY e.event_id DESC LIMIT 1
    ''', (chat_id, PLATFORM))
    event = cur.fetchone()

    if not event:
        logger.warning(f"No active event found for chat {chat_id}. Cannot revoke user {user_id}.")
        conn.close()
        return

    event_id = event[0]
    dtm = datetime.datetime.now()

    _exec(conn, '''
        INSERT INTO Revoked (event_id, user_id, operation_datetime)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE operation_datetime = VALUES(operation_datetime);
    ''', (event_id, user_id, dtm))
    _exec(conn, '''
        DELETE FROM Participants WHERE event_id = %s AND user_id = %s;
    ''', (event_id, user_id))
    conn.commit()
    conn.close()

def get_event_id_by_chat_id(chat_id):
    conn = reconnect()
    cur = _exec(conn, 'SELECT MAX(event_id) FROM Events WHERE chat_id = %s AND platform = %s;', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return int(row[0])
    raise ValueError(f"No event found for chat_id: {chat_id}")

def get_legioneer_user(event_id: int):
    """Get next available legioneer user_id for MAX (range 31-49)."""
    conn = reconnect()
    cur = _exec(conn, 'SELECT COUNT(user_id) FROM Participants WHERE event_id = %s AND user_id BETWEEN 31 AND 49;', (event_id,))
    count = cur.fetchone()
    conn.close()
    if count is not None:
        return int(count[0]) + 31
    raise ValueError(f"Strange error - not found legioners in event {event_id}")

def apply_for_legioneer(chat_id, invited_by_user_id=None):
    logger.info(f"Event - New legioneer-player request from chat {chat_id}")
    conn = reconnect()
    event_id = get_event_id_by_chat_id(chat_id)
    user_id = get_legioneer_user(event_id)
    dtm = datetime.datetime.now()
    _exec(conn, '''
        INSERT INTO Participants (event_id, user_id, operation_datetime, paid, invited_by)
        VALUES (%s, %s, %s, FALSE, %s)
        ON DUPLICATE KEY UPDATE operation_datetime = VALUES(operation_datetime), invited_by = VALUES(invited_by);
    ''', (event_id, user_id, dtm, invited_by_user_id))
    _exec(conn, '''
        DELETE FROM Revoked WHERE event_id = %s AND user_id = %s;
    ''', (event_id, user_id))
    conn.commit()
    conn.close()

def revoke_for_legioneer(chat_id):
    """Remove last legioneer from event. MAX uses user_id 31-59."""
    logger.info(f"Event - Legioneer-player canceled request for chat: {chat_id}")
    conn = reconnect()
    event_id = get_event_id_by_chat_id(chat_id)
    user_id = get_legioneer_user(event_id) - 1
    if user_id > 30:
        dtm = datetime.datetime.now()
        _exec(conn, 'DELETE FROM Participants WHERE event_id = %s AND user_id = %s;', (event_id, user_id))
        _exec(conn, '''
            INSERT INTO Revoked (event_id, user_id, operation_datetime)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE operation_datetime = VALUES(operation_datetime);
        ''', (event_id, user_id, dtm))
        conn.commit()
    else:
        logger.warning(f"There is no legioners in chat {chat_id}. User id is {user_id} No operation performed.")
    conn.close()

def get_chat_user_rp(chat_id, user_id: int) -> Tuple[int, int]:
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT COUNT(*)
        FROM Participants p
        WHERE p.event_id IN (
            SELECT e.event_id FROM Events e WHERE e.status = "Fixed" AND e.chat_id = %s AND e.platform = %s
        )
        AND p.user_id = %s;
    ''', (chat_id, PLATFORM, user_id))
    chat_games = int(cur.fetchone()[0])
    cur = _exec(conn, 'SELECT COUNT(*) FROM Penalties WHERE chat_id = %s AND platform = %s AND user_id = %s;', (chat_id, PLATFORM, user_id))
    chat_penalties = int(cur.fetchone()[0])
    conn.close()
    return (chat_games, chat_penalties)

def get_user_cancellation_datetime(chat_id, canceled_user_id: int) -> str:
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT r.operation_datetime
        FROM Revoked r
        WHERE r.event_id = (
            SELECT e.event_id FROM Events e WHERE e.status = "Open" AND e.chat_id = %s AND e.platform = %s ORDER BY e.event_id DESC LIMIT 1
        )
        AND r.user_id = %s
        LIMIT 1;
    ''', (chat_id, PLATFORM, canceled_user_id))
    row = cur.fetchone()
    conn.close()
    if not row:
        logger.error(f'Strange situation for chat_id = {chat_id} and canceled_user_id = {canceled_user_id}')
        return 'DATETIME NOT FOUND'
    return row[0].strftime('%Y-%m-%d %H:%M:%S') if isinstance(row[0], datetime.datetime) else str(row[0])

def set_payment_status(chat_id: int, user_id: int, paid: bool = True):
    """Set payment status for a player in the open event of a chat"""
    conn = reconnect()
    paid_at = datetime.datetime.now() if paid else None
    _exec(conn, '''
        UPDATE Participants p
        JOIN (
            SELECT e.event_id FROM Events e WHERE e.status = "Open" AND e.chat_id = %s AND e.platform = %s ORDER BY e.event_id DESC LIMIT 1
        ) ev ON p.event_id = ev.event_id
        SET p.paid = %s, p.paid_at = %s
        WHERE p.user_id = %s;
    ''', (chat_id, PLATFORM, 1 if paid else 0, paid_at, user_id))
    conn.commit()
    conn.close()

def get_payment_status(chat_id: int, user_id: int) -> bool:
    """Get payment status for a player"""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT p.paid
        FROM Participants p
        WHERE p.event_id = (
            SELECT e.event_id FROM Events e WHERE e.status = "Open" AND e.chat_id = %s AND e.platform = %s ORDER BY e.event_id DESC LIMIT 1
        )
        AND p.user_id = %s
        LIMIT 1;
    ''', (chat_id, PLATFORM, user_id))
    row = cur.fetchone()
    conn.close()
    return bool(row[0]) if row else False

def create_table_payment_log():
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS PaymentLog (
            log_id BIGINT NOT NULL AUTO_INCREMENT,
            event_id BIGINT NOT NULL,
            payer_user_id BIGINT NOT NULL,
            paid_at DATETIME NOT NULL,
            for_friend BOOLEAN DEFAULT FALSE,
            PRIMARY KEY (log_id),
            KEY idx_paylog_event (event_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')
    conn.commit()
    conn.close()


def create_table_chat_links():
    """Create table for linking chats across platforms."""
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS ChatLinks (
            link_id BIGINT NOT NULL AUTO_INCREMENT,
            chat_id_1 BIGINT NOT NULL,
            platform_1 VARCHAR(16) NOT NULL,
            chat_id_2 BIGINT DEFAULT NULL,
            platform_2 VARCHAR(16) DEFAULT NULL,
            link_secret VARCHAR(32) NOT NULL,
            created_at DATETIME NOT NULL,
            linked_at DATETIME DEFAULT NULL,
            PRIMARY KEY (link_id),
            UNIQUE KEY uq_link_secret (link_secret),
            KEY idx_chat1 (chat_id_1, platform_1),
            KEY idx_chat2 (chat_id_2, platform_2)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')
    conn.commit()
    conn.close()


def create_table_event_links():
    """Create table for linking events across platforms."""
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS EventLinks (
            link_id BIGINT NOT NULL AUTO_INCREMENT,
            event_id_1 BIGINT NOT NULL,
            event_id_2 BIGINT NOT NULL,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (link_id),
            UNIQUE KEY uq_event_pair (event_id_1, event_id_2),
            KEY idx_event1 (event_id_1),
            KEY idx_event2 (event_id_2)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')
    conn.commit()
    conn.close()


def generate_link_secret() -> str:
    """Generate a random secret for chat linking."""
    import secrets
    return secrets.token_hex(4).upper()  # 8 characters


def create_chat_link(chat_id: int) -> str:
    """Create a pending link for this chat. Returns the secret."""
    conn = reconnect()
    secret = generate_link_secret()
    now = datetime.datetime.now()
    _exec(conn, '''
        INSERT INTO ChatLinks (chat_id_1, platform_1, link_secret, created_at)
        VALUES (%s, %s, %s, %s)
    ''', (chat_id, PLATFORM, secret, now))
    conn.commit()
    conn.close()
    return secret


def complete_chat_link(chat_id: int, secret: str) -> Optional[Tuple[int, str]]:
    """Complete linking by providing secret. Returns (linked_chat_id, linked_platform) or None."""
    conn = reconnect()
    # Find pending link with this secret
    cur = _exec(conn, '''
        SELECT link_id, chat_id_1, platform_1 FROM ChatLinks
        WHERE link_secret = %s AND chat_id_2 IS NULL AND linked_at IS NULL
        LIMIT 1
    ''', (secret.upper(),))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None

    link_id, linked_chat_id, linked_platform = row

    # Don't allow linking to same platform
    if linked_platform == PLATFORM:
        conn.close()
        return None

    # Complete the link
    now = datetime.datetime.now()
    _exec(conn, '''
        UPDATE ChatLinks SET chat_id_2 = %s, platform_2 = %s, linked_at = %s
        WHERE link_id = %s
    ''', (chat_id, PLATFORM, now, link_id))
    conn.commit()
    conn.close()
    return (linked_chat_id, linked_platform)


def get_linked_chat(chat_id: int) -> Optional[Tuple[int, str]]:
    """Get linked chat for this chat. Returns (linked_chat_id, linked_platform) or None."""
    conn = reconnect()
    # Check if this chat is chat_id_1
    cur = _exec(conn, '''
        SELECT chat_id_2, platform_2 FROM ChatLinks
        WHERE chat_id_1 = %s AND platform_1 = %s AND linked_at IS NOT NULL
        LIMIT 1
    ''', (chat_id, PLATFORM))
    row = cur.fetchone()
    if row and row[0]:
        conn.close()
        return (row[0], row[1])

    # Check if this chat is chat_id_2
    cur = _exec(conn, '''
        SELECT chat_id_1, platform_1 FROM ChatLinks
        WHERE chat_id_2 = %s AND platform_2 = %s AND linked_at IS NOT NULL
        LIMIT 1
    ''', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    if row:
        return (row[0], row[1])
    return None


def get_linked_chat_message_info(chat_id: int) -> Optional[Tuple[int, str, str]]:
    """Get linked chat's message info for cross-platform sync.
    Returns (linked_chat_id, linked_platform, linked_message_id) or None.
    Note: message_id is string (MAX uses 'mid.xxx', TG uses numeric strings)."""
    linked = get_linked_chat(chat_id)
    if not linked:
        return None
    linked_chat_id, linked_platform = linked
    conn = reconnect()
    # Only sync into a chat that still has an OPEN event. Once its event is
    # fixed or removed, its announcement has been struck through and stripped
    # of buttons — overwriting it would undo that and bring the buttons back.
    cur = _exec(conn, '''
        SELECT c.latest_bot_message_id FROM Chats c
        WHERE c.chat_id = %s AND c.platform = %s
          AND EXISTS (
              SELECT 1 FROM Events e
              WHERE e.chat_id = c.chat_id AND e.platform = c.platform
                AND e.status = 'Open'
          )
        LIMIT 1
    ''', (linked_chat_id, linked_platform))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return (linked_chat_id, linked_platform, str(row[0]))
    return None


def unlink_chat(chat_id: int) -> bool:
    """Remove link for this chat. Returns True if link was removed."""
    conn = reconnect()
    cur = _exec(conn, '''
        DELETE FROM ChatLinks
        WHERE (chat_id_1 = %s AND platform_1 = %s) OR (chat_id_2 = %s AND platform_2 = %s)
    ''', (chat_id, PLATFORM, chat_id, PLATFORM))
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return affected > 0


def get_linked_event_id(event_id: int) -> Optional[int]:
    """Get linked event for this event. Returns linked_event_id or None."""
    conn = reconnect()
    # Check event_id_1
    cur = _exec(conn, 'SELECT event_id_2 FROM EventLinks WHERE event_id_1 = %s LIMIT 1', (event_id,))
    row = cur.fetchone()
    if row:
        conn.close()
        return row[0]
    # Check event_id_2
    cur = _exec(conn, 'SELECT event_id_1 FROM EventLinks WHERE event_id_2 = %s LIMIT 1', (event_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def get_primary_event_id(event_id: int) -> int:
    """Get the primary (original) event ID. If this is a copied event, returns the original.
    Otherwise returns the same event_id."""
    conn = reconnect()
    # If this event is event_id_2 (copy), return event_id_1 (original)
    cur = _exec(conn, 'SELECT event_id_1 FROM EventLinks WHERE event_id_2 = %s LIMIT 1', (event_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else event_id


def create_event_link(event_id_1: int, event_id_2: int):
    """Link two events together."""
    conn = reconnect()
    now = datetime.datetime.now()
    _exec(conn, '''
        INSERT IGNORE INTO EventLinks (event_id_1, event_id_2, created_at)
        VALUES (%s, %s, %s)
    ''', (event_id_1, event_id_2, now))
    conn.commit()
    conn.close()


def get_event_from_linked_chat(linked_chat_id: int, linked_platform: str) -> Optional[Tuple[int, str, str, int, str]]:
    """Get open event from linked chat. Returns (event_id, description, datetime, players_limit, payment_url) or None."""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT event_id, description, datetime, players_limit, COALESCE(payment_url, '') FROM Events
        WHERE chat_id = %s AND platform = %s AND status = "Open"
        ORDER BY event_id DESC LIMIT 1
    ''', (linked_chat_id, linked_platform))
    row = cur.fetchone()
    conn.close()
    return row if row else None


def get_linked_event_users(event_id: int) -> List[Tuple[int, str, str]]:
    """Get users from linked event. Returns [(user_id, platform, display_name), ...]."""
    linked_event_id = get_linked_event_id(event_id)
    if not linked_event_id:
        return []

    conn = reconnect()
    # Get participants with their platform info
    cur = _exec(conn, '''
        SELECT p.user_id, e.platform, u.first_name, u.last_name, u.username
        FROM Participants p
        JOIN Events e ON p.event_id = e.event_id
        LEFT JOIN Users u ON p.user_id = u.user_id AND u.platform = e.platform
        WHERE p.event_id = %s
        ORDER BY p.operation_datetime
    ''', (linked_event_id,))
    rows = cur.fetchall()
    conn.close()

    result = []
    for row in rows:
        user_id, platform, fnm, lnm, unm = row
        fnm = fnm or ''
        lnm = lnm or ''
        unm = unm or ''
        name = " ".join([fnm, lnm]).strip()
        if name and unm:
            name = f"{name} ({unm})"
        elif not name and unm:
            name = unm
        elif not name:
            name = str(user_id)
        result.append((user_id, platform, name))
    return result

# ==================== Cross-platform identity ====================

# One human may hold an account in each messenger. Duty history must follow
# the person, not the account, so accounts are grouped under a person key.
# An unlinked account is its own person: "<platform>:<user_id>".


def create_table_user_links():
    """Accounts grouped into one person, plus the pending invite codes."""
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS UserLinks (
            link_id BIGINT NOT NULL AUTO_INCREMENT,
            person_key VARCHAR(64) NOT NULL,
            user_id BIGINT NOT NULL,
            platform VARCHAR(16) NOT NULL,
            created_at DATETIME NOT NULL,
            PRIMARY KEY (link_id),
            UNIQUE KEY uq_user_account (user_id, platform),
            KEY idx_person_key (person_key)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS UserLinkCodes (
            code_id BIGINT NOT NULL AUTO_INCREMENT,
            link_secret VARCHAR(32) NOT NULL,
            user_id BIGINT NOT NULL,
            platform VARCHAR(16) NOT NULL,
            created_at DATETIME NOT NULL,
            used_at DATETIME DEFAULT NULL,
            PRIMARY KEY (code_id),
            UNIQUE KEY uq_user_link_secret (link_secret),
            KEY idx_code_account (user_id, platform)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')
    conn.commit()
    conn.close()


def get_person_key(user_id: int, platform: str = None) -> str:
    """Identity key spanning this human's accounts. Unlinked accounts get
    their own key, so callers can always group by it."""
    platform = platform or PLATFORM
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT person_key FROM UserLinks WHERE user_id = %s AND platform = %s LIMIT 1;
    ''', (user_id, platform))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else f'{platform}:{user_id}'


def get_person_accounts(person_key: str) -> List[Tuple[int, str]]:
    """Every account belonging to this person: [(user_id, platform), ...]."""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT user_id, platform FROM UserLinks WHERE person_key = %s;
    ''', (person_key,))
    rows = cur.fetchall() or []
    conn.close()
    if rows:
        return [(int(r[0]), r[1]) for r in rows]
    # Unlinked: the key encodes the single account it stands for
    platform, _, raw_id = person_key.partition(':')
    try:
        return [(int(raw_id), platform)]
    except ValueError:
        return []


def create_identity_code(user_id: int, platform: str = None) -> str:
    """Issue a code this person enters in the other messenger to link up."""
    platform = platform or PLATFORM
    conn = reconnect()
    secret = generate_link_secret()
    _exec(conn, '''
        INSERT INTO UserLinkCodes (link_secret, user_id, platform, created_at)
        VALUES (%s, %s, %s, %s)
    ''', (secret, user_id, platform, datetime.datetime.now()))
    conn.commit()
    conn.close()
    return secret


def complete_identity_link(user_id: int, secret: str,
                           platform: str = None) -> Optional[Tuple[int, str]]:
    """Redeem a code, merging both accounts into one person.

    Returns the other (user_id, platform), or None when the code is unknown,
    already used, or would link an account to itself/the same platform."""
    platform = platform or PLATFORM
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT code_id, user_id, platform FROM UserLinkCodes
        WHERE link_secret = %s AND used_at IS NULL LIMIT 1
    ''', (secret.strip().upper(),))
    row = cur.fetchone()
    if not row:
        conn.close()
        return None

    code_id, other_user_id, other_platform = int(row[0]), int(row[1]), row[2]
    if other_platform == platform and other_user_id == user_id:
        conn.close()
        return None

    # Reuse whichever side already has a person key so previously merged
    # accounts stay together; otherwise start a key from the inviting account.
    cur = _exec(conn, '''
        SELECT person_key FROM UserLinks
        WHERE (user_id = %s AND platform = %s) OR (user_id = %s AND platform = %s)
        LIMIT 1
    ''', (other_user_id, other_platform, user_id, platform))
    existing = cur.fetchone()
    person_key = existing[0] if existing else f'{other_platform}:{other_user_id}'

    now = datetime.datetime.now()
    for uid, plat in ((other_user_id, other_platform), (user_id, platform)):
        _exec(conn, '''
            INSERT INTO UserLinks (person_key, user_id, platform, created_at)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE person_key = VALUES(person_key);
        ''', (person_key, uid, plat, now))
    _exec(conn, 'UPDATE UserLinkCodes SET used_at = %s WHERE code_id = %s', (now, code_id))
    conn.commit()
    conn.close()
    return (other_user_id, other_platform)


def unlink_identity(user_id: int, platform: str = None) -> bool:
    """Detach this account from its person, making it its own person again."""
    platform = platform or PLATFORM
    conn = reconnect()
    cur = _exec(conn, 'DELETE FROM UserLinks WHERE user_id = %s AND platform = %s',
                (user_id, platform))
    removed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return removed


def get_linked_identity(user_id: int, platform: str = None) -> List[Tuple[int, str]]:
    """This person's accounts on OTHER platforms (empty when unlinked)."""
    platform = platform or PLATFORM
    key = get_person_key(user_id, platform)
    return [(uid, plat) for uid, plat in get_person_accounts(key)
            if (uid, plat) != (user_id, platform)]


# ==================== Duty roster (дежурный) ====================

# Guests and legioneers are stored under small synthetic user ids; real
# accounts (Telegram/MAX user ids) are far above this threshold.
REAL_USER_ID_MIN = 100


def create_table_duty():
    """Duty roster: who is on duty (and plays for free) at each event."""
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Duty (
            duty_id BIGINT AUTO_INCREMENT PRIMARY KEY,
            event_id BIGINT NOT NULL,
            chat_id BIGINT NOT NULL,
            user_id BIGINT NOT NULL,
            platform VARCHAR(16) NOT NULL DEFAULT 'max',
            duty_date DATETIME NOT NULL,
            assigned_by VARCHAR(16) NOT NULL DEFAULT 'auto',
            UNIQUE KEY uq_duty_event (event_id),
            KEY idx_duty_user (user_id, platform),
            KEY idx_duty_chat (chat_id, platform)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')
    conn.commit()
    conn.close()


def _duty_event_key(chat_id: int) -> Optional[int]:
    """Duty is keyed by the primary event id, so two linked events
    (Telegram + MAX) share one duty instead of picking one each."""
    event_id = get_event_id_by_chat_id(chat_id)
    return get_primary_event_id(event_id) if event_id else None


def _duty_chat_scope(chat_id: int) -> List[int]:
    """Chats whose duty history counts together: this one and its link."""
    chats = [chat_id]
    linked = get_linked_chat(chat_id)
    if linked:
        chats.append(linked[0])
    return chats


def get_event_duty(chat_id: int) -> Optional[Tuple[int, str, str]]:
    """Duty of the chat's open event: (user_id, platform, assigned_by)."""
    key = _duty_event_key(chat_id)
    if not key:
        return None
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT user_id, platform, assigned_by FROM Duty WHERE event_id = %s LIMIT 1;
    ''', (key,))
    row = cur.fetchone()
    conn.close()
    return (int(row[0]), row[1], row[2]) if row else None


def set_event_duty(chat_id: int, user_id: int, platform: str, assigned_by: str = 'auto') -> bool:
    """Assign duty for the chat's open event, replacing any previous one."""
    key = _duty_event_key(chat_id)
    if not key:
        return False
    conn = reconnect()
    _exec(conn, '''
        INSERT INTO Duty (event_id, chat_id, user_id, platform, duty_date, assigned_by)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            chat_id = VALUES(chat_id), user_id = VALUES(user_id),
            platform = VALUES(platform), duty_date = VALUES(duty_date),
            assigned_by = VALUES(assigned_by);
    ''', (key, chat_id, user_id, platform, datetime.datetime.now(), assigned_by))
    conn.commit()
    conn.close()
    return True


def get_duty_count(chat_id: int, user_id: int, platform: str) -> int:
    """Past duties of the PERSON behind this account, in this chat and its
    link. Someone who signed up in MAX last time and in Telegram this time is
    the same person, so both accounts' duties count together."""
    chats = _duty_chat_scope(chat_id)
    accounts = get_person_accounts(get_person_key(user_id, platform))
    if not accounts:
        return 0
    chat_ph = ','.join(['%s'] * len(chats))
    acct_ph = ','.join(['(%s,%s)'] * len(accounts))
    params = list(chats)
    for uid, plat in accounts:
        params += [uid, plat]
    conn = reconnect()
    cur = _exec(conn, f'''
        SELECT COUNT(*) FROM Duty
        WHERE chat_id IN ({chat_ph}) AND (user_id, platform) IN ({acct_ph});
    ''', tuple(params))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else 0


def get_duty_candidates(chat_id: int) -> List[Tuple[int, str, str]]:
    """Real participants of the open event: [(user_id, platform, name)].

    Guests and legioneers never take duty, so they are filtered out. Accounts
    of the same person are collapsed into one candidate, so being signed up on
    both platforms does not double someone's chance of being picked."""
    candidates = []
    seen_persons = set()

    def add(user_id, platform, name):
        if user_id < REAL_USER_ID_MIN:
            return
        key = get_person_key(user_id, platform)
        if key in seen_persons:
            return
        seen_persons.add(key)
        candidates.append((user_id, platform, name))

    # Local accounts first, so a person present on both platforms is mentioned
    # in the chat where the command was typed.
    for user_id in get_event_users(chat_id):
        add(user_id, PLATFORM, compose_full_name(user_id))
    event_id = get_event_id_by_chat_id(chat_id)
    if event_id:
        for user_id, platform, name in get_linked_event_users(event_id):
            add(user_id, platform, name)
    return candidates


def choose_duty(chat_id: int) -> Optional[Tuple[int, str, str]]:
    """Pick the next duty: fewest past duties, ties broken at random."""
    candidates = get_duty_candidates(chat_id)
    if not candidates:
        return None
    counted = [
        (get_duty_count(chat_id, user_id, platform), user_id, platform, name)
        for user_id, platform, name in candidates
    ]
    fewest = min(row[0] for row in counted)
    pool = [(uid, plat, name) for count, uid, plat, name in counted if count == fewest]
    return random.choice(pool)


def is_same_person(user_id_1: int, platform_1: str, user_id_2: int, platform_2: str) -> bool:
    """Whether two accounts belong to the same human."""
    if (user_id_1, platform_1) == (user_id_2, platform_2):
        return True
    return get_person_key(user_id_1, platform_1) == get_person_key(user_id_2, platform_2)


def get_duty_display_name(user_id: int, platform: str) -> str:
    """Display name for a duty user on either platform."""
    if platform == PLATFORM:
        return compose_full_name(user_id)
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT first_name, last_name, username FROM Users
        WHERE user_id = %s AND platform = %s LIMIT 1;
    ''', (user_id, platform))
    row = cur.fetchone()
    conn.close()
    if not row:
        return str(user_id)
    name = " ".join([row[0] or '', row[1] or '']).strip()
    return name or (row[2] or str(user_id))


def get_duty_stats(chat_id: int) -> List[Tuple[int, str, str, int]]:
    """Duty tally for this chat: [(user_id, platform, name, count)], busiest
    first. Tallied per person, so someone's MAX and Telegram duties add up
    into a single row."""
    chats = _duty_chat_scope(chat_id)
    placeholders = ','.join(['%s'] * len(chats))
    conn = reconnect()
    cur = _exec(conn, f'''
        SELECT user_id, platform, COUNT(*) AS cnt FROM Duty
        WHERE chat_id IN ({placeholders})
        GROUP BY user_id, platform;
    ''', tuple(chats))
    rows = cur.fetchall() or []
    conn.close()

    totals = {}
    for raw_uid, plat, cnt in rows:
        uid = int(raw_uid)
        key = get_person_key(uid, plat)
        entry = totals.get(key)
        if entry is None:
            totals[key] = [uid, plat, int(cnt)]
        else:
            entry[2] += int(cnt)
            # Prefer showing the account on this bot's own platform
            if entry[1] != PLATFORM and plat == PLATFORM:
                entry[0], entry[1] = uid, plat
    result = [
        (uid, plat, get_duty_display_name(uid, plat), count)
        for uid, plat, count in totals.values()
    ]
    result.sort(key=lambda r: r[3], reverse=True)
    return result


def _column_type(conn, table: str, column: str) -> Optional[str]:
    """Actual SQL type of a column, or None when it does not exist."""
    try:
        cur = _exec(conn, '''
            SELECT COLUMN_TYPE FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
        ''', (table, column))
        row = cur.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.warning(f"Could not read type of {table}.{column}: {e}")
        return None


def migrate_schema():
    """Add new columns to existing tables if they don't exist yet."""
    conn = reconnect()
    migrations = [
        ('Participants', 'paid_at', 'DATETIME DEFAULT NULL'),
        ('Participants', 'invited_by', 'BIGINT DEFAULT NULL'),
        ('Events', 'payment_url', 'TEXT DEFAULT NULL'),
        ('Events', 'telegraph_url', 'TEXT DEFAULT NULL'),
        # Platform support migrations
        ('Users', 'platform', "VARCHAR(16) NOT NULL DEFAULT 'max'"),
        ('Chats', 'platform', "VARCHAR(16) NOT NULL DEFAULT 'max'"),
        ('Events', 'platform', "VARCHAR(16) NOT NULL DEFAULT 'max'"),
        ('Penalties', 'platform', "VARCHAR(16) NOT NULL DEFAULT 'max'"),
    ]
    for table, col, definition in migrations:
        try:
            _exec(conn, f'ALTER TABLE {table} ADD COLUMN {col} {definition}')
            logger.info(f"Migration: added {table}.{col}")
        except Exception as e:
            # "Duplicate column name" simply means the migration already ran
            if 'duplicate column' not in str(e).lower():
                logger.warning(f"Migration: could not add {table}.{col}: {e}")

    # Type change migrations (BIGINT -> VARCHAR for string message IDs).
    # This one matters: MAX message ids look like "mid.abc123", and a numeric
    # column stores them as 0, so every later edit of that message fails.
    type_changes = [
        ('Chats', 'latest_bot_message_id', 'VARCHAR(64)'),
    ]
    for table, col, new_type in type_changes:
        current = _column_type(conn, table, col)
        if current is None:
            continue
        if new_type.split('(')[0].lower() in current.lower():
            continue  # already the right type
        try:
            _exec(conn, f'ALTER TABLE {table} MODIFY COLUMN {col} {new_type}')
            conn.commit()
            logger.info(f"Migration: {table}.{col} changed from {current} to {new_type}")
        except Exception as e:
            logger.error(
                f"Migration FAILED: {table}.{col} is {current} but must be {new_type}: {e}. "
                f"String message ids are stored as 0 in a numeric column, so the bot "
                f"cannot edit its own announcements. Fix it by hand with: "
                f"ALTER TABLE {table} MODIFY COLUMN {col} {new_type};"
            )
    conn.close()

def init_database():
    """Create all tables and run schema migrations."""
    logger.info(
        f"Database: {MYSQL_CFG['database']} on {MYSQL_CFG['host']} "
        f"as {MYSQL_CFG['user']} (platform={PLATFORM})"
    )
    create_table_users()
    create_table_chats()
    create_table_events()
    create_table_participants()
    create_table_revoked()
    create_table_chat_penalties()
    create_table_payment_log()
    create_table_chat_links()
    create_table_event_links()
    create_table_duty()
    create_table_user_links()
    migrate_schema()

def record_payment_log(chat_id: int, payer_user_id: int, for_friend: bool = False):
    """Append a payment event to PaymentLog for the active event."""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT event_id FROM Events WHERE status = "Open" AND chat_id = %s AND platform = %s ORDER BY event_id DESC LIMIT 1
    ''', (chat_id, PLATFORM))
    row = cur.fetchone()
    if not row:
        conn.close()
        return
    event_id = row[0]
    _exec(conn, '''
        INSERT INTO PaymentLog (event_id, payer_user_id, paid_at, for_friend)
        VALUES (%s, %s, %s, %s)
    ''', (event_id, payer_user_id, datetime.datetime.now(), 1 if for_friend else 0))
    conn.commit()
    conn.close()

def get_payment_log(chat_id: int) -> List[Tuple]:
    """Return [(display_name, paid_at, for_friend), ...] ordered by time."""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT u.first_name, u.last_name, u.username, pl.paid_at, pl.for_friend
        FROM PaymentLog pl
        LEFT JOIN Users u ON pl.payer_user_id = u.user_id AND u.platform = %s
        WHERE pl.event_id = (
            SELECT event_id FROM Events WHERE status = "Open" AND chat_id = %s AND platform = %s ORDER BY event_id DESC LIMIT 1
        )
        ORDER BY pl.paid_at
    ''', (PLATFORM, chat_id, PLATFORM))
    rows = cur.fetchall()
    conn.close()
    result = []
    for r in rows:
        fnm = r[0] or ''
        lnm = r[1] or ''
        unm = r[2] or ''
        name = " ".join([fnm, lnm]).strip()
        if name and unm:
            name = f"{name} ({unm})"
        elif not name and unm:
            name = unm
        elif not name:
            name = "Unknown"
        result.append((name, r[3], bool(r[4])))
    return result

def has_user_invited_legioneer(chat_id: int, user_id: int) -> bool:
    """Check if user has invited any legioneer to the active event."""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT COUNT(*)
        FROM Participants
        WHERE event_id = (
            SELECT event_id FROM Events WHERE status = "Open" AND chat_id = %s AND platform = %s ORDER BY event_id DESC LIMIT 1
        )
        AND user_id BETWEEN 31 AND 49
        AND invited_by = %s
    ''', (chat_id, PLATFORM, user_id))
    row = cur.fetchone()
    conn.close()
    return bool(row and row[0] > 0)


def get_unpaid_legioneer(chat_id: int, user_id: int) -> Optional[int]:
    """Get first unpaid legioneer invited by user. Returns legioneer user_id or None."""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT p.user_id
        FROM Participants p
        WHERE p.event_id = (
            SELECT event_id FROM Events WHERE status = "Open" AND chat_id = %s AND platform = %s ORDER BY event_id DESC LIMIT 1
        )
        AND p.user_id BETWEEN 31 AND 49
        AND p.invited_by = %s
        AND p.paid = FALSE
        ORDER BY p.user_id ASC
        LIMIT 1
    ''', (chat_id, PLATFORM, user_id))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def process_payment(chat_id: int, user_id: int) -> dict:
    """
    Handle PAY button press. Returns dict with 'message' and 'success' keys.
    First press -> payment for self. Subsequent presses -> for unpaid legioneer.
    """
    if user_id not in (get_event_users(chat_id) or []):
        return {'message': 'You must be registered for the event to confirm payment.', 'success': False}

    # The duty player plays for free, so their press must not be spent on
    # themselves — it goes straight to a guest they brought.
    on_duty = False
    duty = get_event_duty(chat_id)
    if duty:
        on_duty = is_same_person(duty[0], duty[1], user_id, PLATFORM)

    already_paid = get_payment_status(chat_id, user_id)
    if not already_paid and not on_duty:
        set_payment_status(chat_id, user_id, True)
        record_payment_log(chat_id, user_id, for_friend=False)
        return {'message': 'Payment confirmed!', 'success': True}

    # Check for unpaid legioneer invited by this user
    legioneer_id = get_unpaid_legioneer(chat_id, user_id)
    if legioneer_id:
        set_payment_status(chat_id, legioneer_id, True)
        record_payment_log(chat_id, user_id, for_friend=True)
        return {'message': 'Payment for friend confirmed!', 'success': True}

    if on_duty and not already_paid:
        return {'message': 'You are on duty — you play for free.', 'success': False}
    return {'message': 'Payment already confirmed.', 'success': False}

if __name__ == '__main__':
    try:
        print('Creating tables in MySQL database...')
        init_database()
        print('Done.')
    except Error as e:
        print(f'Error: {e}')
        sys.exit(1)
