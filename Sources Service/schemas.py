from datetime import datetime
from pydantic import BaseModel, Field


class CreateSourceCommand(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., min_length=1)


class LinkSourceCommand(BaseModel):
    promise_id: str
    source_id: str


class SourceResponse(BaseModel):
    id: str
    name: str
    url: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PromiseSourceResponse(BaseModel):
    id: str
    promise_id: str
    source_id: str
    linked_at: datetime

    model_config = {"from_attributes": True}