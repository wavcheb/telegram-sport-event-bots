# MAX Sport Event Bot

Бот для MAX Messenger для организации спортивных событий с регистрацией участников.

## Возможности

- Создание событий с датой и временем
- Регистрация участников через кнопки
- Добавление легионеров (гостей)
- Подтверждение оплаты
- Кросс-платформенная связка с Telegram ботом
- Режим webhook для production (с автоматическим откатом на long polling)
- Toast-уведомления (всплывающие подсказки) при нажатии кнопок вместо сообщений в чат

## Установка

### Как часть монорепозитория

```bash
cd telegram-sport-event-bots
./max_sporteventbot/setup_venv.sh
```

### Как отдельный бот

```bash
# Скопировать файлы бота в отдельную директорию
mkdir -p /usr/local/maxbot/sporteventbot
cp -r max_sporteventbot/* /usr/local/maxbot/sporteventbot/

cd /usr/local/maxbot/sporteventbot
./setup_venv.sh
```

## Конфигурация

Создайте файл `.env`:

```bash
cp .env.example .env
nano .env
```

Обязательные переменные:

```
MAX_BOT_TOKEN=ваш_токен_max_бота

# База данных (общая с Telegram ботом)
MYSQL_HOST=localhost
MYSQL_DATABASE=futsal_bot
MYSQL_USER=futsal_bot
MYSQL_PASSWORD=пароль
```

Webhook (обязательно для production; если `MAX_WEBHOOK_URL` не задан, бот работает в режиме long polling — только для разработки):

```
# Публичный HTTPS URL, на который MAX будет отправлять обновления
MAX_WEBHOOK_URL=https://example.com/maxbot-webhook/

# Секрет для проверки webhook-запросов (рекомендуется)
MAX_WEBHOOK_SECRET=случайная_строка

# Локальный aiohttp-листенер (за nginx reverse proxy)
MAX_WEBHOOK_HOST=127.0.0.1
MAX_WEBHOOK_PORT=8180
MAX_WEBHOOK_PATH=/
```

Опциональные переменные:

```
# Страница оплаты
PAYMENTS_PAGE_URL=https://example.com/payments.php

# Для автоматической синхронизации в Telegram (кросс-API)
TG_BOT_TOKEN=токен_telegram_бота

# Доступ к Telegram API из заблокированных регионов:
# SOCKS/HTTP прокси
TELEGRAM_PROXY=socks5://127.0.0.1:1080
# или Cloudflare Worker прокси для api.telegram.org
TG_API_URL=https://tg-api-proxy.your-domain.workers.dev
```

## Запуск

```bash
./run.sh
```

Или напрямую:

```bash
source venv/bin/activate
python bot.py
```

## Команды бота

При запуске бот публикует свой список команд в MAX (`PATCH /me/commands`),
поэтому при вводе `/` мессенджер показывает подсказки. Список задаётся
константой `BOT_COMMANDS` в `bot.py` — при добавлении новой команды впишите её
туда же (MAX принимает не больше 32 команд).

| Команда | Описание |
|---------|----------|
| `/start` | Начало работы с ботом |
| `/help` | Список доступных команд |
| `/event_add` | Создать новое событие |
| `/event_remove` | Закрыть текущее событие |
| `/event_update` | Изменить описание события |
| `/limit` | Установить лимит участников |
| `/info` | Показать текущее событие |
| `/add` | Записаться на событие |
| `/remove` | Отменить запись |
| `/add_leg` | Добавить легионера (гостя) |
| `/rem_leg` | Убрать последнего легионера |
| `/pay` | Подтвердить оплату |
| `/fix` | Зафиксировать состав и статистику |
| `/penalty` | Добавить штраф за неявку |
| `/stat` | Статистика участников |
| `/event_datetime` | Установить дату и время события (свободная форма) |
| `/event_duty` | Выбрать дежурного на событие |
| `/mepls` | Вызваться дежурить самому |
| `/duty_stats` | Статистика дежурств |
| `/link` | Связать чат с Telegram чатом |
| `/unlink` | Отвязать чат |
| `/event_copy` | Скопировать событие из связанного Telegram чата |
| `/payments` | Показать страницу оплаты |

## 🧹 Дежурный

Дежурный за игру не платит. Что именно входит в дежурство, каждый чат
решает сам — стирка манишек, мяч, бронь площадки.

- `/event_duty` — среди участников события считается, кто сколько раз уже
  дежурил; из тех, у кого дежурств меньше всего, случайно выбирается один.
  Гости и легионеры (служебные id < 100) в выборе не участвуют.
- `/mepls` — любой записавшийся участник может вызваться дежурить сам и
  заменить назначенного.
- `/duty_stats` — кто сколько раз дежурил, кто дежурит сейчас и кто из
  записавшихся не дежурил ещё ни разу (именно из них выбирает `/event_duty`).

Дежурный назначается только вручную: в чатах, где дежурных нет, команды
просто не используются.

Дежурный отмечается 🧹 в анонсе события, а на странице оплат получает
зелёную плашку «Дежурный» и считается рассчитавшимся.

Дежурство общее для связанных чатов: выбранный в MAX дежурный виден и в
Telegram (и наоборот), а объявление публикуется в обоих чатах.

## Кросс-платформенная связка

MAX и Telegram боты могут использовать общую базу данных и показывать участников с обеих платформ.

### Настройка связки

1. В Telegram чате выполните `/link` - бот выдаст секретный код
2. В MAX чате выполните `/link КОД` - чаты связаны
3. Теперь участники из обеих платформ видны в обоих чатах

### Синхронизация участников

Для копирования события из Telegram:

```
/event_copy
```

### Автоматическая синхронизация (кросс-API)

Для автоматического обновления сообщений при изменении участников:

1. В `.env` добавьте `TG_BOT_TOKEN=токен_telegram_бота`
2. Когда участник записывается в MAX - сообщение в Telegram обновится автоматически
3. И наоборот (в Telegram боте нужен `MAX_BOT_TOKEN`)

## База данных

Бот использует MySQL. Таблицы создаются автоматически при первом запуске.

### Общая база с Telegram ботом

Боты разделяют данные через поле `platform`:
- Telegram бот: `platform = 'telegram'`
- MAX бот: `platform = 'max'`

Это позволяет:
- Использовать общую базу данных
- Связывать чаты между платформами
- Показывать участников из обеих платформ

## systemd сервис

Готовые unit-файлы поставляются вместе с ботом:

- `max-sport-event-bot.service` — системный сервис (требует root)
- `max-sport-event-bot-user.service` — пользовательский сервис (без root)

Они запускают `run.sh` из директории бота (`WorkingDirectory=/usr/local/maxbot/sporteventbot`). `EnvironmentFile=` не используется — `.env` загружается самим ботом через python-dotenv.

Установка системного сервиса:

```bash
sudo cp max-sport-event-bot.service /etc/systemd/system/
sudo nano /etc/systemd/system/max-sport-event-bot.service  # замените YOUR_USERNAME и пути при необходимости

sudo systemctl daemon-reload
sudo systemctl enable max-sport-event-bot
sudo systemctl start max-sport-event-bot
```

Или пользовательский сервис (без root):

```bash
mkdir -p ~/.config/systemd/user
cp max-sport-event-bot-user.service ~/.config/systemd/user/max-sport-event-bot.service
systemctl --user daemon-reload
systemctl --user enable --now max-sport-event-bot
loginctl enable-linger $USER
```

## Логи

Логи сохраняются в директории `logs/`.

```bash
tail -f logs/logs.log
```

## Зависимости

- Python 3.11+
- maxapi >= 1.2.0 (MAX Messenger API)
- mysql-connector-python
- python-dotenv
- loguru
- requests[socks] (кросс-платформенная синхронизация, поддержка SOCKS-прокси)
- parsedatetime
- recurrent
