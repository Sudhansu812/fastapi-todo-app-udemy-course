# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# activate the venv (named .totoenv in this project)
./.totoenv/Scripts/activate

# install dependencies (requirements.txt must stay UTF-8 — see Gotchas below)
pip install -r requirements.txt

# run the dev server (from the project root, not from src/)
uvicorn src.main:app --reload

# regenerate requirements.txt after installing a new package
pip freeze > requirements.txt
```

There is no test suite, linter, or migration tool configured yet.

## Architecture

FastAPI + SQLAlchemy (sync) + SQLite, layered as:

```
src/
├── main.py                    # assembles the app: lifespan, middleware, router mount — no business logic
├── core/                      # cross-cutting setup
│   ├── config.py              #   pydantic-settings Settings, loaded from env/.env
│   ├── database.py            #   engine, SessionLocal, Base, get_db() dependency
│   └── logging.py             #   JSON-formatted logger (console + file handler)
├── middleware/
│   └── logging.py             # LoggingMiddleware — logs method/path/status per request
├── models/                    # SQLAlchemy ORM classes (DB table shape)
├── schemas/                   # Pydantic request/response models (API contract)
├── crud/                      # data-access functions — plain functions taking a Session, no FastAPI imports
└── api/
    ├── deps.py                # shared FastAPI dependencies (e.g. db_dependency)
    └── v1/
        ├── api.py             # api_router — aggregates all v1 routers
        └── routers/           # route handlers — thin, delegate to crud/, validate via schemas/
```

Request flow: `api/v1/routers/*.py` → `crud/*.py` (DB access) → `models/*.py` (ORM) / `schemas/*.py` (response shape).

Key conventions to preserve when extending this structure:
- **Routers stay thin.** They resolve the DB session via `db_dependency` (from `src/api/deps.py`), call a `crud` function, and return data validated by a `schemas` model via `response_model`. No `db.query(...)` calls directly inside a router.
- **`crud/` functions are framework-agnostic.** They take a `Session` as a plain parameter and never import from `fastapi` — this keeps them callable from tests, scripts, or background jobs without a request context.
- **`models/` vs `schemas/`.** `models/` are SQLAlchemy ORM classes describing the DB table; `schemas/` are Pydantic models describing what the API accepts/returns. Never return an ORM instance directly from a route — go through a `schemas` `response_model`.
- **Table creation runs in `main.py`'s `lifespan` startup hook** (`Base.metadata.create_all`), not at import time. There are no Alembic migrations — schema changes currently mean editing a model and restarting the app (SQLite will not alter existing tables, so a schema change against an existing `todos.db` needs the DB file deleted or a manual migration).
- **`get_db()` in `core/database.py`** currently only yields and closes the session — it does not commit automatically. Any write endpoint (`POST`/`PUT`/`DELETE`) added to `crud/` must call `db.commit()` itself (or `get_db()` should be extended to commit/rollback centrally — decide this before adding the first write endpoint, to avoid partial-commit bugs across multi-write requests).

## Gotchas

- **`requirements.txt` must be UTF-8.** Regenerating it via PowerShell's `pip freeze > requirements.txt` writes UTF-16, which breaks `pip install -r requirements.txt` on most other tools/CI. Use `pip freeze | Out-File -Encoding utf8 requirements.txt` instead, or re-save as UTF-8 after freezing.
- **`env/.env` is gitignored** and holds real secrets (DB passwords); `env/.env.example` is the checked-in template with placeholder values — update both when adding a new setting.
- **`core/config.py` has unused MySQL/PostgreSQL/MSSQL settings and URL-builder properties.** Only `sqlite_url` is actually wired into `core/database.py`; the drivers for the other DBs (`pymysql`, `psycopg`, `pyodbc`) are not installed. These are kept intentionally for future use — don't assume they're dead code to delete, but don't assume they work either.
- **`todos.db` is gitignored** and created fresh on first run via the `lifespan` startup hook.
