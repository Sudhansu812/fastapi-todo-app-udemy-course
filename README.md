# Todo API — FastAPI + SQLAlchemy + SQLite

A small Todo REST API, restructured from a single-`main.py` course project into a layered
structure closer to what you'd find in a real-world FastAPI codebase. This README walks through
the project the way a course would — setup first, then each layer in the order a request actually
flows through it.

## 1. Setup

```bash
mkdir todo-project3 && cd todo-project3
mkdir src
python -m venv .totoenv
./.totoenv/Scripts/activate      # Windows. On macOS/Linux: source .totoenv/bin/activate

python.exe -m pip install --upgrade pip
pip install -r requirements.txt
```

Copy `env/.env.example` to `env/.env` and fill in real values — `env/.env` is gitignored since it
holds credentials, so this step doesn't happen automatically.

```bash
cp env/.env.example env/.env
```

Run the dev server from the project root (not from inside `src/`, since imports are rooted at `src.`):

```bash
uvicorn src.main:app --reload
```

Visit `http://127.0.0.1:8000/docs` for interactive Swagger docs. On first startup, `todos.db`
(SQLite) is created automatically along with the `todos` table — no manual migration step exists
yet (see [Gotchas](#7-gotchas--known-limitations)).

If you install a new package, regenerate `requirements.txt` carefully — see the note in
[Gotchas](#7-gotchas--known-limitations) about encoding.

## 2. Folder structure

```
src/
├── main.py                    # assembles the app — no business logic lives here
├── core/                      # cross-cutting setup, used by every other layer
│   ├── config.py              #   typed settings, loaded from env/.env
│   ├── database.py            #   SQLAlchemy engine/session + transaction handling
│   └── logging.py             #   JSON logger (console + file)
├── middleware/
│   └── logging.py             # logs method/path/status for every request
├── models/                    # SQLAlchemy ORM classes — the DB table shape
│   └── todo.py
├── schemas/                   # Pydantic models — the API's request/response contract
│   └── todo.py
├── crud/                      # data-access functions — the only layer that talks to the DB
│   └── todo.py
└── api/
    ├── deps.py                # shared FastAPI dependencies (e.g. DB session injection)
    └── v1/
        ├── api.py             # aggregates all v1 routers under one router
        └── routers/
            └── todos.py       # route handlers — thin, delegate to crud/
```

The course version of this project put config, DB setup, the ORM model, and the one route all
inside (or one import away from) `main.py`. The idea behind splitting it up this way: each layer
has exactly one reason to change. Changing the DB engine touches `core/database.py` only; adding a
field to the API response touches `schemas/` only; changing a query touches `crud/` only.

## 3. `core/` — cross-cutting setup

Everything in `core/` is infrastructure that every other layer depends on, but that has no
business logic of its own.

### `core/config.py` — typed settings

FastAPI apps typically read configuration (DB URLs, secrets, feature flags) from environment
variables rather than hardcoding them, so the same code can run against different databases in
dev/test/prod without editing source. `pydantic-settings` gives you a typed, validated way to do
this:

```python
class Settings(BaseSettings):
    CONNECTION_STRING: str = "sqlite:///./todos.db"
    ...
    class Config:
        env_file = os.path.join(os.path.dirname(__file__), "..", "..", "env", ".env")

settings = Settings()
```

`Settings` reads from `env/.env` at import time; any field not set there falls back to its default.
A single `settings` instance is created once and imported everywhere else that needs config —
`sqlite_url` is the only URL currently wired up to an actual connection (see
[Gotchas](#7-gotchas--known-limitations) for why the MySQL/Postgres/MSSQL properties exist but
aren't used yet).

### `core/database.py` — engine, session, and the transaction boundary

```python
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={'check_same_thread': False})
SessionLocal = sessionmaker(autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

- `engine` is the actual connection to SQLite; `Base` is the class every ORM model inherits from
  (it's how `Base.metadata.create_all(...)` in `main.py` knows what tables to create).
- `get_db()` is a **generator dependency** — FastAPI's mechanism for "set something up, hand it to
  the route, then clean up afterward." The code before `yield` runs before the route handler; the
  code after `yield` runs once the route handler has returned its result. That means every route
  using this dependency shares one open transaction for its entire duration: if the route (and
  whatever `crud` functions it calls) finishes without raising, `db.commit()` fires; if anything
  raises, `db.rollback()` fires instead and the exception re-propagates. This is what lets
  multi-step writes stay atomic without every `crud` function needing to remember to commit itself.

### `core/logging.py`

Sets up a `logging.Logger` that formats every record as JSON (timestamp, level, logger name,
message) and writes it to both the console and a dated file under `LOG_DIR` (`./logs` by default).

## 4. `models/` vs `schemas/` — two different jobs

This split is the biggest structural difference from a typical course project, and worth being
explicit about because the names sound similar but the jobs are not:

- **`models/todo.py`** is the SQLAlchemy ORM class — it describes what's actually in the
  `todos` table:
  ```python
  class Todos(Base):
      __tablename__ = "todos"
      id = Column(Integer, primary_key=True, index=True)
      title = Column(String)
      description = Column(String)
      priority = Column(Integer)
      complete = Column(Boolean, default=False)
  ```
- **`schemas/todo.py`** holds Pydantic models — they describe what the *API* accepts and returns,
  which is a separate concern from the DB schema even when the fields happen to line up today:
  ```python
  class TodoResponse(BaseModel):
      model_config = ConfigDict(from_attributes=True)
      id: int
      title: str
      description: str
      priority: int
      complete: bool

  class TodoRequest(BaseModel):
      title: str = Field(min_length=1, max_length=128)
      description: str = Field(min_length=1, max_length=356)
      priority: int = Field(gt=0, lt=6)
      complete: Optional[bool] = Field(default=False)
  ```

Why bother with two classes that look almost identical? A route should never return a raw ORM
object directly — `response_model=TodoResponse` is what tells FastAPI to validate and reshape
whatever a route returns into exactly this schema before it's serialized to JSON, silently
dropping anything not declared on the schema (like SQLAlchemy's internal `_sa_instance_state`).
`from_attributes=True` in `TodoResponse.model_config` is what allows Pydantic to build itself from
an ORM instance's attributes rather than requiring a plain dict. `TodoRequest` is the reverse
direction — it validates incoming request bodies (`min_length`, `gt`/`lt` bounds, etc.) before any
of that data reaches the database.

## 5. `crud/` — the only layer that queries the database

```python
def get_todos(db: Session) -> list[Todos]:
    return db.query(Todos).all()

def get_todo(todo_id: int, db: Session) -> Todos:
    return db.query(Todos).filter(Todos.id == todo_id).first()

def create_todo(todo: TodoRequest, db: Session) -> Todos:
    db_todo = Todos(**todo.model_dump())
    db.add(db_todo)
    db.flush()
    db.refresh(db_todo)
    return db_todo

def update_todo(todo_id: int, todo: TodoRequest, db: Session) -> Todos | None:
    db_todo = get_todo(todo_id, db)
    if db_todo is None:
        return None
    for field, value in todo.model_dump().items():
        setattr(db_todo, field, value)
    db.flush()
    db.refresh(db_todo)
    return db_todo

def delete_todo(todo_id: int, db: Session) -> bool:
    db_todo = get_todo(todo_id, db)
    if not db_todo:
        return False
    db.delete(db_todo)
    db.flush()
    return True
```

Every function here takes a plain `Session` and has no `fastapi` import anywhere in the file. That's
deliberate — these functions should be callable from a test, a script, or a background job without
needing an HTTP request in flight. A few things worth noting:

- `create_todo` uses `Todos(**todo.model_dump())` to turn a validated `TodoRequest` into an ORM
  instance in one line, relying on the field names matching.
- None of these functions call `db.commit()`. They call `db.flush()` instead, which sends the SQL
  statement (`INSERT`/`UPDATE`/`DELETE`) to SQLite immediately — enough to make `db.refresh()` work
  and to make the change visible within the current transaction — without ending that transaction.
  The actual `commit()` happens once, centrally, in `get_db()` after the route returns (see
  [core/database.py](#3-core--cross-cutting-setup) above). This matters once a route needs more
  than one write: they commit or roll back together, rather than partially succeeding.
- `update_todo` and `delete_todo` both reuse `get_todo()` rather than re-querying — one function
  owns "how do I look up a todo by id."
- `Session.add()` is only needed for objects the session doesn't know about yet (new, transient
  objects — see `create_todo`). Objects already loaded via a query (like inside `update_todo`) are
  already tracked, so mutating their attributes is enough for SQLAlchemy to pick up the change on
  the next flush — no `add()` call needed.

## 6. `api/` — routers, dependencies, and wiring

### `api/deps.py` — shared dependencies

```python
db_dependency = Annotated[Session, Depends(get_db)]
```

`Annotated[Session, Depends(get_db)]` is FastAPI's typed-dependency shorthand: any route parameter
typed as `db: db_dependency` gets a `Session` injected by calling `get_db()`. Defining this once in
`api/deps.py` and importing it means every router shares identical DB-session wiring instead of
repeating `Depends(get_db)` in every file.

### `api/v1/routers/todos.py` — the route handlers

```python
router = APIRouter(prefix="/todos", tags=["todos-sqlite"])

@router.get("/", response_model=list[TodoResponse], status_code=status.HTTP_200_OK)
async def get_all(db: db_dependency):
    return get_todos(db)

@router.get("/todo/{todo_id}", response_model=TodoResponse, status_code=status.HTTP_200_OK)
async def get_by_id(db: db_dependency, todo_id: int = Path(gt=0)):
    todo = get_todo(todo_id, db)
    if not todo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such todo found.")
    return todo

@router.post("/create", response_model=TodoResponse, status_code=status.HTTP_201_CREATED)
async def create(todo: TodoRequest, db: db_dependency):
    return create_todo(todo=todo, db=db)

@router.put("/update/{todo_id}", response_model=TodoResponse, status_code=status.HTTP_200_OK)
async def update(db: db_dependency, new_todo: TodoRequest, todo_id: int = Path(gt=0)):
    updated_todo = update_todo(todo_id=todo_id, todo=new_todo, db=db)
    if updated_todo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such todo found.")
    return updated_todo

@router.delete("/remove/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(db: db_dependency, todo_id: int = Path(gt=0)):
    removed = delete_todo(todo_id, db)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such todo found.")
```

Every handler follows the same shape: pull a DB session via `db_dependency`, delegate to one
`crud` function, and either return data (shaped by `response_model`) or raise `HTTPException` for
the not-found case. No `db.query(...)` calls happen in this file — that's the actual point of
having a `crud/` layer.

`Path(gt=0)` validates the `{todo_id}` path parameter is a positive integer before the handler body
even runs; a request with `todo_id=0` or a non-integer never reaches `get_todo`/`update_todo`.

### `api/v1/api.py` — aggregating routers

```python
api_router = APIRouter(prefix="/api")
api_router.include_router(todos_v1.router, prefix="/v1")
```

This exists so `main.py` only has to mount one router (`api_router`), no matter how many resource
routers (`todos`, and eventually others) get added under `api/v1/routers/`. Adding a new resource
means creating `api/v1/routers/<resource>.py` and adding one `include_router(...)` line here — no
changes to `main.py`.

### Current endpoints

| Method | Path                          | Description         |
|--------|-------------------------------|----------------------|
| GET    | `/api/v1/todos/`              | List all todos       |
| GET    | `/api/v1/todos/todo/{todo_id}`| Get one todo by id    |
| POST   | `/api/v1/todos/create`        | Create a todo         |
| PUT    | `/api/v1/todos/update/{todo_id}`| Replace a todo (full update) |
| DELETE | `/api/v1/todos/remove/{todo_id}`| Delete a todo        |

## 7. `main.py` — assembling the app

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(LoggingMiddleware)
app.include_router(api_router)
```

This is the only file that constructs the app, and it does nothing but wire together pieces built
elsewhere:

- `lifespan` is FastAPI's startup/shutdown hook — an `async` generator where everything before
  `yield` runs once on startup and everything after runs on shutdown (nothing does here).
  `Base.metadata.create_all(bind=engine)` creates any table that doesn't exist yet, based on every
  model that inherits from `Base`. Running this inside `lifespan` (rather than as a bare statement
  at module import time, which is what the course version did) ties it to the app's actual
  lifecycle — it fires when the app starts, not the instant something imports `models`.
- `add_middleware(LoggingMiddleware)` wraps every request/response in the logger from
  `middleware/logging.py`.
- `include_router(api_router)` mounts every versioned route from `api/v1/api.py`.

## 8. Gotchas & known limitations

- **No migrations.** `Base.metadata.create_all()` only creates tables that don't exist — it will
  not alter an existing table if you change a model's columns. A real schema change against an
  existing `todos.db` currently means deleting the file (data loss) or hand-editing it. Alembic
  would be the standard next step if this project grows.
- **`requirements.txt` must stay UTF-8.** Regenerating it via PowerShell's
  `pip freeze > requirements.txt` writes UTF-16, which breaks `pip install -r requirements.txt` for
  most other tools/CI. Use `pip freeze | Out-File -Encoding utf8 requirements.txt` instead.
- **`core/config.py` has unused MySQL/PostgreSQL/MSSQL settings** and URL-builder `@property`
  methods. Only `sqlite_url` is wired into `core/database.py`; the other drivers (`pymysql`,
  `psycopg`, `pyodbc`) aren't installed. These are kept intentionally for future use, not dead code
  to delete — but they don't work yet either.
- **`env/.env` and `todos.db` are gitignored**, `env/.env.example` is the checked-in template.
  Update both when adding a new setting.
- **`PUT /update/{todo_id}` is a full replace**, not a partial update — `TodoRequest` requires
  `title`/`description`/`priority` on every update call. A `PATCH` endpoint with an all-optional
  schema would be the way to support partial updates later.
