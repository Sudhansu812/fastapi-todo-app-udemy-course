from fastapi import APIRouter, HTTPException, Path
from starlette import status
from src.crud.todo import create_todo, delete_todo, get_todos, get_todo, update_todo
from src.schemas.todo import TodoRequest, TodoResponse
from src.api.deps import db_dependency

router = APIRouter(prefix="/todos", tags=["todos-sqlite"])

@router.get("/", response_model=list[TodoResponse], status_code=status.HTTP_200_OK)
async def get_all(db: db_dependency):
    return get_todos(db)

@router.get("/todo/{todo_id}", response_model=TodoResponse, status_code=status.HTTP_200_OK)
async def get_by_id(db: db_dependency, todo_id: int = Path(gt=0)):
    todo = get_todo(todo_id, db)
    if not todo:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such todo found.")
    return todo

@router.post("/create", response_model=TodoResponse, status_code=status.HTTP_201_CREATED)
async def create(todo: TodoRequest, db: db_dependency):
    final_todo = create_todo(todo=todo, db=db)
    return final_todo

@router.put("/update/{todo_id}", response_model=TodoResponse, status_code=status.HTTP_200_OK)
async def update(db: db_dependency, new_todo: TodoRequest, todo_id: int = Path(gt=0)):
    updated_todo = update_todo(todo_id=todo_id, todo=new_todo, db=db)
    if updated_todo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such todo found.")
    return updated_todo

@router.delete("/remove/{todo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove(db: db_dependency, todo_id: int = Path(gt=0)):
    removed: bool = delete_todo(todo_id, db)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such todo found.")