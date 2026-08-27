from sqlalchemy.orm import Session
from src.models.todo import Todos
from src.schemas.todo import TodoRequest
from sqlalchemy import and_

def get_todos(db: Session) -> list[Todos]:
    return db.query(Todos).all()

def get_todo(todo_id: int, db: Session) -> Todos:
    return db.query(Todos).filter(Todos.id == todo_id).first()

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