from datetime import datetime
from pydantic import BaseModel, Field


class CreatePoliticianCommand(BaseModel):
	name: str = Field(..., min_length=1, max_length=255)
	role: str = Field(..., min_length=1, max_length=255)


class PoliticianResponse(BaseModel):
	id: str
	name: str
	role: str
	created_at: datetime

	model_config = {"from_attributes": True}
