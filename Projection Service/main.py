import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from consumer import run_event_consumer
from database import Base, engine, get_db
from repository import ProjectionRepository
from schemas import PromiseSummaryResponse


KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
repo = ProjectionRepository()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    consumer_task = asyncio.create_task(run_event_consumer(KAFKA_BROKER))

    yield

    consumer_task.cancel()
    await asyncio.gather(consumer_task, return_exceptions=True)


app = FastAPI(title="Projection Service", lifespan=lifespan)


@app.get("/query/promises", response_model=list[PromiseSummaryResponse])
async def list_promise_summaries(
    politician_id: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    summaries = await repo.list_summaries(db, politician_id=politician_id)
    return summaries


@app.get("/query/promises/{promise_id}", response_model=PromiseSummaryResponse)
async def get_promise_summary(
    promise_id: str,
    db: AsyncSession = Depends(get_db),
):
    summary = await repo.get_summary(db, promise_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Promise summary not found")
    return summary