# 📊 Tournament Table Formatting Example

## New Beautiful Table Format

The tournament table now uses:
- ✅ **Monospace font** (`<pre>` tags) for perfect column alignment
- ✅ **Unicode box-drawing characters** for beautiful borders
- ✅ **Medal emojis** (🥇🥈🥉) for top 3 positions
- ✅ **HTML formatting** for title and legend
- ✅ **Compact and readable** layout

## Example Output

**Before (old format):**
```
📊 ТУРНИРНАЯ ТАБЛИЦА

Поз  Команда              И   В   Н   П   ЗМ   ПМ    Р  Очки
────────────────────────────────────────────────────────────
🥇1   Боруссия             2   2   0   0   11    6   +5    6
🥈2   Барселона            2   1   0   1    9    6   +3    3
🥉3   Реал                 2   0   0   2   12   -8    0    0
```
(Problem: columns don't align in Telegram without monospace font)

**After (new format v2 - FIXED):**
```
📊 ТУРНИРНАЯ ТАБЛИЦА
🥇 Боруссия • 🥈 Барселона • 🥉 Реал

┌────┬──────────────────────┬────┬───┬───┬───┬────┬────┬─────┬──────┐
│Поз │ Команда              │ И  │ В │ Н │ П │ ЗМ │ ПМ │  Р  │ Очки │
├────┼──────────────────────┼────┼───┼───┼───┼────┼────┼─────┼──────┤
│  1 │ Боруссия             │  2 │ 2 │ 0 │ 0 │ 11 │  6 │  +5 │   6  │
│  2 │ Барселона            │  2 │ 1 │ 0 │ 1 │  9 │  6 │  +3 │   3  │
│  3 │ Реал                 │  2 │ 0 │ 0 │ 2 │ 12 │  8 │  -8 │   0  │
└────┴──────────────────────┴────┴───┴───┴───┴────┴────┴─────┴──────┘

📖 Обозначения:
И - Игры, В - Выигрыши, Н - Ничьи, П - Поражения
ЗМ - Забито, ПМ - Пропущено, Р - Разница
```

**Key improvement:** Medals moved OUTSIDE the monospace table to prevent alignment issues!

## Features

### Unicode Box Characters Used
- `┌ ┬ ┐` - Top border
- `├ ┼ ┤` - Middle separator
- `└ ┴ ┘` - Bottom border
- `│` - Vertical separator
- `─` - Horizontal line

### Column Widths
- **Поз**: 4 chars (position + emoji)
- **Команда**: Dynamic (max 20 chars, truncated with "..")
- **И/В/Н/П**: 2 chars each (stats)
- **ЗМ/ПМ**: 3 chars each (goals)
- **Р**: 5 chars (goal difference with sign)
- **Очки**: 6 chars (points)

### Medal Emojis
- 🥇 - 1st place
- 🥈 - 2nd place
- 🥉 - 3rd place

### HTML Formatting
- `<pre>...</pre>` - Monospace block for table
- `<b>...</b>` - Bold for titles
- `<i>...</i>` - Italic for legend

## Technical Details

**File**: `tournament_bot/tournament_logic.py`
**Function**: `format_standings_table()`
**Parse Mode**: `ParseMode.HTML`

The table is sent using Telegram's HTML parse mode, which properly renders:
- The `<pre>` tag ensures monospace font
- Unicode characters render correctly
- Emojis display inline with text
- Bold and italic formatting work outside the `<pre>` block

## Testing

To test the new format:
```bash
cd /usr/local/tgbot
git pull
./run_tournament_bot.sh
```

In Telegram:
1. Create tournament: `/create`
2. Add teams: `Team1; Team2; Team3`
3. Enter match results
4. View table: `/table`

The table will now render beautifully with proper alignment! 🎉

## /stopnow Confirmation Buttons

The `/stopnow` command now uses interactive buttons instead of text confirmation.

### Old Behavior:
```
User: /stopnow
Bot: Команды сыграли разное количество матчей...
     Подтвердите завершение турнира:
     /stopnow confirm

User: /stopnow confirm  (had to type this)
Bot: Tournament finished
```

### New Behavior:
```
User: /stopnow
Bot: ⚠️ Внимание!
     Команды сыграли разное количество матчей...

     [✅ Подтвердить] [❌ Отмена]  (clickable buttons)

User: *clicks button*
Bot: Tournament finished / Отменено
```

### Features:
- ✅ No typing required - just click button
- ✅ Works for both equal and different game counts
- ✅ Safety confirmation even when all teams played same games
- ✅ Shows match statistics before confirmation
- ✅ Clear visual feedback
- ✅ Only tournament creator can confirm
- ✅ Cannot accidentally finish tournament

### Implementation:
- `stopnow_confirm_{tournament_id}` callback data
- `stopnow_cancel_{tournament_id}` callback data
- Pattern-based callback routing
- InlineKeyboardMarkup with two buttons
