from fastapi import APIRouter, Depends
from src.api.role_deps import require_role
from src.api.v1.routers import todos as todos_v1, auth as auth_v1, admin as admin_v1

api_router = APIRouter(prefix="/api")
api_router.include_router(todos_v1.router, prefix="/v1")
api_router.include_router(auth_v1.router, prefix="/v1")
api_router.include_router(admin_v1.router, prefix="/v1", dependencies=[Depends(require_role("adm"))])