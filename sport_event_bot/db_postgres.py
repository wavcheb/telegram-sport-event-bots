# -*- coding: utf-8 -*-
"""This module works with PostgreSQL database.
Adapted from the original MySQL implementation for the tg-sport-event-bot.
"""

import os
import sys
import datetime
from typing import List, Optional, Set, Tuple
from loguru import logger
import psycopg2
from psycopg2 import sql, extras
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Fixed platform for this bot
PLATFORM = 'telegram'

# Connection settings from environment (compatible with Neon)
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_NAME = os.getenv('DB_NAME', 'neondb')
DB_USER = os.getenv('DB_USER', 'neondb_owner')
DB_PASS = os.getenv('DB_PASS', '')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_SSLMODE = os.getenv('DB_SSLMODE', 'require')

logger.remove()
logger.add("logs.log", level="DEBUG")
logger.add(sys.stderr, level="DEBUG")

def reconnect():
    """Open a new PostgreSQL connection"""
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT,
        sslmode=DB_SSLMODE
    )
    conn.autocommit = True
    return conn

def _exec(conn, query, params=None):
    cur = conn.cursor()
    cur.execute(query, params or ())
    return cur

def _exec_many(conn, query, seq_of_params):
    cur = conn.cursor()
    extras.execute_values(cur, query, seq_of_params)
    return cur

def create_table_users():
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Users (
            user_id BIGINT NOT NULL,
            platform VARCHAR(16) NOT NULL DEFAULT 'telegram',
            first_name VARCHAR(255) DEFAULT '',
            last_name  VARCHAR(255) DEFAULT '',
            username   VARCHAR(255) DEFAULT '',
            birth_date VARCHAR(32)  DEFAULT '',
            phone      VARCHAR(64)  DEFAULT '',
            facebook   VARCHAR(255) DEFAULT '',
            extra      TEXT,
            PRIMARY KEY (user_id, platform)
        );
    ''')
    
    # Insert legioneer users for this platform
    rows = [(uid, PLATFORM, 'Legioneer') for uid in range(10, 30)]
    # Postgres specific INSERT ... ON CONFLICT
    query = "INSERT INTO Users (user_id, platform, first_name) VALUES %s ON CONFLICT (user_id, platform) DO NOTHING"
    _exec_many(conn, query, rows)
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
        );
    ''')
    conn.close()

def create_table_events():
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Events (
            event_id SERIAL PRIMARY KEY,
            chat_id BIGINT,
            platform VARCHAR(16) NOT NULL DEFAULT 'telegram',
            status VARCHAR(32) DEFAULT 'Open',
            description TEXT,
            datetime VARCHAR(64) DEFAULT '',
            players_limit INT DEFAULT 0,
            payment_url TEXT DEFAULT NULL,
            telegraph_url TEXT DEFAULT NULL,
            extra1 TEXT,
            extra2 TEXT,
            extra3 TEXT,
            CONSTRAINT fk_events_chat
              FOREIGN KEY (chat_id, platform) REFERENCES Chats(chat_id, platform)
              ON DELETE SET NULL ON UPDATE CASCADE
        );
    ''')
    _exec(conn, 'CREATE INDEX IF NOT EXISTS idx_events_chat_platform ON Events (chat_id, platform);')
    conn.close()

def create_table_participants():
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Participants (
            event_id BIGINT NOT NULL,
            user_id BIGINT,
            operation_datetime TIMESTAMP NOT NULL,
            paid BOOLEAN DEFAULT FALSE,
            paid_at TIMESTAMP DEFAULT NULL,
            invited_by BIGINT DEFAULT NULL,
            UNIQUE (event_id, user_id),
            CONSTRAINT fk_part_event
              FOREIGN KEY (event_id) REFERENCES Events(event_id)
              ON DELETE CASCADE ON UPDATE CASCADE
        );
    ''')
    _exec(conn, 'CREATE INDEX IF NOT EXISTS idx_participants_event ON Participants (event_id);')
    conn.close()

def create_table_revoked():
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Revoked (
            event_id BIGINT NOT NULL,
            user_id BIGINT,
            operation_datetime TIMESTAMP NOT NULL,
            UNIQUE (event_id, user_id),
            CONSTRAINT fk_rev_event
              FOREIGN KEY (event_id) REFERENCES Events(event_id)
              ON DELETE CASCADE ON UPDATE CASCADE
        );
    ''')
    _exec(conn, 'CREATE INDEX IF NOT EXISTS idx_revoked_event ON Revoked (event_id);')
    conn.close()

def create_table_chat_penalties():
    conn = reconnect()
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Penalties (
            chat_id BIGINT,
            platform VARCHAR(16) NOT NULL DEFAULT 'telegram',
            user_id BIGINT,
            operation_datetime TIMESTAMP NOT NULL,
            operator_id BIGINT,
            CONSTRAINT fk_pen_chat
              FOREIGN KEY (chat_id, platform) REFERENCES Chats(chat_id, platform)
              ON DELETE CASCADE ON UPDATE CASCADE,
            CONSTRAINT fk_pen_user
              FOREIGN KEY (user_id, platform) REFERENCES Users(user_id, platform)
              ON DELETE CASCADE ON UPDATE CASCADE,
            CONSTRAINT fk_pen_operator
              FOREIGN KEY (operator_id, platform) REFERENCES Users(user_id, platform)
              ON DELETE CASCADE ON UPDATE CASCADE
        );
    ''')
    _exec(conn, 'CREATE INDEX IF NOT EXISTS idx_pen_chat_platform ON Penalties (chat_id, platform);')
    _exec(conn, 'CREATE INDEX IF NOT EXISTS idx_pen_user_platform ON Penalties (user_id, platform);')
    conn.close()

def init_database():
    """Initialize all tables"""
    create_table_users()
    create_table_chats()
    create_table_events()
    create_table_participants()
    create_table_revoked()
    create_table_chat_penalties()

# --- Data Operations ---

def close_all_open_events_for_chat(chat_id: int):
    conn = reconnect()
    _exec(conn, 'UPDATE Events SET status = %s WHERE chat_id = %s AND platform = %s AND status = %s;', ('Closed', chat_id, PLATFORM, 'Open'))
    conn.close()

def event_add(chat_id: int, text: str, dtm: datetime.datetime, players_limit: int, latest_bot_message_id: int, latest_bot_message_text: str):
    event_datetime = dtm if dtm else datetime.datetime.now()
    conn = reconnect()
    cur = _exec(conn, '''INSERT INTO Events (chat_id, platform, description, datetime, players_limit) 
                        VALUES (%s, %s, %s, %s, %s) RETURNING event_id;''',
                (chat_id, PLATFORM, text, str(event_datetime), players_limit))
    event_id = cur.fetchone()[0]
    _exec(conn, '''UPDATE Chats SET latest_event_id = %s, latest_bot_message_id = %s, latest_bot_message_text = %s 
                  WHERE chat_id = %s AND platform = %s;''',
          (event_id, str(latest_bot_message_id), latest_bot_message_text, chat_id, PLATFORM))
    conn.close()

def update_event_text(chat_id, new_text):
    conn = reconnect()
    _exec(conn, 'UPDATE Events SET description = %s WHERE status = %s AND chat_id = %s AND platform = %s;', (new_text, 'Open', chat_id, PLATFORM))
    conn.close()

def get_event_text(chat_id) -> str:
    conn = reconnect()
    cur = _exec(conn, 'SELECT description FROM Events WHERE status=%s AND chat_id = %s AND platform = %s LIMIT 1;', ('Open', chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else ''

def set_players_limit(chat_id, players_limit: int):
    conn = reconnect()
    _exec(conn, 'UPDATE Events SET players_limit = %s WHERE status = %s AND chat_id = %s AND platform = %s;', (players_limit, 'Open', chat_id, PLATFORM))
    conn.close()

def get_event_limit(chat_id) -> int:
    conn = reconnect()
    cur = _exec(conn, 'SELECT players_limit FROM Events WHERE status=%s AND chat_id = %s AND platform = %s LIMIT 1;', ('Open', chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row and row[0] is not None else 0

def set_event_datetime(chat_id: int, dtm: datetime.datetime):
    conn = reconnect()
    _exec(conn, 'UPDATE Events SET datetime = %s WHERE status = %s AND chat_id = %s AND platform = %s;', (str(dtm), 'Open', chat_id, PLATFORM))
    conn.close()

def get_event_datetime(chat_id: int) -> str:
    conn = reconnect()
    cur = _exec(conn, 'SELECT datetime FROM Events WHERE status=%s AND chat_id = %s AND platform = %s LIMIT 1;', ('Open', chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else ''

def get_event_payment_url(chat_id: int) -> Optional[str]:
    conn = reconnect()
    cur = _exec(conn, 'SELECT payment_url FROM Events WHERE status=%s AND chat_id = %s AND platform = %s LIMIT 1;', ('Open', chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else None

def set_event_payment_url(chat_id: int, url: Optional[str]):
    conn = reconnect()
    _exec(conn, 'UPDATE Events SET payment_url = %s WHERE status = %s AND chat_id = %s AND platform = %s;', (url, 'Open', chat_id, PLATFORM))
    conn.close()

def get_event_telegraph_url(chat_id: int) -> Optional[str]:
    conn = reconnect()
    cur = _exec(conn, 'SELECT telegraph_url FROM Events WHERE status=%s AND chat_id = %s AND platform = %s LIMIT 1;', ('Open', chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] else None

def set_event_telegraph_url(chat_id: int, url: Optional[str]):
    conn = reconnect()
    _exec(conn, 'UPDATE Events SET telegraph_url = %s WHERE status = %s AND chat_id = %s AND platform = %s;', (url, 'Open', chat_id, PLATFORM))
    conn.close()

def fix_event(chat_id):
    conn = reconnect()
    _exec(conn, 'UPDATE Events SET status = %s WHERE status = %s AND chat_id = %s AND platform = %s;', ('Fixed', 'Open', chat_id, PLATFORM))
    conn.close()

def get_latest_bot_message_id(chat_id) -> int:
    conn = reconnect()
    cur = _exec(conn, 'SELECT latest_bot_message_id FROM Chats WHERE chat_id = %s AND platform = %s LIMIT 1;', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        try:
            return int(row[0])
        except (ValueError, TypeError):
            return 0
    return 0

def get_latest_bot_message_text(chat_id) -> str:
    conn = reconnect()
    cur = _exec(conn, 'SELECT latest_bot_message_text FROM Chats WHERE chat_id = %s AND platform = %s LIMIT 1;', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    return row[0] if row and row[0] is not None else ""

def save_latest_bot_message(chat_id, message_id, message_text):
    conn = reconnect()
    _exec(conn, 'UPDATE Chats SET latest_bot_message_id = %s, latest_bot_message_text = %s WHERE chat_id = %s AND platform = %s;',
          (str(message_id), message_text, chat_id, PLATFORM))
    conn.close()

def add_or_update_user(user_id, first_name='', last_name='', username=''):
    conn = reconnect()
    query = '''
        INSERT INTO Users (user_id, platform, first_name, last_name, username)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (user_id, platform)
        DO UPDATE SET first_name = EXCLUDED.first_name, last_name = EXCLUDED.last_name, username = EXCLUDED.username;
    '''
    _exec(conn, query, (user_id, PLATFORM, first_name or '', last_name or '', username or ''))
    conn.close()

def compose_full_name(user_id: int) -> str:
    conn = reconnect()
    cur = _exec(conn, 'SELECT first_name, last_name, username FROM Users WHERE user_id = %s AND platform = %s;', (user_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    if not row:
        return str(user_id)
    fnm, lnm, unm = (row[0] or ''), (row[1] or ''), (row[2] or '')
    res = " ".join([fnm, lnm]).strip()
    if res and unm:
        res = f"{res} ({unm})"
    return res or unm or str(user_id)

def penalty_for_user_in_chat(chat_id, user_id, operator_id: int):
    conn = reconnect()
    _exec(conn, 'INSERT INTO Penalties(chat_id, platform, user_id, operation_datetime, operator_id) VALUES (%s, %s, %s, %s, %s);',
          (chat_id, PLATFORM, user_id, datetime.datetime.now(), operator_id))
    conn.close()

def get_all_userids() -> List[int]:
    conn = reconnect()
    cur = _exec(conn, 'SELECT user_id FROM Users WHERE platform = %s;', (PLATFORM,))
    rows = cur.fetchall()
    conn.close()
    return [int(row[0]) for row in rows]

def get_all_chat_ids() -> Set[int]:
    conn = reconnect()
    cur = _exec(conn, 'SELECT chat_id FROM Chats WHERE platform = %s;', (PLATFORM,))
    rows = cur.fetchall()
    conn.close()
    return set(int(row[0]) for row in rows)

def register_new_chat_id(chat_id: int, lang: str):
    conn = reconnect()
    query = 'INSERT INTO Chats(chat_id, platform, lang) VALUES (%s, %s, %s) ON CONFLICT (chat_id, platform) DO NOTHING;'
    _exec(conn, query, (chat_id, PLATFORM, lang or ''))
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
    return row[0] if row and row[0] else 'en'

def set_chat_lang(chat_id: int, lang: str):
    conn = reconnect()
    _exec(conn, 'UPDATE Chats SET lang = %s WHERE chat_id = %s AND platform = %s;', (lang, chat_id, PLATFORM))
    conn.close()

def get_event_users(chat_id: int) -> List[int]:
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT p.user_id
        FROM Participants p
        WHERE p.event_id = (SELECT e.event_id FROM Events e WHERE e.status = 'Open' AND e.chat_id = %s AND e.platform = %s LIMIT 1)
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
        WHERE r.event_id = (SELECT e.event_id FROM Events e WHERE e.status = 'Open' AND e.chat_id = %s AND e.platform = %s LIMIT 1)
        ORDER BY r.operation_datetime;
    ''', (chat_id, PLATFORM))
    rows = cur.fetchall()
    conn.close()
    return [int(r[0]) for r in rows] if rows else []

def apply_for_participation_in_the_event(chat_id: int, user_id: int):
    conn = reconnect()
    cur = _exec(conn, "SELECT event_id FROM Events WHERE status = 'Open' AND chat_id = %s AND platform = %s LIMIT 1;", (chat_id, PLATFORM))
    event = cur.fetchone()
    if not event:
        conn.close()
        return
    event_id = event[0]
    dtm = datetime.datetime.now()
    _exec(conn, '''
        INSERT INTO Participants (event_id, user_id, operation_datetime, paid)
        VALUES (%s, %s, %s, FALSE)
        ON CONFLICT (event_id, user_id) DO UPDATE SET operation_datetime = EXCLUDED.operation_datetime;
    ''', (event_id, user_id, dtm))
    _exec(conn, 'DELETE FROM Revoked WHERE event_id = %s AND user_id = %s;', (event_id, user_id))
    conn.close()

def revoke_application_for_the_event(chat_id: int, user_id: int):
    conn = reconnect()
    cur = _exec(conn, "SELECT event_id FROM Events WHERE status = 'Open' AND chat_id = %s AND platform = %s LIMIT 1;", (chat_id, PLATFORM))
    event = cur.fetchone()
    if not event:
        conn.close()
        return
    event_id = event[0]
    dtm = datetime.datetime.now()
    _exec(conn, '''
        INSERT INTO Revoked (event_id, user_id, operation_datetime)
        VALUES (%s, %s, %s)
        ON CONFLICT (event_id, user_id) DO UPDATE SET operation_datetime = EXCLUDED.operation_datetime;
    ''', (event_id, user_id, dtm))
    _exec(conn, 'DELETE FROM Participants WHERE event_id = %s AND user_id = %s;', (event_id, user_id))
    conn.close()

def get_event_id_by_chat_id(chat_id):
    conn = reconnect()
    cur = _exec(conn, 'SELECT MAX(event_id) FROM Events WHERE chat_id = %s AND platform = %s;', (chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return int(row[0])
    return None

def get_legioneer_user(event_id: int):
    conn = reconnect()
    cur = _exec(conn, 'SELECT COUNT(user_id) FROM Participants WHERE event_id = %s AND user_id < 29;', (event_id,))
    count = cur.fetchone()
    conn.close()
    return int(count[0]) + 10 if count else 10

def apply_for_legioneer(chat_id, invited_by_user_id=None):
    conn = reconnect()
    event_id = get_event_id_by_chat_id(chat_id)
    if not event_id:
        conn.close()
        return
    user_id = get_legioneer_user(event_id)
    dtm = datetime.datetime.now()
    _exec(conn, '''
        INSERT INTO Participants (event_id, user_id, operation_datetime, paid, invited_by)
        VALUES (%s, %s, %s, FALSE, %s)
        ON CONFLICT (event_id, user_id) DO UPDATE SET operation_datetime = EXCLUDED.operation_datetime, invited_by = EXCLUDED.invited_by;
    ''', (event_id, user_id, dtm, invited_by_user_id))
    _exec(conn, 'DELETE FROM Revoked WHERE event_id = %s AND user_id = %s;', (event_id, user_id))
    conn.close()

def revoke_for_legioneer(chat_id):
    conn = reconnect()
    event_id = get_event_id_by_chat_id(chat_id)
    if not event_id:
        conn.close()
        return
    user_id = get_legioneer_user(event_id) - 1
    if user_id > 9:
        dtm = datetime.datetime.now()
        _exec(conn, 'DELETE FROM Participants WHERE event_id = %s AND user_id = %s;', (event_id, user_id))
        _exec(conn, '''
            INSERT INTO Revoked (event_id, user_id, operation_datetime)
            VALUES (%s, %s, %s)
            ON CONFLICT (event_id, user_id) DO UPDATE SET operation_datetime = EXCLUDED.operation_datetime;
        ''', (event_id, user_id, dtm))
    conn.close()

def get_chat_user_rp(chat_id, user_id: int) -> Tuple[int, int]:
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT COUNT(*) FROM Participants p
        WHERE p.event_id IN (SELECT e.event_id FROM Events e WHERE e.status = 'Fixed' AND e.chat_id = %s AND e.platform = %s)
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
        SELECT r.operation_datetime FROM Revoked r
        WHERE r.event_id = (SELECT e.event_id FROM Events e WHERE e.status = 'Open' AND e.chat_id = %s AND e.platform = %s LIMIT 1)
        AND r.user_id = %s LIMIT 1;
    ''', (chat_id, PLATFORM, canceled_user_id))
    row = cur.fetchone()
    conn.close()
    if not row:
        return 'N/A'
    return row[0].strftime('%Y-%m-%d %H:%M:%S') if isinstance(row[0], datetime.datetime) else str(row[0])

def set_payment_status(chat_id: int, user_id: int, paid: bool = True):
    conn = reconnect()
    paid_at = datetime.datetime.now() if paid else None
    _exec(conn, '''
        UPDATE Participants SET paid = %s, paid_at = %s
        WHERE user_id = %s AND event_id = (
            SELECT event_id FROM Events WHERE status = 'Open' AND chat_id = %s AND platform = %s LIMIT 1
        );
    ''', (paid, paid_at, user_id, chat_id, PLATFORM))
    conn.close()

def get_payment_status(chat_id: int, user_id: int) -> bool:
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT p.paid FROM Participants p
        WHERE p.user_id = %s AND p.event_id = (
            SELECT event_id FROM Events WHERE status = 'Open' AND chat_id = %s AND platform = %s LIMIT 1
        );
    ''', (user_id, chat_id, PLATFORM))
    row = cur.fetchone()
    conn.close()
    return bool(row[0]) if row else False

def process_payment(chat_id: int, user_id: int) -> dict:
    """Toggle payment status and return result message"""
    current_status = get_payment_status(chat_id, user_id)
    new_status = not current_status
    set_payment_status(chat_id, user_id, new_status)
    msg = 'Payment confirmed' if new_status else 'Payment revoked'
    return {'success': True, 'message': msg}
