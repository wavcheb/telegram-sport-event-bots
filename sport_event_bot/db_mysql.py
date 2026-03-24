# -*- coding: utf-8 -*-
"""This module works with MySQL database with 5 tables: Users, Chats, Events, Participants, Revoked, Penalties
Updated to support payment status for participants. Migrated from sqlite3 to MySQL.
"""

import os
import sys
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
PLATFORM = 'telegram'

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

logger.remove()
logger.add("logs.log", level="DEBUG")
logger.add(sys.stderr, level="DEBUG")

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
            platform VARCHAR(16) NOT NULL DEFAULT 'telegram',
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
    # Insert legioneer users for this platform
    rows = [(uid, PLATFORM, 'Legioneer') for uid in range(10, 30)]
    _exec_many(conn, '''INSERT IGNORE INTO Users (user_id, platform, first_name) VALUES (%s, %s, %s);''', rows)
    conn.commit()
    conn.close()

def create_table_chats():
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Chats (
            chat_id BIGINT NOT NULL,
            platform VARCHAR(16) NOT NULL DEFAULT 'telegram',
            lang VARCHAR(8),
            priority_members TEXT,
            latest_event_id BIGINT DEFAULT 0,
            latest_bot_message_id VARCHAR(64) DEFAULT '',
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
            platform VARCHAR(16) NOT NULL DEFAULT 'telegram',
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
            platform VARCHAR(16) NOT NULL DEFAULT 'telegram',
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

def get_latest_bot_message_id(chat_id) -> int:
    conn = reconnect()
    cur = _exec(conn, '''SELECT latest_bot_message_id FROM Chats WHERE chat_id = %s AND platform = %s LIMIT 1;''', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    # Handle VARCHAR column: empty string or None -> 0
    if row and row[0]:
        try:
            return int(row[0])
        except (ValueError, TypeError):
            return 0
    return 0

def get_latest_bot_message_text(chat_id) -> str:
    conn = reconnect()
    cur = _exec(conn, '''SELECT latest_bot_message_text FROM Chats WHERE chat_id = %s AND platform = %s LIMIT 1;''', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else ""

def save_latest_bot_message(chat_id, message_id, message_text):
    conn = reconnect()
    _exec(conn, '''UPDATE Chats SET latest_bot_message_id = %s, latest_bot_message_text = %s WHERE chat_id = %s AND platform = %s;''',
          (message_id, message_text, chat_id, PLATFORM))
    conn.commit()
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
    language_code = lang or ''
    conn = reconnect()
    _exec(conn, 'INSERT IGNORE INTO Chats(chat_id, platform, lang) VALUES (%s, %s, %s)', (chat_id, PLATFORM, language_code))
    conn.commit()
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
    conn = reconnect()
    cur = _exec(conn, 'SELECT COUNT(user_id) FROM Participants WHERE event_id = %s AND user_id < 29;', (event_id,))
    count = cur.fetchone()
    conn.close()
    if count is not None:
        return int(count[0]) + 10
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
    logger.info(f"Event - Legioneer-player canceled request for chat: {chat_id}")
    conn = reconnect()
    event_id = get_event_id_by_chat_id(chat_id)
    user_id = get_legioneer_user(event_id) - 1
    if user_id > 9:
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


def get_linked_chat_message_info(chat_id: int) -> Optional[Tuple[int, str, str]]:
    """Get linked chat's message info for cross-platform sync.
    Returns (linked_chat_id, linked_platform, linked_message_id) or None.
    Note: message_id is string (MAX uses 'mid.xxx', TG uses numeric strings)."""
    linked = get_linked_chat(chat_id)
    if not linked:
        return None
    linked_chat_id, linked_platform = linked
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT latest_bot_message_id FROM Chats
        WHERE chat_id = %s AND platform = %s LIMIT 1
    ''', (linked_chat_id, linked_platform))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return (linked_chat_id, linked_platform, str(row[0]))
    return None


def get_primary_event_id(event_id: int) -> int:
    """Get the primary (original) event ID. If this is a copied event, returns the original.
    Otherwise returns the same event_id."""
    conn = reconnect()
    # If this event is event_id_2 (copy), return event_id_1 (original)
    cur = _exec(conn, 'SELECT event_id_1 FROM EventLinks WHERE event_id_2 = %s LIMIT 1', (event_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else event_id


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


def get_event_from_linked_chat(linked_chat_id: int, linked_platform: str) -> Optional[Tuple[int, str, str, int]]:
    """Get open event from linked chat. Returns (event_id, description, datetime, players_limit) or None."""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT event_id, description, datetime, players_limit FROM Events
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

def migrate_schema():
    """Add new columns to existing tables if they don't exist yet."""
    conn = reconnect()
    migrations = [
        ('Participants', 'paid_at', 'DATETIME DEFAULT NULL'),
        ('Participants', 'invited_by', 'BIGINT DEFAULT NULL'),
        ('Events', 'payment_url', 'TEXT DEFAULT NULL'),
        ('Events', 'telegraph_url', 'TEXT DEFAULT NULL'),
        # Platform support migrations
        ('Users', 'platform', "VARCHAR(16) NOT NULL DEFAULT 'telegram'"),
        ('Chats', 'platform', "VARCHAR(16) NOT NULL DEFAULT 'telegram'"),
        ('Events', 'platform', "VARCHAR(16) NOT NULL DEFAULT 'telegram'"),
        ('Penalties', 'platform', "VARCHAR(16) NOT NULL DEFAULT 'telegram'"),
    ]
    for table, col, definition in migrations:
        try:
            _exec(conn, f'ALTER TABLE {table} ADD COLUMN {col} {definition}')
        except Exception:
            pass  # column already exists
    conn.close()

def init_database():
    """Create all tables and run schema migrations."""
    create_table_users()
    create_table_chats()
    create_table_events()
    create_table_participants()
    create_table_revoked()
    create_table_chat_penalties()
    create_table_payment_log()
    create_table_chat_links()
    create_table_event_links()
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
        AND user_id < 30
        AND invited_by = %s
    ''', (chat_id, PLATFORM, user_id))
    row = cur.fetchone()
    conn.close()
    return bool(row and row[0] > 0)

def process_payment(chat_id: int, user_id: int) -> dict:
    """
    Handle PAY button press. Returns dict with 'message' and 'success' keys.
    First press -> payment for self. Subsequent presses (if user has legioneer) -> for friend.
    """
    if user_id not in (get_event_users(chat_id) or []):
        return {'message': 'You must be registered for the event to confirm payment.', 'success': False}

    already_paid = get_payment_status(chat_id, user_id)
    if not already_paid:
        set_payment_status(chat_id, user_id, True)
        record_payment_log(chat_id, user_id, for_friend=False)
        return {'message': 'Payment confirmed!', 'success': True}

    if has_user_invited_legioneer(chat_id, user_id):
        record_payment_log(chat_id, user_id, for_friend=True)
        return {'message': 'Payment for friend confirmed!', 'success': True}

    return {'message': 'Payment already confirmed.', 'success': False}

if __name__ == '__main__':
    try:
        print('Creating tables in MySQL database...')
        init_database()
        print('Done.')
    except Error as e:
        print(f'Error: {e}')
        sys.exit(1)
