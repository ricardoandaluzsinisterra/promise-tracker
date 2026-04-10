import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from consumer import run_event_consumer
from database import Base, engine, get_db
from outbox import run_outbox_poller
from repository import TrackingRepository
from schemas import CreateTrackingCommand, TrackingResponse, UpdateTrackingProgressCommand


KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
repo = TrackingRepository()


@asynccontextmanager
async def lifespan(app: FastAPI):
	async with engine.begin() as conn:
		await conn.run_sync(Base.metadata.create_all)

	poller_task = asyncio.create_task(run_outbox_poller(KAFKA_BROKER))
	consumer_task = asyncio.create_task(run_event_consumer(KAFKA_BROKER))

	yield

	poller_task.cancel()
	consumer_task.cancel()
	await asyncio.gather(poller_task, consumer_task, return_exceptions=True)


app = FastAPI(title="Trackers Service", lifespan=lifespan)


@app.post("/tracking", response_model=TrackingResponse, status_code=201)
async def create_tracking(
	command: CreateTrackingCommand,
	db: AsyncSession = Depends(get_db),
):
	tracking = await repo.create_tracking_record(db, command)
	return tracking


@app.patch("/tracking/{promise_id}", response_model=TrackingResponse)
async def update_tracking_progress(
	promise_id: str,
	command: UpdateTrackingProgressCommand,
	db: AsyncSession = Depends(get_db),
):
	tracking = await repo.update_progress(db, promise_id, command)
	if tracking is None:
		raise HTTPException(status_code=404, detail="Tracking record not found")
	return tracking


@app.get("/tracking/{promise_id}", response_model=TrackingResponse)
async def get_tracking(
	promise_id: str,
	db: AsyncSession = Depends(get_db),
):
	tracking = await repo.get_tracking_by_promise_id(db, promise_id)
	if tracking is None:
		raise HTTPException(status_code=404, detail="Tracking record not found")
	return tracking
