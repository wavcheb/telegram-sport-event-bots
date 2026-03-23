# MAX Sport Event Bot

Бот для MAX Messenger для организации спортивных событий с регистрацией участников.

## Возможности

- Создание событий с датой и временем
- Регистрация участников через кнопки
- Добавление легионеров (гостей)
- Подтверждение оплаты
- Кросс-платформенная связка с Telegram ботом

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

Опциональные переменные:

```
# Страница оплаты
PAYMENTS_PAGE_URL=https://example.com/payments.php
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

| Команда | Описание |
|---------|----------|
| `/start` | Начало работы с ботом |
| `/event` | Создать новое событие |
| `/link` | Связать чат с Telegram чатом |
| `/unlink` | Отвязать чат |
| `/event_copy` | Синхронизировать участников из Telegram |
| `/payments` | Показать страницу оплаты |

## Кросс-платформенная связка

MAX и Telegram боты могут использовать общую базу данных и показывать участников с обеих платформ.

### Настройка связки

1. В Telegram чате выполните `/link` - бот выдаст секретный код
2. В MAX чате выполните `/link КОД` - чаты связаны
3. Теперь участники из обеих платформ видны в обоих чатах

### Синхронизация участников

Для копирования участников из Telegram события:

```
/event_copy
```

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

Создайте файл `/etc/systemd/system/max-sport-event-bot.service`:

```ini
[Unit]
Description=MAX Sport Event Bot
After=network.target mysql.service

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/usr/local/maxbot/sporteventbot
EnvironmentFile=/usr/local/maxbot/sporteventbot/.env
ExecStart=/usr/local/maxbot/sporteventbot/run.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Запуск:

```bash
sudo systemctl daemon-reload
sudo systemctl enable max-sport-event-bot
sudo systemctl start max-sport-event-bot
```

## Логи

Логи сохраняются в директории `logs/`.

```bash
tail -f logs/logs.log
```

## Зависимости

- Python 3.11+
- maxapi (MAX Messenger API)
- mysql-connector-python
- python-dotenv
- loguru
