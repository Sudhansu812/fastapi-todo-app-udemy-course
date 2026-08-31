FROM python:3.13-slim

WORKDIR /app

# Install dependencies first so this layer is cached unless requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Only copy what the app actually needs at runtime — no env/, tests, or local db files
# (see .dockerignore). alembic.ini + alembic/ are needed so migrations can run in-container.
COPY alembic.ini .
COPY alembic ./alembic
COPY src ./src

EXPOSE 8000

# Apply any pending migrations, then start the server. Config (CONNECTION_STRING, JWT_SECRET,
# etc.) is expected to come from real environment variables passed to `docker run -e ...` —
# no env/.env is copied into the image, so there's nothing to fall back to inside the container.
CMD ["sh", "-c", "alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port 8000"]
