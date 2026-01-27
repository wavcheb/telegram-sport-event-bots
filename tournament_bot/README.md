# 🏆 Tournament Bot

Telegram bot for managing sports tournaments with automatic standings calculation based on Round-Robin algorithm.

## 🌟 Features

- **Round-Robin Tournament System**: Fair scheduling ensuring every team plays every other team
- **Automatic Standings**: Real-time calculation following standard rules (3-1-0 points)
- **Multiple Rounds**: Support for 1-4 rounds (each team plays others multiple times)
- **Interactive Match Entry**: Click buttons to enter scores, instant table updates
- **Early Finish**: Option to stop tournament early with proper handling
- **Result Editing**: Modify match results with automatic recalculation
- **Beautiful Tables**: Clean, emoji-enhanced tournament standings
- **Creator Rights**: Only tournament creator can manage and edit

## 📋 Requirements

- Python 3.11+
- MySQL 5.7+ or MariaDB 10.3+
- Telegram Bot Token
- python-telegram-bot >= 22.0
- loguru
- mysql-connector-python

## 🚀 Quick Start

### 1. Database Setup

Create a separate database for Tournament Bot:

```sql
CREATE DATABASE tournament_bot CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'tournament_bot'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON tournament_bot.* TO 'tournament_bot'@'localhost';
FLUSH PRIVILEGES;
```

Update credentials in `tournament_bot/db_tournament.py`:
```python
MYSQL_CFG = {
    'host': 'localhost',
    'database': 'tournament_bot',
    'user': 'tournament_bot',
    'password': 'your_password',  # Change this!
    ...
}
```

Initialize database tables:
```bash
python3 -m tournament_bot.db_tournament
```

### 2. Configure Bot Token

Create `tournament_bot/token.txt` file with your Telegram Bot Token:

```bash
echo "YOUR_TOURNAMENT_BOT_TOKEN" > tournament_bot/token.txt
```

### 3. Run the Bot

```bash
./run_tournament_bot.sh
```

Or directly with Python:
```bash
python3 -m tournament_bot.bot
```

## 📖 How to Use

### Creating a Tournament

1. Start with `/create` command
2. Enter number of teams (2-20)
3. Enter team names:
   - With semicolon: `Barcelona; Real Madrid; Bayern`
   - With spaces: `Barcelona Real_Madrid Bayern`
   - Line by line:
     ```
     Barcelona
     Real Madrid
     Bayern
     ```
4. Choose number of rounds (1-4)
5. Confirm by clicking "✅ Создать сетку"

### During Tournament

- **View Status**: `/status` - See current standings and next matches
- **View Table**: `/table` - See only the standings table
- **Enter Result**: Click on a match button, then enter score:
  - `3:1` or `3-1` or `3 1` - all formats work
- **Edit Result**: `/edit 5 2:1` - Edit match #5 to 2:1
- **Finish Early**: `/stopnow` - End tournament before all matches

### Tournament Rules

- **Win**: 3 points
- **Draw**: 1 point
- **Loss**: 0 points
- **Tiebreaker**: Goal difference, then goals scored

### Early Finish

When using `/stopnow`:
- If teams played different numbers of games, you'll need to confirm
- Final table will only count teams with equal minimum games played
- At least one match must be played to finish early

## 🎯 Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and bot introduction |
| `/help` | Detailed help with all features |
| `/create` | Start creating a new tournament |
| `/status` | Show tournament status with next matches |
| `/table` | Show current standings table |
| `/stopnow` | Finish tournament early (creator only) |
| `/edit [match#] [score]` | Edit match result (creator only) |
| `/cancel` | Cancel tournament creation (during setup) |

## 💡 Usage Examples

### Example 1: Simple 4-Team Tournament

```
User: /create
Bot: Сколько команд? (2-20)

User: 4
Bot: Введите названия 4 команд

User: Barcelona; Real Madrid; Bayern; PSG
Bot: Команды добавлены. Сколько кругов? (1-4)

User: 1
Bot: [Shows summary with "Создать сетку" button]

User: [Clicks "Создать сетку"]
Bot: [Shows table and 4 next match buttons]

User: [Clicks "Barcelona vs Real Madrid"]
Bot: Введите счет: 3:1

User: 3:1
Bot: ✅ Результат записан!
     [Updated table with Barcelona leading]
```

### Example 2: Editing a Result

```
User: /edit 5 2:1
Bot: ✅ Результат матча #5 изменен!
     ⚽ Team1 2:1 Team2
     (Было: 3:0)
     Таблица пересчитана.
```

### Example 3: Early Finish

```
User: /stopnow
Bot: ⚠️ Внимание!
     Команды сыграли разное количество матчей
     ...
     Подтвердите: /stopnow confirm

User: /stopnow confirm
Bot: 🏆 ТУРНИР ЗАВЕРШЕН!
     [Shows final standings]
```

## 🗄️ Database Schema

### Tournaments Table
- `tournament_id` - Primary key
- `chat_id` - Telegram chat/group ID
- `creator_id` - User who created tournament
- `num_teams`, `num_rounds` - Tournament parameters
- `status` - creating/active/finished
- `created_at`, `finished_at` - Timestamps

### Teams Table
- `team_id` - Primary key
- `tournament_id` - Foreign key
- `name` - Team name
- `position` - Initial position

### Matches Table
- `match_id` - Primary key
- `tournament_id` - Foreign key
- `round`, `match_number` - Match identification
- `team1_id`, `team2_id` - Competing teams
- `team1_score`, `team2_score` - Match result
- `status` - pending/finished

### Standings Table (Cached)
- Automatically calculated from match results
- `played`, `won`, `drawn`, `lost` - Statistics
- `goals_for`, `goals_against`, `goal_difference` - Goal stats
- `points` - Total points (3 for win, 1 for draw)

## 🔧 Technical Details

### Round-Robin Algorithm

The bot uses the **Circle Method** for generating fair Round-Robin schedules:
1. Teams are arranged in a circle
2. First team stays fixed, others rotate
3. Ensures each team plays every other team exactly once per round
4. Handles odd numbers of teams (one team gets "bye")

### Standings Calculation

Standings are recalculated after each match:
1. Fetch all finished matches
2. Reset all standings to zero
3. Process each match:
   - Winner gets +3 points
   - Draw gives both +1 point
   - Loser gets 0 points
4. Update goal stats (for/against/difference)
5. Sort by: points DESC, goal_difference DESC, goals_for DESC

### FSM (Finite State Machine)

Tournament creation uses ConversationHandler:
- `AWAITING_TEAM_COUNT` → Enter number
- `AWAITING_TEAM_NAMES` → Enter names
- `AWAITING_ROUND_COUNT` → Choose rounds
- `AWAITING_CONFIRMATION` → Create grid

## 🛠️ Development

### Project Structure

```
telegram-sport-event-bots/
├── tournament_bot/          # Tournament Bot module
│   ├── __init__.py         # Package initialization
│   ├── bot.py              # Main bot with handlers
│   ├── db_tournament.py    # Database operations
│   ├── tournament_logic.py # Tournament algorithms
│   ├── token.txt           # Bot token (create this)
│   ├── token.txt.example   # Token file template
│   └── logs/               # Log files
├── run_tournament_bot.sh   # Startup script
└── README_TOURNAMENT.md    # This file
```

### Adding New Features

1. **New Command**: Add handler in `tournament_bot/bot.py` `main()` function
2. **New Algorithm**: Implement in `tournament_bot/tournament_logic.py`
3. **Database Change**: Update schema in `tournament_bot/db_tournament.py`

### Testing

```bash
# Initialize database
python3 -m tournament_bot.db_tournament

# Run bot
./run_tournament_bot.sh

# Test in Telegram:
/start
/create
# Follow prompts...
```

## 🐛 Troubleshooting

### Bot doesn't start
- Check `tournament_bot/token.txt` exists and contains valid token
- Verify Python version: `python --version` (need 3.11+)
- Check logs: `tail -f tournament_bot/logs/tournament_bot.log`

### Database connection fails
- Verify MySQL is running: `systemctl status mysql`
- Test credentials: `mysql -u tournament_bot -p tournament_bot`
- Check config in `tournament_bot/db_tournament.py`

### Can't create tournament
- Ensure no active tournament in that chat
- Check you have required permissions
- Finish existing tournament with `/stopnow`

### Match scores don't update
- Verify tournament is in 'active' status
- Check you clicked the correct match button
- Try format: `3:1` (with colon)

## 📝 Limitations

- One active tournament per chat at a time
- Maximum 20 teams per tournament
- Maximum 4 rounds
- Only creator can manage tournament
- No multi-stage tournaments (playoffs, etc.)

## 🚀 Future Enhancements

Potential features for future versions:
- [ ] Multi-stage tournaments (groups + playoffs)
- [ ] Scheduling with dates/times
- [ ] Player statistics across tournaments
- [ ] Export results to CSV/PDF
- [ ] Multiple tournaments per chat
- [ ] Team management (add/remove mid-tournament)
- [ ] Undo last result
- [ ] Tournament templates

## 💡 Tips

1. **Team Names**: Keep them short (under 20 chars) for better display
2. **Rounds**: Start with 1 round, add more for longer tournaments
3. **Testing**: Test with 3-4 teams before running real tournaments
4. **Backup**: Export final standings before deleting
5. **Performance**: Works best with 4-12 teams

## 🤝 Integration with Event Bot

Both bots can run simultaneously:
- Use separate databases (`futsal_bot` and `tournament_bot`)
- Can share same MySQL server
- Use different bot tokens
- Independent operation

## 📄 License

Part of the Sport Event Bot project.

## 🙏 Credits

- Round-Robin algorithm: Standard circle method
- Created for sports communities
- Built with python-telegram-bot

---

**Ready to organize your tournament? Start with `/create`! 🏆⚽**
