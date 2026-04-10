from datetime import datetime
from pydantic import BaseModel

from models import PromiseSummaryStatus


class PromiseSummaryResponse(BaseModel):
    id: str
    promise_id: str
    title: str
    politician_id: str
    politician_name: str | None
    status: PromiseSummaryStatus
    progress: int
    source_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}