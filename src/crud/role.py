from sqlalchemy import select
from sqlalchemy.orm import Session
from src.models.role import Role
from src.models.user_role import UserRole

def get_roles_by_user(user_id: int, db: Session) -> list[str]:
    stmt = (
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id, Role.is_active == True)
    )
    return list(db.execute(stmt).scalars().all())
    
    
def get_role_by_code(code: str, db: Session) -> Role | None:
    stmt = (
        select(Role)
        .where(Role.code == code)
    )
    return db.execute(stmt).scalars().first()
    
def assign_role_to_user(user_id: int, role_id: int, db: Session):
    user_role = UserRole(user_id=user_id, role_id=role_id)
    db.add(user_role)
    db.flush()
    db.refresh(user_role)
    return user_role