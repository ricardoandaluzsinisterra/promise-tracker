import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from consumer import run_event_consumer
from database import Base, engine, get_db
from outbox import run_outbox_poller
from repository import PoliticianRepository
from schemas import CreatePoliticianCommand, PoliticianResponse


KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
repo = PoliticianRepository()


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


app = FastAPI(title="Politicians Service", lifespan=lifespan)


@app.post("/politicians", response_model=PoliticianResponse, status_code=201)
async def create_politician(
	command: CreatePoliticianCommand,
	db: AsyncSession = Depends(get_db),
):
	politician = await repo.create_politician(db, command)
	return politician


@app.get("/politicians/{politician_id}", response_model=PoliticianResponse)
async def get_politician(
	politician_id: str,
	db: AsyncSession = Depends(get_db),
):
	politician = await repo.get_politician(db, politician_id)
	if politician is None:
		raise HTTPException(status_code=404, detail="Politician not found")
	return politician
