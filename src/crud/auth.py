from sqlalchemy import or_, and_
from sqlalchemy.orm import Session
from src.models.user import User
from src.schemas.user import UserLoginRequest

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