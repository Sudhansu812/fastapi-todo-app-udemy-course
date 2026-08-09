from fastapi import APIRouter
from src.api.v1.routers import todos as todos_v1

api_router = APIRouter(prefix="/api")
api_router.include_router(todos_v1.router, prefix="/v1")