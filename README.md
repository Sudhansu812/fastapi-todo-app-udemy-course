# Todo API — FastAPI + SQLAlchemy + SQLite + Alembic + JWT Auth

A small Todo REST API, restructured from a single-`main.py` course project into a layered structure closer to what you'd find in a real-world FastAPI codebase. This README walks through the project the way a course would — setup first, then each layer in the order a request actually flows through it, then the two things that got bolted on after the initial layering: JWT authentication and Alembic migrations.

## 1. Setup

```bash
mkdir todo-project3 && cd todo-project3
mkdir src
python -m venv .totoenv
./.totoenv/Scripts/activate      # Windows. On macOS/Linux: source .totoenv/bin/activate

python.exe -m pip install --upgrade pip
pip install -r requirements.txt
```

Copy `env/.env.example` to `env/.env` and fill in real values — `env/.env` is gitignored since it holds credentials, so this step doesn't happen automatically.

```bash
cp env/.env.example env/.env
```

Fill in at least `CONNECTION_STRING` (a `sqlite:///./<file>.db` URL is fine for local dev) and `JWT_SECRET` (any long random string — this signs every access token, see [Authentication](#8-authentication--authorization-jwt)).

Run the dev server from the project root (not from inside `src/`, since imports are rooted at `src.`):

```bash
uvicorn src.main:app --reload
```

Visit `http://127.0.0.1:8000/docs` for interactive Swagger docs. Unlike earlier versions of this project, tables are **not** created automatically on startup anymore — schema is managed by Alembic migrations. Run the migration once before starting the server the first time:

```bash
alembic upgrade head
```

See [Alembic migrations](#9-alembic-migrations) for the full workflow, including what to do after changing a model.

If you install a new package, regenerate `requirements.txt` carefully — see the note in [Gotchas](#10-gotchas--known-limitations) about encoding.

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
│   ├── __init__.py            #   imports every model so Base.metadata sees all of them
│   ├── todo.py
│   ├── user.py
│   ├── role.py
│   └── user_role.py           #   join table: which roles a user has
├── schemas/                   # Pydantic models — the API's request/response contract
│   ├── todo.py
│   └── user.py                #   also holds Token / TokenData for the JWT payload
├── crud/                      # data-access functions — the only layer that talks to the DB
│   ├── todo.py
│   └── auth.py                #   user lookup/creation for register + login
└── api/
    ├── deps.py                # shared FastAPI dependency: DB session injection
    ├── user_deps.py           # shared FastAPI dependency: current authenticated user
    └── v1/
        ├── api.py             # aggregates all v1 routers under one router
        └── routers/
            ├── todos.py       # route handlers — thin, delegate to crud/, require auth
            └── auth.py        # register / login / JWT issuing + decoding

alembic/                       # migration environment (see section 9)
├── env.py                     # wired to Base.metadata + settings.sqlite_url
└── versions/                  # one file per migration
alembic.ini                    # Alembic config — script location, logging
```

The course version of this project put config, DB setup, the ORM model, and the one route all inside (or one import away from) `main.py`. The idea behind splitting it up this way: each layer has exactly one reason to change. Changing the DB engine touches `core/database.py` only; adding a field to the API response touches `schemas/` only; changing a query touches `crud/` only.

## 3. `core/` — cross-cutting setup

Everything in `core/` is infrastructure that every other layer depends on, but that has no business logic of its own.

### `core/config.py` — typed settings

FastAPI apps typically read configuration (DB URLs, secrets, feature flags) from environment variables rather than hardcoding them, so the same code can run against different databases in dev/test/prod without editing source. `pydantic-settings` gives you a typed, validated way to do this:

```python
class Settings(BaseSettings):
    CONNECTION_STRING: str = "sqlite:///./todos.db"
    JWT_SECRET: str = ""
    ALGORITHM: str = "HS256"
    ...
    class Config:
        env_file = os.path.join(os.path.dirname(__file__), "..", "..", "env", ".env")

settings = Settings()
```

`Settings` reads from `env/.env` at import time; any field not set there falls back to its default. A single `settings` instance is created once and imported everywhere else that needs config — `sqlite_url` is the only URL currently wired up to an actual connection (see [Gotchas](#10-gotchas--known-limitations) for why the MySQL/Postgres/MSSQL properties exist but aren't used yet). `jwt_secret`/`algorithm` back the JWT signing described in [Authentication](#8-authentication--authorization-jwt) — both `core/database.py` (via `sqlite_url`) and `alembic/env.py` (via `sqlite_url` too) import this same `settings` object, so the DB URL only lives in one place.

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

- `engine` is the actual connection to SQLite; `Base` is the class every ORM model inherits from (it's how `Base.metadata` — and Alembic's autogenerate — know what tables should exist).
- `get_db()` is a **generator dependency** — FastAPI's mechanism for "set something up, hand it to the route, then clean up afterward." The code before `yield` runs before the route handler; the code after `yield` runs once the route handler has returned its result. That means every route using this dependency shares one open transaction for its entire duration: if the route (and whatever `crud` functions it calls) finishes without raising, `db.commit()` fires; if anything raises, `db.rollback()` fires instead and the exception re-propagates. This is what lets multi-step writes stay atomic without every `crud` function needing to remember to commit itself.

### `core/logging.py`

Sets up a `logging.Logger` that formats every record as JSON (timestamp, level, logger name, message) and writes it to both the console and a dated file under `LOG_DIR` (`./logs` by default).

## 4. `models/` vs `schemas/` — two different jobs

This split is the biggest structural difference from a typical course project, and worth being explicit about because the names sound similar but the jobs are not:

- **`models/todo.py`** is the SQLAlchemy ORM class — it describes what's actually in the `todos` table, including its foreign key to the user who owns it:
  ```python
  class Todos(Base):
      __tablename__ = "todos"
      id = Column(Integer, primary_key=True, index=True)
      title = Column(String)
      description = Column(String)
      priority = Column(Integer)
      complete = Column(Boolean, default=False)
      owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
  ```
- **`schemas/todo.py`** holds Pydantic models — they describe what the *API* accepts and returns, which is a separate concern from the DB schema even when the fields happen to line up today. Note `owner_id` never appears here — it's set server-side from the authenticated user, not something a client supplies:
  ```python
  class TodoResponse(BaseModel):
      model_config = ConfigDict(from_attributes=True)
      id: int
      title: str
      description: str
      priority: int
      complete: bool

  class TodoRequest(BaseModel):
      model_config = ConfigDict(from_attributes=True)
      title: str = Field(min_length=1, max_length=128)
      description: str = Field(min_length=1, max_length=356)
      priority: int = Field(gt=0, lt=6)
      complete: Optional[bool] = Field(default=False)
  ```

Why bother with two classes that look almost identical? A route should never return a raw ORM object directly — `response_model=TodoResponse` is what tells FastAPI to validate and reshape whatever a route returns into exactly this schema before it's serialized to JSON, silently dropping anything not declared on the schema (like SQLAlchemy's internal `_sa_instance_state`). `from_attributes=True` in a schema's `model_config` is what allows Pydantic to build itself from an ORM instance's attributes rather than requiring a plain dict. `TodoRequest` is the reverse direction — it validates incoming request bodies (`min_length`, `gt`/`lt` bounds, etc.) before any of that data reaches the database.

The same split applies to `models/user.py` / `schemas/user.py`: `UserResponse` deliberately has no `password` or `hashed_password` field, so a user's hash can never leak into an API response no matter what a route accidentally returns (see [Authentication](#8-authentication--authorization-jwt)).

### `models/role.py` and `models/user_role.py` — a many-to-many relationship

`roles` and `users` have a many-to-many relationship (a user can have more than one role, a role applies to more than one user), which SQLAlchemy models with a plain join/association table rather than a column on either side:

```python
class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id"), primary_key=True)
```

`UserRole` has no `id` column of its own — marking **both** `user_id` and `role_id` as `primary_key=True` makes the pair itself the primary key, which is what a pure join table wants: the database enforces that a given `(user_id, role_id)` combination can't be inserted twice, without needing a separate `UniqueConstraint`. `role.py` and `user_role.py` use the newer `Mapped[...]`/`mapped_column(...)` typed style rather than the plain `Column(...)` style in `todo.py`/`user.py` — both are valid SQLAlchemy 2.0 syntax; this project has both because they were added at different times, not because one is preferred.

These two models exist to support role-based access down the line, but nothing in `api/` currently reads from `roles`/`user_roles` yet — see [Gotchas](#10-gotchas--known-limitations).

### `models/__init__.py` — why it matters

```python
from src.models.todo import Todos
from src.models.user import User
from src.models.role import Role
from src.models.user_role import UserRole
```

`Base.metadata` (used by both Alembic's autogenerate and, previously, `create_all`) only knows about a model class once Python has actually imported that module — a class sitting unimported in a `.py` file doesn't register itself. Whichever entrypoint runs first (`main.py`, `alembic/env.py`, a script) needs `import src.models` to run *before* touching `Base.metadata`, so that all four model modules get imported together in one place instead of relying on whatever routers happen to import `crud/`, which happens to import `models/todo.py` but not the others. This bit the project once already: `users` silently never got created because nothing imported `models/user.py` until this `__init__.py` existed to force it.

## 5. `crud/` — the only layer that queries the database

```python
def get_todos(db: Session) -> list[Todos]:
    return db.query(Todos).all()

def get_todo_by_user(todo_id: int, user_id, db: Session) -> Todos:
    return db.query(Todos).filter(
        and_(Todos.id == todo_id, Todos.owner_id == user_id)
    ).first()

def get_todos_by_user(user_id, db: Session) -> list[Todos]:
    return db.query(Todos).filter(Todos.owner_id == user_id).all()

def create_todo(todo: TodoRequest, owner_id, db: Session) -> Todos:
    db_todo = Todos(**todo.model_dump(), owner_id=owner_id)
    db.add(db_todo)
    db.flush()
    db.refresh(db_todo)
    return db_todo

def update_todo(todo_id: int, todo: TodoRequest, user_id: int, db: Session) -> Todos | None:
    db_todo = get_todo_by_user(todo_id, user_id, db)
    if db_todo is None:
        return None
    for field, value in todo.model_dump().items():
        setattr(db_todo, field, value)
    db.flush()
    db.refresh(db_todo)
    return db_todo

def delete_todo(todo_id: int, user_id: int, db: Session) -> bool:
    db_todo = get_todo_by_user(todo_id, user_id, db)
    if not db_todo:
        return False
    db.delete(db_todo)
    db.flush()
    return True
```

Every function here takes a plain `Session` and has no `fastapi` import anywhere in the file. That's deliberate — these functions should be callable from a test, a script, or a background job without needing an HTTP request in flight. A few things worth noting:

- `create_todo` uses `Todos(**todo.model_dump())` to turn a validated `TodoRequest` into an ORM instance in one line, relying on the field names matching, then adds the caller-supplied `owner_id` — the request body never contains `owner_id` itself (see [`models/` vs `schemas/`](#4-models-vs-schemas--two-different-jobs)).
- `get_todo_by_user`/`update_todo`/`delete_todo` all filter on `owner_id == user_id` in the same query that looks the todo up, rather than fetching by id and checking ownership afterward — this makes "todo exists but belongs to someone else" and "todo doesn't exist" return the same `None`, which the router turns into the same `404` either way. That's deliberate: it avoids leaking whether a given todo id exists at all to a user who doesn't own it.
- None of these functions call `db.commit()`. They call `db.flush()` instead, which sends the SQL statement (`INSERT`/`UPDATE`/`DELETE`) to SQLite immediately — enough to make `db.refresh()` work and to make the change visible within the current transaction — without ending that transaction. The actual `commit()` happens once, centrally, in `get_db()` after the route returns (see [core/database.py](#3-core--cross-cutting-setup) above). This matters once a route needs more than one write: they commit or roll back together, rather than partially succeeding.
- `Session.add()` is only needed for objects the session doesn't know about yet (new, transient objects — see `create_todo`). Objects already loaded via a query (like inside `update_todo`) are already tracked, so mutating their attributes is enough for SQLAlchemy to pick up the change on the next flush — no `add()` call needed.

`crud/auth.py` follows the same pattern for users:

```python
def register_user(user: User, db: Session) -> User:
    db.add(user)
    db.flush()
    db.refresh(user)
    return user

def get_user_hashed_password(user_credentials: UserLoginRequest, db: Session) -> User | None:
    user = db.query(User).filter(
        or_(User.username == user_credentials.username, User.email == user_credentials.username)
    ).first()
    if not user:
        return None
    return user
```

`get_user_hashed_password` looks a user up by **either** username or email in one query (`or_(...)`) so the login form can accept either — the function name is a little misleading since it returns the whole `User` row, not just the hash; the router pulls `user.hashed_password` off of it afterward.

## 6. `api/` — routers, dependencies, and wiring

### `api/deps.py` — DB session dependency

```python
db_dependency = Annotated[Session, Depends(get_db)]
```

`Annotated[Session, Depends(get_db)]` is FastAPI's typed-dependency shorthand: any route parameter typed as `db: db_dependency` gets a `Session` injected by calling `get_db()`. Defining this once in `api/deps.py` and importing it means every router shares identical DB-session wiring instead of repeating `Depends(get_db)` in every file.

### `api/user_deps.py` — current-user dependency

```python
user_dependency = Annotated[TokenData, Depends(get_current_user)]
```

Same shorthand pattern, but for identity instead of the DB: `user: user_dependency` on a route resolves to a `TokenData` (see [`schemas/user.py`](#8-authentication--authorization-jwt)) by running `get_current_user` (defined in `api/v1/routers/auth.py`), which decodes and validates the caller's JWT. If the token is missing, malformed, or expired, that dependency raises before the route body ever runs — the dependency *is* the auth check, not something you additionally verify inside each handler (see [Authentication](#8-authentication--authorization-jwt) for the full mechanics).

### `api/v1/routers/todos.py` — the route handlers

```python
router = APIRouter(prefix="/todos", tags=["todos-sqlite"])

@router.get("/", response_model=list[TodoResponse], status_code=status.HTTP_200_OK)
async def get_all(db: db_dependency):
    return get_todos(db)

@router.get("/user_todos", response_model=list[TodoResponse], status_code=status.HTTP_200_OK)
async def get_all_user_todos(db: db_dependency, user: user_dependency):
    return get_todos_by_user(user.user_id, db)

@router.get("/todo/{todo_id}", response_model=TodoResponse, status_code=status.HTTP_200_OK)
async def get_by_id(db: db_dependency, user: user_dependency, todo_id: int = Path(gt=0)):
    todo = get_todo_by_user(todo_id, user.user_id, db)
    if not todo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Todo not found.")
    return todo

@router.post("/create", response_model=TodoResponse, status_code=status.HTTP_201_CREATED)
async def create(todo: TodoRequest, db: db_dependency, user: user_dependency):
    return create_todo(todo=todo, owner_id=user.user_id, db=db)

@router.put("/update/{todo_id}", response_model=TodoResponse, status_code=status.HTTP_200_OK)
async def update(db: db_dependency, user: user_dependency, new_todo: TodoRequest, todo_id: int = Path(gt=0)):
    updated_todo = update_todo(todo_id=todo_id, todo=new_todo, user_id=user.user_id, db=db)
    if updated_todo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such todo found.")
    return updated_todo

@router.delete("/remove/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(db: db_dependency, user: user_dependency, todo_id: int = Path(gt=0)):
    removed = delete_todo(todo_id, user.user_id, db)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such todo found.")
```

Every handler follows the same shape: pull a DB session via `db_dependency`, delegate to one `crud` function, and either return data (shaped by `response_model`) or raise `HTTPException` for the not-found case. No `db.query(...)` calls happen in this file — that's the actual point of having a `crud/` layer. `Path(gt=0)` validates the `{todo_id}` path parameter is a positive integer before the handler body even runs.

All write/scoped endpoints (everything except `GET /`) additionally take `user: user_dependency` — this both requires a valid access token (see above) and scopes the query to that user's own todos via `user.user_id`. `GET /` (list *all* todos, unscoped) is the one endpoint left without auth — worth revisiting once role-based access is wired up (see [Gotchas](#10-gotchas--known-limitations)).

### `api/v1/api.py` — aggregating routers

```python
api_router = APIRouter(prefix="/api")
api_router.include_router(todos_v1.router, prefix="/v1")
api_router.include_router(auth_v1.router, prefix="/v1")
```

This exists so `main.py` only has to mount one router (`api_router`), no matter how many resource routers get added under `api/v1/routers/`. Adding a new resource means creating `api/v1/routers/<resource>.py` and adding one `include_router(...)` line here — no changes to `main.py`.

## 7. `main.py` — assembling the app

```python
import src.models  # noqa: F401 — registers all models on Base.metadata before create_all

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(LoggingMiddleware)
app.include_router(api_router)
```

This is the only file that constructs the app, and it does nothing but wire together pieces built elsewhere:

- `lifespan` is FastAPI's startup/shutdown hook — an `async` generator where everything before `yield` runs once on startup and everything after runs on shutdown (nothing does here). `Base.metadata.create_all(bind=engine)` is now commented out: table creation is Alembic's job (see [Alembic migrations](#9-alembic-migrations)) rather than something the app does on every boot. The `import src.models` line stays even with `create_all` disabled, since other code (routers, `crud/`) still needs those model classes defined and registered on `Base.metadata` for ORM queries and relationships to work.
- `add_middleware(LoggingMiddleware)` wraps every request/response in the logger from `middleware/logging.py`.
- `include_router(api_router)` mounts every versioned route from `api/v1/api.py`.

## 8. Authentication & authorization (JWT)

Two endpoints under `/api/v1/auth`, plus one dependency (`get_current_user`) that every protected `todos` route relies on.

### Registering (`POST /auth/create`)

```python
@router.post("/create", status_code=status.HTTP_201_CREATED)
async def register_user(db: db_dependency, user: UserRequest):
    create_user_model = User(
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
        username=user.username,
        hashed_password=__hash_password(user.password),
        is_active=True,
    )
    return create_user(create_user_model, db)
```

`__hash_password` calls `bcrypt_context.hash(password)` — a `passlib.context.CryptContext` configured for the `bcrypt` scheme. The plaintext password from the request is never stored; only the bcrypt hash is. **bcrypt hashes are salted and non-deterministic** — hashing the same password twice produces two different strings, because the salt is embedded in the hash's own output (`$2b$<cost>$<salt><hash>`). That's fine, because verifying a password never re-hashes and string-compares; it extracts the salt/cost that's already embedded in the *stored* hash and re-derives from that, which is what `bcrypt_context.verify(plain, stored_hash)` does under the hood.

### Logging in (`POST /auth/authenticate`)

```python
@router.post("/authenticate", response_model=Token, status_code=status.HTTP_200_OK)
async def authenticate(db: db_dependency, user_credentials: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = get_user_hash(UserLoginRequest(username=user_credentials.username, password=user_credentials.password), db)
    if not user:
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username / email.")
    if not __verify_password(user_credentials.password, user.hashed_password):
        return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password.")
    token = __create_access_token(username=user.username, user_id=user.id, expires_delta=timedelta(minutes=30))
    return token
```

`OAuth2PasswordRequestForm` is a FastAPI-provided dependency that parses a standard OAuth2 login request — **form-encoded** (`application/x-www-form-urlencoded`), not JSON, with `username` and `password` fields. That's why `python-multipart` has to be installed: FastAPI needs it to parse any `Form(...)`-based request body, and `OAuth2PasswordRequestForm` is built on `Form(...)` under the hood — without it, hitting this endpoint raises `RuntimeError: Form data requires "python-multipart" to be installed` at request time, not at import time.

`__create_access_token` builds a JWT with `python-jose`:

```python
def __create_access_token(username: str, user_id: int, expires_delta: timedelta) -> Token:
    encode = {'sub': username, 'id': user_id}
    encode.update({'exp': datetime.now(timezone.utc) + expires_delta})
    jwt_token = jwt.encode(encode, app_config.jwt_secret, algorithm=app_config.algorithm)
    return Token(access_token=jwt_token, token_type="bearer")
```

The token's payload (`sub`, `id`, `exp`) is signed (not encrypted) with `JWT_SECRET` — anyone can decode and read it, but can't forge or alter it without knowing the secret. `exp` is what makes the token expire after 30 minutes; `jose` checks this automatically on decode.

### Protecting a route (`get_current_user` + `OAuth2PasswordBearer`)

```python
oauth2_bearer = OAuth2PasswordBearer(tokenUrl='api/v1/auth/authenticate')

async def get_current_user(token: Annotated[str, Depends(oauth2_bearer)]):
    try:
        payload = jwt.decode(token, app_config.jwt_secret, algorithms=[app_config.algorithm])
        username = payload.get('sub')
        user_id = payload.get('id')
        if username is None or user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials.")
        return TokenData(user_id=user_id, username=username)
    except JWTError as je:
        raise HTTPException(status_code=401, detail="Could not validate credentials.") from je
```

`OAuth2PasswordBearer(tokenUrl=...)` does two things:
1. At runtime, it reads the `Authorization: Bearer <token>` header off incoming requests and hands the raw token string to whatever depends on it (`get_current_user` here). If the header is **missing entirely**, it raises `HTTPException(401, "Not authenticated")` itself — before `get_current_user`'s body even runs, which is why a request with no `Authorization` header at all gets that generic message instead of the custom one above; the custom message only fires once a token *is* present but turns out invalid or expired.
2. It tells **Swagger's "Authorize" lock button** where to POST a username/password to get a token. `tokenUrl` must match the actual login route's full path (including the router's `/api/v1` prefix) — pointing it at the wrong path is a common mistake and shows up as Swagger's login form POSTing to a URL that 404s.

Because `get_current_user` either returns a valid `TokenData` or raises, any route with `user: user_dependency` in its signature is guaranteed a valid, non-`None` identity by the time its body runs — there's no need for an `if user is None:` check inside the handler; the dependency resolution *is* the authorization gate (see `api/user_deps.py` above). This is the same shape as an `[Authorize]` attribute in ASP.NET: to require auth on every route in a router without adding a parameter to each one, attach the dependency at the router level instead — `APIRouter(dependencies=[Depends(get_current_user)])`.

## 9. Alembic migrations

This project used to create tables via `Base.metadata.create_all(bind=engine)` in `main.py`'s `lifespan` hook. That approach can't express schema *changes* — SQLite (and `create_all` in general) will only create tables that don't exist yet; it never alters an existing one. Alembic replaces that with versioned, incremental migration files.

### One-time setup, step by step (already done in this repo — here's how it got there)

**Step 1 — install it** (from the project root, venv active, same as any other dependency):

```bash
pip install alembic
pip freeze | Out-File -Encoding utf8 requirements.txt   # keep requirements.txt UTF-8, see Gotchas
```

**Step 2 — scaffold the migration environment:**

```bash
alembic init alembic
```

This must be run from the project root (the same directory as `requirements.txt`), and it creates:

```
alembic.ini            # Alembic's own config — script location, logging, and (by default) the DB URL
alembic/
├── env.py              # the script that actually runs on every alembic command — this is what
│                        #   connects Alembic to a real database and to your models
├── script.py.mako      # template used to generate each new migration file
└── versions/           # empty at first — one file per migration will live here
```

Nothing here is wired to *this* project yet — it's a generic scaffold. Two things need fixing before autogenerate will work, and both live in `alembic/env.py`.

**Step 3 — point `env.py` at this project's models and database.** Out of the box, `env.py` has:

```python
# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = None
```

`target_metadata = None` means Alembic has nothing to diff your models against — every `--autogenerate` call would silently produce an empty migration. Fix it by importing this project's `Base` and models, near the top of `env.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # project root importable

import src.models  # noqa: F401 — registers all models on Base.metadata
from src.core.config import settings as app_config
from src.core.database import Base

target_metadata = Base.metadata  # instead of the template's `None`
```

The `sys.path.insert(...)` line matters because `alembic/env.py` doesn't otherwise know how to resolve `src.*` imports — it isn't run as part of the `src` package, so without this, `import src.models` raises `ModuleNotFoundError`.

**Step 4 — point `env.py` at the real database URL.** `alembic.ini` ships with a placeholder:

```ini
sqlalchemy.url = driver://user:pass@localhost/dbname
```

If you leave that as-is (or fill in the ini file directly), you'd end up hardcoding a second copy of the DB URL that has to be kept in sync with `env/.env` by hand. Instead, override it in `env.py` from the app's own settings, right after `config = context.config` is defined:

```python
from src.core.config import settings as app_config

config.set_main_option("sqlalchemy.url", app_config.sqlite_url)
```

Skipping this step is the single most common way `alembic revision --autogenerate` fails on a fresh setup — it raises `sqlalchemy.exc.NoSuchModuleError: Can't load plugin: sqlalchemy.dialects:driver`, because Alembic is trying to load a database dialect literally named `driver` straight out of the placeholder string.

**Step 5 — sanity-check the wiring** before trusting autogenerate with anything:

```bash
alembic current      # should run without error and print "(no revisions)" / current revision
```

If this errors, re-check steps 3–4 before moving on — `revision --autogenerate` will fail the same way.

**Step 6 — generate and apply the first migration:**

```bash
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```

See [Gotcha: autogenerate diffs against the current DB, not "nothing"](#gotcha-autogenerate-diffs-against-the-current-db-not-nothing) below if this produces an empty migration — it means Alembic compared your models against a database that already had these tables in it (e.g. from an earlier `create_all()` run).

### Day-to-day workflow

After changing a model (adding a column, a table, a constraint, etc.):

```bash
# 1. Generate a migration by diffing your models against the live DB
alembic revision --autogenerate -m "short description of the change"

# 2. Open the generated file under alembic/versions/ and read it —
#    autogenerate is a helpful diff, not a guarantee; it can miss
#    things like renamed columns (sees them as a drop + an add) or
#    unnamed constraints.

# 3. Apply it
alembic upgrade head
```

Other commands worth knowing:

```bash
alembic downgrade -1        # revert the most recent migration
alembic history              # list all migrations in order
alembic current              # show which migration the DB is currently at
```

### Seeding reference data (e.g. default roles)

Autogenerate only ever produces *schema* changes (`CREATE TABLE`, `ADD COLUMN`, etc.) — it never inserts rows, because there's nothing in your models for it to diff against for actual data. Seeding fixed reference data (like the `admin`/`user` rows in `roles`) is a **data migration**: a migration file you write by hand rather than autogenerate, using `op.bulk_insert(...)` in `upgrade()` and the matching cleanup in `downgrade()`.

**Step 1 — create a blank revision** (no `--autogenerate`, since there's no schema change to detect):

```bash
alembic revision -m "seed default roles"
```

**Step 2 — fill in `upgrade()`/`downgrade()`** in the generated file under `alembic/versions/`:

```python
roles_table = sa.table(
    "roles",
    sa.column("code", sa.String),
    sa.column("name", sa.String),
    sa.column("description", sa.String),
    sa.column("is_active", sa.Boolean),
)

DEFAULT_ROLES = [
    {"code": "admin", "name": "Administrator", "description": "Full access to all resources.", "is_active": True},
    {"code": "user", "name": "User", "description": "Standard access — can manage their own todos.", "is_active": True},
]

def upgrade() -> None:
    op.bulk_insert(roles_table, DEFAULT_ROLES)

def downgrade() -> None:
    codes = [role["code"] for role in DEFAULT_ROLES]
    op.execute(roles_table.delete().where(roles_table.c.code.in_(codes)))
```

`sa.table(...)`/`sa.column(...)` here are lightweight, migration-local table definitions — deliberately **not** an import of `src.models.role.Role`. This is a real Alembic convention, not a shortcut: a migration has to keep working correctly years from now even after the actual `Role` model has changed shape or been renamed, so migrations describe the schema as it looked *at that point in history*, independent of whatever the current model file says today. `op.bulk_insert` then generates a plain `INSERT` against that table shape, and `id`/`created_at` are left out of both the `sa.table()` definition and the row dicts — `id` autoincrements and `created_at` has a `server_default=func.now()`, so the database fills both in itself.

**Step 3 — apply it** the same way as any other migration:

```bash
alembic upgrade head
```

`downgrade()` deletes the seeded rows by their `code`, so `alembic downgrade -1` cleanly undoes just the seeding without touching the `roles` table's schema. This is why a hand-written data migration is preferable to a one-off script here: seeding, re-running on a fresh clone, and reverting are all just the normal Alembic commands, and the seed data ships in version control alongside the schema it depends on.

### First-time setup on a fresh clone

There's no `todosapp.db` yet, and no tables in it. Instead of `create_all`, run:

```bash
alembic upgrade head
```

This replays every migration under `alembic/versions/` in order, building the schema from scratch.

### Gotcha: autogenerate diffs against the current DB, not "nothing"

`alembic revision --autogenerate` compares your models to whatever the **currently connected database** already looks like — not to an assumed-empty baseline. If you already ran `Base.metadata.create_all()` once (from before Alembic was introduced) and then generate an "initial migration" against that same, already-fully-created database, Alembic will correctly see *no difference* and emit an empty `upgrade()`/`downgrade()` — which is useless as a true initial migration for anyone starting from an empty DB. The fix used to bootstrap this project's first migration: delete the SQLite file so it's genuinely empty, then autogenerate against it so Alembic sees every table as newly added.

## 10. Gotchas & known limitations

- **No more `create_all()`.** Schema changes now go through Alembic (see above) — `Base.metadata.create_all()` in `main.py` is commented out, not deleted, as a reminder of what it used to do.
- **`requirements.txt` must stay UTF-8.** Regenerating it via PowerShell's `pip freeze > requirements.txt` writes UTF-16, which breaks `pip install -r requirements.txt` for most other tools/CI. Use `pip freeze | Out-File -Encoding utf8 requirements.txt` instead.
- **`bcrypt` is pinned to `4.0.1`.** `passlib` 1.7.4 (the latest release, unmaintained since 2020) reads a `bcrypt.__about__.__version__` attribute to detect the backend version; that attribute was removed in `bcrypt` 4.1.0+, so anything newer breaks password hashing/verification with `AttributeError: module 'bcrypt' has no attribute '__about__'`.
- **`python-multipart` is required** for `OAuth2PasswordRequestForm` (used by `/auth/authenticate`) — any `Form(...)`-based endpoint needs it, and FastAPI only raises the missing-dependency error at request time, not at import/startup time.
- **`core/config.py` has unused MySQL/PostgreSQL/MSSQL settings** and URL-builder `@property` methods. Only `sqlite_url` is wired into `core/database.py`; the other drivers (`pymysql`, `psycopg`, `pyodbc`) aren't installed. These are kept intentionally for future use, not dead code to delete — but they don't work yet either.
- **`env/.env` and `todosapp.db` are gitignored**, `env/.env.example` is the checked-in template. Update both when adding a new setting.
- **`PUT /update/{todo_id}` is a full replace**, not a partial update — `TodoRequest` requires `title`/`description`/`priority` on every update call. A `PATCH` endpoint with an all-optional schema would be the way to support partial updates later.
- **`Role`/`UserRole` exist as tables but nothing reads them yet.** `User` no longer has a `role` column (roles moved to the `roles`/`user_roles` join table), but `UserRequest`/`UserResponse` still declare a `role: Optional[str]` field, and `TokenData.role` is typed `list[str]` while nothing currently populates it from `user_roles`. Wiring up role-based access (reading a user's roles via `UserRole`, embedding them in the JWT, checking them in `get_current_user` or a new dependency) is the natural next step, and worth doing before relying on `role` anywhere in `auth.py` — right now that field is vestigial from before the join table was introduced.
- **`GET /api/v1/todos/` (list-all) has no auth check**, unlike every other `todos` route. It returns every user's todos to anyone who calls it, unauthenticated. Worth adding `user: user_dependency` (and probably an admin-role check once roles are wired up) before this goes anywhere near production.

## 11. Current endpoints

| Method | Path                              | Auth required | Description                          |
|--------|------------------------------------|:---:|---------------------------------------|
| POST   | `/api/v1/auth/create`             |     | Register a new user                   |
| POST   | `/api/v1/auth/authenticate`       |     | Log in (form-encoded), get a JWT      |
| GET    | `/api/v1/todos/`                  |     | List **all** todos (see Gotchas)      |
| GET    | `/api/v1/todos/user_todos`        | ✅  | List the current user's todos         |
| GET    | `/api/v1/todos/todo/{todo_id}`    | ✅  | Get one of the current user's todos   |
| POST   | `/api/v1/todos/create`            | ✅  | Create a todo, owned by current user  |
| PUT    | `/api/v1/todos/update/{todo_id}`  | ✅  | Replace one of the current user's todos (full update) |
| DELETE | `/api/v1/todos/remove/{todo_id}`  | ✅  | Delete one of the current user's todos |

For an auth-required route, click **Authorize** in Swagger (`/docs`), then log in with the username and password from `/auth/create` — Swagger POSTs to `/auth/authenticate` behind the scenes and attaches the resulting token to subsequent requests automatically.
