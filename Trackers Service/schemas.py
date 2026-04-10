from datetime import datetime
from pydantic import BaseModel, Field

from models import TrackingStatus


class CreateTrackingCommand(BaseModel):
    promise_id: str
    politician_id: str
    progress: int = Field(default=0, ge=0)


class UpdateTrackingProgressCommand(BaseModel):
    progress: int = Field(..., ge=0)


class TrackingResponse(BaseModel):
    id: str
    promise_id: str
    politician_id: str
    progress: int
    status: TrackingStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}