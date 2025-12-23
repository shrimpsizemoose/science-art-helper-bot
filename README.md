# Workshop Signup Bot

Telegram-бот для регистрации участников на воркшопы и вебинары.
Наверное, его можно использовать и не только для задач мастерской Science Art, но мне мало представляется это возможным.

## Возможности

- Регистрация через deep link (`t.me/bot?start=event_code`)
- Кастомный вопрос при регистрации (текст или варианты ответа), который потом виден админам
- Рассылка напоминаний участникам
- Можно отменить регистрацию есличо
- Статистика и экспорт в CSV
- Локально можно с sqlite (разработка), в проде на postgresql

## Квикстарт

```bash
uv sync

cp .env.example .env
# .env: BOT_TOKEN, DATABASE_URL, CONFIG_PATH
# config.toml: admin_ids, ну и остальное тоже

uv run python -m src.main
```

## Конфигурация

### Переменные окружения (.env)

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен бота (от @BotFather) |
| `DATABASE_URL` | `sqlite:///bot.db` или `postgresql://user:pass@host:5432/db` |
| `CONFIG_PATH` | Путь к config.toml |

### PostgreSQL (для прода)

```sql
-- Подключиться к postgres и создать юзера/базу
CREATE USER workshop_bot WITH PASSWORD 'your_secure_password';
CREATE DATABASE workshop_bot OWNER workshop_bot;
```

Тогда `DATABASE_URL=postgresql://workshop_bot:your_secure_password@host:5432/workshop_bot`

Таблицы создадутся автоматически при первом запуске бота.

### Настройки (config.toml)

```toml
[bot]
admin_ids = [123456789]  # Telegram ID администраторов
# admin_group_id = -1001234567890  # Группа где можно тоже писать админ-команды (опционально)

[system_messages]
no_active_event = "Нет активных мероприятий."
event_not_available = "Регистрация закрыта."

[default_event_messages]
registration_success = "Вы зарегистрированы на {event_title}!"
already_registered = "Вы уже зарегистрированы на {event_title}."
cancel_button_text = "Не смогу прийти"
cancel_confirmation = "Хорошо, вы отписаны от {event_title}."
```

## Команды бота

### Для пользователей

| Команда | Описание |
|---------|----------|
| `/start <code>` | Регистрация на мероприятие |
| `/start` | Информация о текущем мероприятии |

### Для администраторов

| Команда | Описание |
|---------|----------|
| `/newevent` | Создать новое мероприятие (интерактивно) |
| `/endevent` | Завершить текущее мероприятие |
| `/broadcast` | Отправить сообщение всем участникам |
| `/stats` | Статистика регистраций |
| `/export` | Экспорт участников в CSV |

## Docker

Ну вообще он тут должен сам собираться через github actions, но можно локально тоже:

```bash
docker build -t workshop-bot:v1.0 .

docker run -d \
  -e BOT_TOKEN=your_token_yopt \
  -e DATABASE_URL=sqlite:///data/bot.db \
  -e CONFIG_PATH=/app/config.toml \
  -v $(pwd)/config.toml:/app/config.toml:ro \
  -v bot-data:/app/data \
  workshop-bot:v1.0
```

## Разработка: можно линтить всякое

```bash
uv sync
uv run ruff check src/
uv run pytest
```

## Лицензия

Можно делать что угодно: [WTFPL](LICENSE)
