from sqlalchemy.orm import Session
from src.models.todo import Todos
from src.schemas.todo import TodoRequest

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