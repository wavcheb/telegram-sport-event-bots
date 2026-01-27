# -*- coding: utf-8 -*-
"""
Tournament Logic Module
Round-Robin algorithm, standings calculation, formatting
"""

import re
from typing import List, Tuple, Optional
from loguru import logger

def generate_round_robin_schedule(team_ids: List[int], num_rounds: int = 1) -> List[Tuple[int, int, int, int]]:
    """
    Generate Round-Robin tournament schedule
    Returns: list of (round, match_number, team1_id, team2_id)

    Algorithm: Circle method for round-robin
    """
    n = len(team_ids)
    matches = []
    match_counter = 1

    # If odd number of teams, add a "bye" (None)
    if n % 2 == 1:
        team_ids = team_ids + [None]
        n += 1

    # Generate matches for each round
    for round_num in range(1, num_rounds + 1):
        # Each team plays every other team once per round
        # Total matches per round = n/2 * (n-1)
        teams = team_ids.copy()

        for match_day in range(n - 1):
            # Pair teams: first with last, second with second-to-last, etc.
            for i in range(n // 2):
                team1 = teams[i]
                team2 = teams[n - 1 - i]

                # Skip if either team is "bye"
                if team1 is not None and team2 is not None:
                    matches.append((round_num, match_counter, team1, team2))
                    match_counter += 1

            # Rotate teams (keep first team fixed, rotate others)
            teams = [teams[0]] + [teams[-1]] + teams[1:-1]

    logger.info(f"Generated {len(matches)} matches for {len(team_ids)} teams, {num_rounds} rounds")
    return matches

def parse_score(score_text: str) -> Optional[Tuple[int, int]]:
    """
    Parse score from various formats
    Supported: "3:1", "3-1", "3 1", "3  1"
    Returns: (team1_score, team2_score) or None if invalid
    """
    score_text = score_text.strip()

    # Try different separators
    patterns = [
        r'^(\d+)\s*:\s*(\d+)$',  # 3:1
        r'^(\d+)\s*-\s*(\d+)$',  # 3-1
        r'^(\d+)\s+(\d+)$',      # 3 1
    ]

    for pattern in patterns:
        match = re.match(pattern, score_text)
        if match:
            score1 = int(match.group(1))
            score2 = int(match.group(2))
            # Sanity check: scores should be reasonable (0-99)
            if 0 <= score1 <= 99 and 0 <= score2 <= 99:
                return (score1, score2)

    return None

def parse_team_names(text: str) -> List[str]:
    """
    Parse team names from various formats
    Supported:
    - Semicolon: "Team1; Team2; Team3"
    - Space: "Team1 Team2 Team3"
    - Newline: "Team1\nTeam2\nTeam3"
    Returns: list of team names
    """
    # Try semicolon first
    if ';' in text:
        teams = [t.strip() for t in text.split(';') if t.strip()]
    # Try newline
    elif '\n' in text:
        teams = [t.strip() for t in text.split('\n') if t.strip()]
    # Try space (but handle multi-word team names)
    else:
        # Split by multiple spaces or single space if clear separation
        teams = [t.strip() for t in re.split(r'\s{2,}', text) if t.strip()]
        # If only one team found, try splitting by single space
        if len(teams) <= 1:
            teams = [t.strip() for t in text.split() if t.strip()]

    # Remove duplicates while preserving order
    seen = set()
    unique_teams = []
    for team in teams:
        if team not in seen:
            seen.add(team)
            unique_teams.append(team)

    return unique_teams

def format_standings_table(standings: List[Tuple], include_position: bool = True) -> str:
    """
    Format standings as a beautiful table with monospace font
    standings: list of (team_id, name, played, won, drawn, lost, gf, ga, gd, points)
    """
    if not standings:
        return "Нет данных для отображения."

    # Calculate column widths
    max_name_len = max(len(row[1]) for row in standings)
    max_name_len = min(max_name_len, 20)  # Limit to 20 chars

    # Build table with monospace formatting
    lines = []

    # Title (outside of monospace block)
    lines.append("📊 <b>ТУРНИРНАЯ ТАБЛИЦА</b>")

    # Show medals for top 3 outside of table
    if include_position and len(standings) >= 1:
        medal_lines = []
        for position, row in enumerate(standings[:3], start=1):
            if position == 1:
                medal_lines.append(f"🥇 {row[1]}")
            elif position == 2:
                medal_lines.append(f"🥈 {row[1]}")
            elif position == 3:
                medal_lines.append(f"🥉 {row[1]}")
        if medal_lines:
            lines.append("<i>" + " • ".join(medal_lines) + "</i>")

    lines.append("")  # Empty line before table

    # Start monospace block
    lines.append("<pre>")

    # Header with Unicode box-drawing characters
    if include_position:
        header = f"┌────┬{'─' * (max_name_len + 2)}┬────┬───┬───┬───┬────┬────┬─────┬──────┐"
        lines.append(header)

        # Column headers
        col_header = f"│Поз │ {'Команда':<{max_name_len}} │ И  │ В │ Н │ П │ ЗМ │ ПМ │  Р  │ Очки │"
        lines.append(col_header)

        separator = f"├────┼{'─' * (max_name_len + 2)}┼────┼───┼───┼───┼────┼────┼─────┼──────┤"
    else:
        header = f"┌{'─' * (max_name_len + 2)}┬────┬───┬───┬───┬────┬────┬─────┬──────┐"
        lines.append(header)

        col_header = f"│ {'Команда':<{max_name_len}} │ И  │ В │ Н │ П │ ЗМ │ ПМ │  Р  │ Очки │"
        lines.append(col_header)

        separator = f"├{'─' * (max_name_len + 2)}┼────┼───┼───┼───┼────┼────┼─────┼──────┤"

    lines.append(separator)

    # Rows - NO EMOJIS in monospace part
    for position, row in enumerate(standings, start=1):
        team_id, name, played, won, drawn, lost, gf, ga, gd, points = row

        # Truncate long names or pad short names
        if len(name) > max_name_len:
            name = name[:max_name_len-2] + ".."
        else:
            # Pad short names to max_name_len to ensure proper alignment
            name = name.ljust(max_name_len)

        # Format goal difference with sign
        gd_str = f"{gd:+4d}" if gd != 0 else "  0 "

        if include_position:
            # Just position number, no emoji
            line = f"│ {position:>2} │ {name} │ {played:>2} │{won:>2} │{drawn:>2} │{lost:>2} │ {gf:>2} │ {ga:>2} │{gd_str} │  {points:>2}  │"
        else:
            line = f"│ {name} │ {played:>2} │{won:>2} │{drawn:>2} │{lost:>2} │ {gf:>2} │ {ga:>2} │{gd_str} │  {points:>2}  │"

        lines.append(line)

    # Bottom border
    if include_position:
        bottom = f"└────┴{'─' * (max_name_len + 2)}┴────┴───┴───┴───┴────┴────┴─────┴──────┘"
    else:
        bottom = f"└{'─' * (max_name_len + 2)}┴────┴───┴───┴───┴────┴────┴─────┴──────┘"

    lines.append(bottom)

    # End monospace block
    lines.append("</pre>")

    # Legend (outside of monospace block)
    lines.append("\n📖 <b>Обозначения:</b>")
    lines.append("<i>И - Игры, В - Выигрыши, Н - Ничьи, П - Поражения</i>")
    lines.append("<i>ЗМ - Забито, ПМ - Пропущено, Р - Разница</i>")

    return "\n".join(lines)

def format_match_button_text(team1_name: str, team2_name: str) -> str:
    """Format match button text"""
    max_len = 15
    if len(team1_name) > max_len:
        team1_name = team1_name[:max_len-2] + ".."
    if len(team2_name) > max_len:
        team2_name = team2_name[:max_len-2] + ".."
    return f"⚽ {team1_name} vs {team2_name}"

def format_match_result(team1_name: str, team2_name: str, score1: int, score2: int) -> str:
    """Format match result message"""
    if score1 > score2:
        result_emoji = "🏆"
        winner = team1_name
    elif score2 > score1:
        result_emoji = "🏆"
        winner = team2_name
    else:
        result_emoji = "🤝"
        winner = None

    message = f"⚽ {team1_name} {score1}:{score2} {team2_name}\n"

    if winner:
        message += f"{result_emoji} Победа: {winner}"
    else:
        message += f"{result_emoji} Ничья"

    return message

def calculate_total_matches(num_teams: int, num_rounds: int) -> int:
    """Calculate total number of matches"""
    # Each team plays every other team once per round
    # Formula: n * (n - 1) / 2 * rounds
    return (num_teams * (num_teams - 1) // 2) * num_rounds

def normalize_standings_by_min_games(standings: List[Tuple], tournament_id: int) -> List[Tuple]:
    """
    Normalize standings when teams have played different numbers of games
    Only count games up to the minimum number played by any team
    This is used for early tournament finish

    NOTE: This is a simplified version. For proper implementation,
    we should recalculate from match history filtered by games played.
    """
    if not standings:
        return standings

    # Find minimum games played
    min_games = min(row[2] for row in standings)  # row[2] is 'played'

    if min_games == 0:
        # No games played, return as is
        return standings

    # For now, just filter teams that have played more than min_games
    # In a real implementation, we'd need to recalculate from match history
    # This is a placeholder - proper implementation would require match-by-match recalculation

    logger.warning(f"Normalizing standings to {min_games} games (simplified)")
    return standings

def format_tournament_summary(tournament_info: dict, standings: List[Tuple]) -> str:
    """Format final tournament summary"""
    lines = []
    lines.append("🏆 <b>═══════════════════════════════</b>")
    lines.append("<b>     ТУРНИР ЗАВЕРШЕН!</b>")
    lines.append("<b>═══════════════════════════════</b> 🏆\n")

    # Tournament info
    lines.append(f"📅 <b>Создан:</b> {tournament_info['created_at'].strftime('%d.%m.%Y %H:%M')}")
    if tournament_info['finished_at']:
        lines.append(f"🏁 <b>Завершен:</b> {tournament_info['finished_at'].strftime('%d.%m.%Y %H:%M')}")
    lines.append(f"👥 <b>Команд:</b> {tournament_info['num_teams']}")
    lines.append(f"🔄 <b>Кругов:</b> {tournament_info['num_rounds']}\n")

    # Standings
    lines.append(format_standings_table(standings))

    # Winner
    if standings:
        winner = standings[0]
        lines.append(f"\n🏆 <b>ПОБЕДИТЕЛЬ: {winner[1]}</b>")
        lines.append(f"<i>Очки: {winner[9]} | Голы: {winner[6]}-{winner[7]}</i>")

    return "\n".join(lines)

# Validation functions

def validate_team_count(count: int) -> bool:
    """Validate team count (2-20)"""
    return 2 <= count <= 20

def validate_round_count(count: int) -> bool:
    """Validate round count (1-4)"""
    return 1 <= count <= 4

def validate_team_names(names: List[str], expected_count: int) -> Tuple[bool, str]:
    """
    Validate team names
    Returns: (is_valid, error_message)
    """
    if len(names) != expected_count:
        return False, f"Ожидалось {expected_count} команд, получено {len(names)}"

    if len(names) != len(set(names)):
        return False, "Названия команд должны быть уникальными"

    for name in names:
        if not name or len(name) < 2:
            return False, "Название команды должно содержать минимум 2 символа"
        if len(name) > 50:
            return False, "Название команды не должно превышать 50 символов"

    return True, ""
