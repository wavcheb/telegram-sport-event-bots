# -*- coding: utf-8 -*-
"""
Database module for Tournament Bot
Manages tournaments, teams, matches, and standings
"""

import os
import sys
import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from loguru import logger
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / '.env')

# Connection settings from environment
# Tournament bot can use its own DB settings or share with sport_event_bot
MYSQL_CFG = {
    'host': os.getenv('TOURNAMENT_MYSQL_HOST') or os.getenv('MYSQL_HOST', 'localhost'),
    'database': os.getenv('TOURNAMENT_MYSQL_DATABASE') or os.getenv('MYSQL_DATABASE', 'tournament_bot'),
    'user': os.getenv('TOURNAMENT_MYSQL_USER') or os.getenv('MYSQL_USER', 'tournament_bot'),
    'password': os.getenv('TOURNAMENT_MYSQL_PASSWORD') or os.getenv('MYSQL_PASSWORD', ''),
    'charset': 'utf8mb4',
    'collation': 'utf8mb4_unicode_ci',
}

def reconnect():
    """Establish connection to MySQL database"""
    try:
        conn = mysql.connector.connect(**MYSQL_CFG)
        return conn
    except Error as e:
        logger.error(f"Database connection error: {e}")
        sys.exit(1)

def _exec(conn, sql: str, params: tuple = ()):
    """Execute SQL query and return cursor"""
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur
    except Error as e:
        logger.error(f"SQL execution error: {e}")
        logger.error(f"SQL: {sql}")
        logger.error(f"Params: {params}")
        raise

def init_database():
    """Initialize database tables"""
    conn = reconnect()

    # Tournaments table
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Tournaments (
            tournament_id INT PRIMARY KEY AUTO_INCREMENT,
            chat_id BIGINT NOT NULL,
            creator_id BIGINT NOT NULL,
            name VARCHAR(255) DEFAULT 'Турнир',
            num_teams INT NOT NULL,
            num_rounds INT NOT NULL,
            status ENUM('creating', 'active', 'finished') DEFAULT 'creating',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            finished_at DATETIME DEFAULT NULL,
            INDEX idx_chat_status (chat_id, status),
            INDEX idx_creator (creator_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')

    # Teams table
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Teams (
            team_id INT PRIMARY KEY AUTO_INCREMENT,
            tournament_id INT NOT NULL,
            name VARCHAR(255) NOT NULL,
            position INT NOT NULL,
            FOREIGN KEY (tournament_id) REFERENCES Tournaments(tournament_id) ON DELETE CASCADE,
            INDEX idx_tournament (tournament_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')

    # Matches table
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Matches (
            match_id INT PRIMARY KEY AUTO_INCREMENT,
            tournament_id INT NOT NULL,
            round INT NOT NULL,
            match_number INT NOT NULL,
            team1_id INT NOT NULL,
            team2_id INT NOT NULL,
            team1_score INT DEFAULT NULL,
            team2_score INT DEFAULT NULL,
            status ENUM('pending', 'finished') DEFAULT 'pending',
            played_at DATETIME DEFAULT NULL,
            FOREIGN KEY (tournament_id) REFERENCES Tournaments(tournament_id) ON DELETE CASCADE,
            FOREIGN KEY (team1_id) REFERENCES Teams(team_id) ON DELETE CASCADE,
            FOREIGN KEY (team2_id) REFERENCES Teams(team_id) ON DELETE CASCADE,
            INDEX idx_tournament_status (tournament_id, status),
            INDEX idx_tournament_round (tournament_id, round)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')

    # Standings table (cached for performance)
    _exec(conn, '''
        CREATE TABLE IF NOT EXISTS Standings (
            standing_id INT PRIMARY KEY AUTO_INCREMENT,
            tournament_id INT NOT NULL,
            team_id INT NOT NULL,
            played INT DEFAULT 0,
            won INT DEFAULT 0,
            drawn INT DEFAULT 0,
            lost INT DEFAULT 0,
            goals_for INT DEFAULT 0,
            goals_against INT DEFAULT 0,
            goal_difference INT DEFAULT 0,
            points INT DEFAULT 0,
            FOREIGN KEY (tournament_id) REFERENCES Tournaments(tournament_id) ON DELETE CASCADE,
            FOREIGN KEY (team_id) REFERENCES Teams(team_id) ON DELETE CASCADE,
            UNIQUE KEY unique_tournament_team (tournament_id, team_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    ''')

    conn.commit()
    conn.close()
    logger.info("Database initialized successfully")

# ==================== Tournament Operations ====================

def create_tournament(chat_id: int, creator_id: int, num_teams: int, num_rounds: int) -> int:
    """Create a new tournament and return tournament_id"""
    conn = reconnect()
    cur = _exec(conn, '''
        INSERT INTO Tournaments (chat_id, creator_id, num_teams, num_rounds, status)
        VALUES (%s, %s, %s, %s, 'creating')
    ''', (chat_id, creator_id, num_teams, num_rounds))
    tournament_id = cur.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Tournament {tournament_id} created by user {creator_id} in chat {chat_id}")
    return tournament_id

def get_active_tournament(chat_id: int) -> Optional[Tuple]:
    """Get active or creating tournament for chat"""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT tournament_id, creator_id, num_teams, num_rounds, status
        FROM Tournaments
        WHERE chat_id = %s AND status IN ('creating', 'active')
        ORDER BY created_at DESC
        LIMIT 1
    ''', (chat_id,))
    result = cur.fetchone()
    conn.close()
    return result

def get_tournament_info(tournament_id: int) -> Optional[Dict]:
    """Get full tournament information"""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT tournament_id, chat_id, creator_id, name, num_teams, num_rounds,
               status, created_at, finished_at
        FROM Tournaments
        WHERE tournament_id = %s
    ''', (tournament_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    return {
        'tournament_id': row[0],
        'chat_id': row[1],
        'creator_id': row[2],
        'name': row[3],
        'num_teams': row[4],
        'num_rounds': row[5],
        'status': row[6],
        'created_at': row[7],
        'finished_at': row[8]
    }

def activate_tournament(tournament_id: int):
    """Change tournament status to active"""
    conn = reconnect()
    _exec(conn, '''
        UPDATE Tournaments SET status = 'active' WHERE tournament_id = %s
    ''', (tournament_id,))
    conn.commit()
    conn.close()
    logger.info(f"Tournament {tournament_id} activated")

def finish_tournament(tournament_id: int):
    """Finish tournament"""
    conn = reconnect()
    _exec(conn, '''
        UPDATE Tournaments
        SET status = 'finished', finished_at = NOW()
        WHERE tournament_id = %s
    ''', (tournament_id,))
    conn.commit()
    conn.close()
    logger.info(f"Tournament {tournament_id} finished")

def delete_tournament(tournament_id: int):
    """Delete tournament (cascade deletes teams, matches, standings)"""
    conn = reconnect()
    _exec(conn, 'DELETE FROM Tournaments WHERE tournament_id = %s', (tournament_id,))
    conn.commit()
    conn.close()
    logger.info(f"Tournament {tournament_id} deleted")

# ==================== Team Operations ====================

def add_teams(tournament_id: int, team_names: List[str]) -> List[int]:
    """Add teams to tournament and return list of team_ids"""
    conn = reconnect()
    team_ids = []

    for position, name in enumerate(team_names, start=1):
        cur = _exec(conn, '''
            INSERT INTO Teams (tournament_id, name, position)
            VALUES (%s, %s, %s)
        ''', (tournament_id, name, position))
        team_ids.append(cur.lastrowid)

    conn.commit()
    conn.close()
    logger.info(f"Added {len(team_names)} teams to tournament {tournament_id}")
    return team_ids

def get_teams(tournament_id: int) -> List[Tuple]:
    """Get all teams for tournament"""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT team_id, name, position
        FROM Teams
        WHERE tournament_id = %s
        ORDER BY position
    ''', (tournament_id,))
    teams = cur.fetchall()
    conn.close()
    return teams

def get_team_name(team_id: int) -> str:
    """Get team name by id"""
    conn = reconnect()
    cur = _exec(conn, 'SELECT name FROM Teams WHERE team_id = %s', (team_id,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else "Unknown"

# ==================== Match Operations ====================

def add_matches(tournament_id: int, matches: List[Tuple[int, int, int, int]]):
    """
    Add matches to tournament
    matches: list of (round, match_number, team1_id, team2_id)
    """
    conn = reconnect()

    for round_num, match_num, team1_id, team2_id in matches:
        _exec(conn, '''
            INSERT INTO Matches (tournament_id, round, match_number, team1_id, team2_id, status)
            VALUES (%s, %s, %s, %s, %s, 'pending')
        ''', (tournament_id, round_num, match_num, team1_id, team2_id))

    conn.commit()
    conn.close()
    logger.info(f"Added {len(matches)} matches to tournament {tournament_id}")

def get_pending_matches(tournament_id: int, limit: int = 4) -> List[Tuple]:
    """Get pending matches"""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT match_id, round, match_number, team1_id, team2_id
        FROM Matches
        WHERE tournament_id = %s AND status = 'pending'
        ORDER BY round, match_number
        LIMIT %s
    ''', (tournament_id, limit))
    matches = cur.fetchall()
    conn.close()
    return matches

def get_match_by_number(tournament_id: int, match_number: int) -> Optional[Tuple]:
    """Get match by its number"""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT match_id, round, match_number, team1_id, team2_id,
               team1_score, team2_score, status
        FROM Matches
        WHERE tournament_id = %s AND match_number = %s
    ''', (tournament_id, match_number))
    match = cur.fetchone()
    conn.close()
    return match

def record_match_result(match_id: int, team1_score: int, team2_score: int):
    """Record match result"""
    conn = reconnect()
    _exec(conn, '''
        UPDATE Matches
        SET team1_score = %s, team2_score = %s, status = 'finished', played_at = NOW()
        WHERE match_id = %s
    ''', (team1_score, team2_score, match_id))
    conn.commit()
    conn.close()
    logger.info(f"Match {match_id} result recorded: {team1_score}:{team2_score}")

def update_match_result(match_id: int, team1_score: int, team2_score: int):
    """Update existing match result"""
    conn = reconnect()
    _exec(conn, '''
        UPDATE Matches
        SET team1_score = %s, team2_score = %s
        WHERE match_id = %s
    ''', (team1_score, team2_score, match_id))
    conn.commit()
    conn.close()
    logger.info(f"Match {match_id} result updated: {team1_score}:{team2_score}")

def get_all_finished_matches(tournament_id: int) -> List[Tuple]:
    """Get all finished matches with match numbers for proper ordering"""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT match_id, match_number, team1_id, team2_id, team1_score, team2_score
        FROM Matches
        WHERE tournament_id = %s AND status = 'finished'
        ORDER BY match_number
    ''', (tournament_id,))
    matches = cur.fetchall()
    conn.close()
    return matches

def count_matches_status(tournament_id: int) -> Tuple[int, int]:
    """Count pending and finished matches"""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT
            SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
            SUM(CASE WHEN status = 'finished' THEN 1 ELSE 0 END) as finished
        FROM Matches
        WHERE tournament_id = %s
    ''', (tournament_id,))
    row = cur.fetchone()
    conn.close()
    return (row[0] or 0, row[1] or 0)

# ==================== Standings Operations ====================

def init_standings(tournament_id: int, team_ids: List[int]):
    """Initialize standings for all teams"""
    conn = reconnect()

    for team_id in team_ids:
        _exec(conn, '''
            INSERT INTO Standings (tournament_id, team_id)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE team_id = team_id
        ''', (tournament_id, team_id))

    conn.commit()
    conn.close()
    logger.info(f"Standings initialized for tournament {tournament_id}")

def recalculate_standings(tournament_id: int):
    """Recalculate standings from all finished matches"""
    conn = reconnect()

    # Reset all standings
    _exec(conn, '''
        UPDATE Standings
        SET played = 0, won = 0, drawn = 0, lost = 0,
            goals_for = 0, goals_against = 0, goal_difference = 0, points = 0
        WHERE tournament_id = %s
    ''', (tournament_id,))

    # Get all finished matches
    matches = get_all_finished_matches(tournament_id)

    # Calculate stats for each match
    for match_id, _, team1_id, team2_id, team1_score, team2_score in matches:
        # Update team1
        if team1_score > team2_score:
            # Team1 won
            _exec(conn, '''
                UPDATE Standings
                SET played = played + 1, won = won + 1,
                    goals_for = goals_for + %s, goals_against = goals_against + %s,
                    goal_difference = goal_difference + %s, points = points + 3
                WHERE tournament_id = %s AND team_id = %s
            ''', (team1_score, team2_score, team1_score - team2_score, tournament_id, team1_id))

            # Team2 lost
            _exec(conn, '''
                UPDATE Standings
                SET played = played + 1, lost = lost + 1,
                    goals_for = goals_for + %s, goals_against = goals_against + %s,
                    goal_difference = goal_difference + %s
                WHERE tournament_id = %s AND team_id = %s
            ''', (team2_score, team1_score, team2_score - team1_score, tournament_id, team2_id))

        elif team1_score < team2_score:
            # Team2 won
            _exec(conn, '''
                UPDATE Standings
                SET played = played + 1, won = won + 1,
                    goals_for = goals_for + %s, goals_against = goals_against + %s,
                    goal_difference = goal_difference + %s, points = points + 3
                WHERE tournament_id = %s AND team_id = %s
            ''', (team2_score, team1_score, team2_score - team1_score, tournament_id, team2_id))

            # Team1 lost
            _exec(conn, '''
                UPDATE Standings
                SET played = played + 1, lost = lost + 1,
                    goals_for = goals_for + %s, goals_against = goals_against + %s,
                    goal_difference = goal_difference + %s
                WHERE tournament_id = %s AND team_id = %s
            ''', (team1_score, team2_score, team1_score - team2_score, tournament_id, team1_id))
        else:
            # Draw
            for team_id in [team1_id, team2_id]:
                _exec(conn, '''
                    UPDATE Standings
                    SET played = played + 1, drawn = drawn + 1,
                        goals_for = goals_for + %s, goals_against = goals_against + %s,
                        points = points + 1
                    WHERE tournament_id = %s AND team_id = %s
                ''', (team1_score, team1_score, tournament_id, team_id))

    conn.commit()
    conn.close()
    logger.info(f"Standings recalculated for tournament {tournament_id}")

def get_standings(tournament_id: int) -> List[Tuple]:
    """Get standings sorted by points, goal difference, goals for"""
    conn = reconnect()
    cur = _exec(conn, '''
        SELECT s.team_id, t.name, s.played, s.won, s.drawn, s.lost,
               s.goals_for, s.goals_against, s.goal_difference, s.points
        FROM Standings s
        JOIN Teams t ON s.team_id = t.team_id
        WHERE s.tournament_id = %s
        ORDER BY s.points DESC, s.goal_difference DESC, s.goals_for DESC, t.name ASC
    ''', (tournament_id,))
    standings = cur.fetchall()
    conn.close()
    return standings

def get_normalized_standings(tournament_id: int, max_games_per_team: int) -> List[Tuple]:
    """
    Get standings recalculated with only first N games per team.
    Used for early tournament finish when teams played different number of games.
    """
    logger.info(f"Calculating normalized standings for tournament {tournament_id}, max_games={max_games_per_team}")

    try:
        # Get all teams
        teams = get_teams(tournament_id)
        logger.info(f"Got {len(teams)} teams for tournament {tournament_id}")
        if not teams:
            return []

        # Get all finished matches (with match_number for ordering)
        all_matches = get_all_finished_matches(tournament_id)
        logger.info(f"Got {len(all_matches)} finished matches for tournament {tournament_id}")

        # For each team, count matches and select first N
        team_stats = {}
        for team_id, team_name, _ in teams:  # _ ignores position field
            team_stats[team_id] = {
                'name': team_name,
                'played': 0,
                'won': 0,
                'drawn': 0,
                'lost': 0,
                'goals_for': 0,
                'goals_against': 0,
                'goal_difference': 0,
                'points': 0
            }

        logger.info(f"Initialized stats for {len(team_stats)} teams")

        # Process matches in order (by match_number)
        for match in all_matches:
            match_id, match_number, team1_id, team2_id, score1, score2 = match

            # Check if team_ids exist in team_stats
            if team1_id not in team_stats:
                logger.error(f"Team {team1_id} from match {match_id} not found in team_stats")
                continue
            if team2_id not in team_stats:
                logger.error(f"Team {team2_id} from match {match_id} not found in team_stats")
                continue

            # Check if both teams haven't exceeded max_games yet
            team1_played = team_stats[team1_id]['played']
            team2_played = team_stats[team2_id]['played']

            # Only count this match if both teams haven't reached the limit
            if team1_played < max_games_per_team and team2_played < max_games_per_team:
                # Update games played
                team_stats[team1_id]['played'] += 1
                team_stats[team2_id]['played'] += 1

                # Update goals
                team_stats[team1_id]['goals_for'] += score1
                team_stats[team1_id]['goals_against'] += score2
                team_stats[team2_id]['goals_for'] += score2
                team_stats[team2_id]['goals_against'] += score1

                # Determine winner and update points/wins/draws/losses
                if score1 > score2:
                    # Team1 wins
                    team_stats[team1_id]['won'] += 1
                    team_stats[team1_id]['points'] += 3
                    team_stats[team2_id]['lost'] += 1
                elif score2 > score1:
                    # Team2 wins
                    team_stats[team2_id]['won'] += 1
                    team_stats[team2_id]['points'] += 3
                    team_stats[team1_id]['lost'] += 1
                else:
                    # Draw
                    team_stats[team1_id]['drawn'] += 1
                    team_stats[team2_id]['drawn'] += 1
                    team_stats[team1_id]['points'] += 1
                    team_stats[team2_id]['points'] += 1

        # Calculate goal difference
        for team_id in team_stats:
            gf = team_stats[team_id]['goals_for']
            ga = team_stats[team_id]['goals_against']
            team_stats[team_id]['goal_difference'] = gf - ga

        logger.info("Goal differences calculated, converting to list")

        # Convert to list of tuples matching get_standings format
        standings = []
        for team_id, stats in team_stats.items():
            standings.append((
                team_id,
                stats['name'],
                stats['played'],
                stats['won'],
                stats['drawn'],
                stats['lost'],
                stats['goals_for'],
                stats['goals_against'],
                stats['goal_difference'],
                stats['points']
            ))

        logger.info(f"Converted to list, sorting {len(standings)} teams")

        # Sort by points DESC, goal_difference DESC, goals_for DESC, name ASC
        standings.sort(key=lambda x: (-x[9], -x[8], -x[6], x[1]))

        logger.info(f"Normalized standings calculated: {len(standings)} teams")
        return standings

    except Exception as e:
        logger.error(f"Error calculating normalized standings: {e}", exc_info=True)
        raise

# Initialize database on module import
if __name__ == '__main__':
    init_database()
    print("Database initialized successfully!")
