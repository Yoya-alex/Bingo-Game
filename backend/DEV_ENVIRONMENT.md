# Development Environment (Separate Processes)

Use this setup when you want to run web server, game engine, and bot separately with local PostgreSQL.

## 1) Prepare development env file

Copy:

- `.env.development.example` -> `.env.development`

Then edit `.env.development` and set:

- `BOT_TOKEN` to your real Telegram bot token
- Local PostgreSQL credentials (`DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`)

Important:

- Keep `DATABASE_URL=` empty in `.env.development` to force local PostgreSQL via `DB_*`.

## 2) Create local PostgreSQL database

Example SQL:

```sql
CREATE DATABASE bingo_bot_dev;
```

## 3) Run migrations

From `backend/`:

```bash
python manage.py migrate
```

## 4) Start services in separate terminals

Terminal 1 (web server only):

```bash
python start_dev_server.py
```

Terminal 2 (game engine only):

```bash
python start_dev_engine.py
```

Terminal 3 (bot only):

```bash
python start_dev_bot.py
```

## Notes

- `manage.py runserver` no longer auto-starts bot/engine unless `AUTO_START_GAME_SERVICES=1`.
- For one-process production-style startup, continue using existing production scripts.
