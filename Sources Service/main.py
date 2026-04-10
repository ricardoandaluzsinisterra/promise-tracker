import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from consumer import run_event_consumer
from database import Base, engine, get_db
from outbox import run_outbox_poller
from repository import SourceRepository
from schemas import (
	CreateSourceCommand,
	LinkSourceCommand,
	PromiseSourceResponse,
	SourceResponse,
)


KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
repo = SourceRepository()


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


app = FastAPI(title="Sources Service", lifespan=lifespan)


@app.post("/sources", response_model=SourceResponse, status_code=201)
async def create_source(
	command: CreateSourceCommand,
	db: AsyncSession = Depends(get_db),
):
	source = await repo.create_source(db, command)
	return source


@app.post("/sources/link", response_model=PromiseSourceResponse, status_code=201)
async def link_source(
	command: LinkSourceCommand,
	db: AsyncSession = Depends(get_db),
):
	link = await repo.link_source_to_promise(db, command)
	return link


@app.get("/sources/promise/{promise_id}", response_model=list[SourceResponse])
async def get_sources_for_promise(
	promise_id: str,
	db: AsyncSession = Depends(get_db),
):
	return await repo.get_sources_for_promise(db, promise_id)


@app.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(
	source_id: str,
	db: AsyncSession = Depends(get_db),
):
	source = await repo.get_source(db, source_id)
	if source is None:
		raise HTTPException(status_code=404, detail="Source not found")
	return source
