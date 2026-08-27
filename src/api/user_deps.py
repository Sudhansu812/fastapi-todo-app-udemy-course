from typing import Annotated
from fastapi import Depends
from src.api.v1.routers.auth import get_current_user
from src.schemas.user import TokenData

user_dependency = Annotated[TokenData, Depends(get_current_user)]