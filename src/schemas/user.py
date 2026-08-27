from typing import Optional
from pydantic import BaseModel, ConfigDict, Field

class UserRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    first_name: str = Field(min_length=1, max_length=128)
    last_name: Optional[str] = Field(max_length=128, description="The user could have no last name.")
    email: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=128)
    role: Optional[str] = Field(max_length=128, description="User might not have a role when created.")
    
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int = Field(gt=0)
    first_name: str = Field(min_length=1, max_length=128)
    last_name: Optional[str] = Field(max_length=128, description="The user could have no last name.")
    email: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128)
    is_active: Optional[bool] = Field(description="By default this will be true.", default=True)
    role: Optional[str] = Field(max_length=128, description="User might not have a role when created.")
    
class UserLoginRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    username: str = Field(min_length=1, max_length=128, description="Accepts username or email.")
    password: str = Field(min_length=1, max_length=128)
    
class Token(BaseModel):
    access_token: str
    token_type: str
    
class TokenData(BaseModel):
    username: str
    user_id: int
    role: list[str]