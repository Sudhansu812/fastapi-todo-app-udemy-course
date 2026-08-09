from contextlib import asynccontextmanager
from fastapi import FastAPI
from src.api.v1.api import api_router
from src.core.database import Base, engine
from src.middleware.logging import LoggingMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield

app = FastAPI(lifespan=lifespan)

app.add_middleware(LoggingMiddleware)
app.include_router(api_router)