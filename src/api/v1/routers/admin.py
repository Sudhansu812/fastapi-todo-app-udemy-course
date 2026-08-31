from fastapi import APIRouter, HTTPException
from passlib.context import CryptContext
from starlette import status
from src.crud.todo import get_todos
from src.models.role import Role
from src.models.user import User
from src.schemas.todo import TodoResponse
from src.api.deps import db_dependency
from src.schemas.user import UserRequest
from src.crud.auth import register_user as create_user
from src.crud.role import get_role_by_code, assign_role_to_user

router = APIRouter(prefix="/admin", tags=["admin-v1"])

@router.get("/all_todos", status_code=status.HTTP_200_OK, response_model=list[TodoResponse])
async def get_all_todos(db: db_dependency):
    return get_todos(db)

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_new_admin(user: UserRequest, db: db_dependency):
    create_user_model = User(
        first_name=user.first_name,
        last_name = user.last_name,
        email = user.email,
        username = user.username,
        hashed_password=__hash_password(user.password),
        is_active=True,
        # role=user.role
    )
    
    db_user = create_user(create_user_model, db)
    user_role: Role = get_role_by_code("usr", db)
    if not user_role:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Role assignment failed. Role not found.")
    admin_role: Role = get_role_by_code("adm", db)
    if not admin_role:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Role assignment failed. Role not found.")
    assign_role_to_user(role_id=user_role.id, user_id=db_user.id, db=db)
    assign_role_to_user(role_id=admin_role.id, user_id=db_user.id, db=db)
    
    return db_user
    

'''
Helpers
'''
def __hash_password(password: str) -> str:
    bcrypt_context = CryptContext(schemes=['bcrypt'], deprecated='auto')
    return bcrypt_context.hash(password)