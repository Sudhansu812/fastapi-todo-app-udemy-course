from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

class TodoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    priority: int
    complete: bool
    
class TodoRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    title: str = Field(min_length=1, max_length=128)
    description: str = Field(min_length=1, max_length=356)
    priority: int = Field(gt=0, lt=6)
    complete: Optional[bool] = Field(description="By default this will be set to false, value need not be entered during creation.", default=False)