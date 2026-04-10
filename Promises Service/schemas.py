'''
AI Prompt: 
Based on the current files of the repository, generate the appropriate pydantic models
for the schemas used by the client. I want to be able to evolve them or modify them later on
so this is the best way to ensure that flexibility, without breaking the API.
'''
from pydantic import BaseModel, Field
from typing import Optional
from models import PromiseStatus

class CreatePromiseCommand(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    description: Optional[str] = None
    politician_id: str

class UpdatePromiseCommand(BaseModel):
    title: Optional[str] = Field(None, min_length=3, max_length=255)
    description: Optional[str] = None

class PromiseResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    politician_id: str
    status: PromiseStatus

    model_config = {"from_attributes": True}  # lets Pydantic read SQLAlchemy objects