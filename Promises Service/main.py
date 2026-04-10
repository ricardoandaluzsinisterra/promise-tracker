# main.py
import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import engine, Base, get_db
from repository import PromiseRepository
from schemas import CreatePromiseCommand, UpdatePromiseCommand, PromiseResponse
from outbox import run_outbox_poller
from consumer import run_event_consumer
from sqlalchemy import select
from models import Promise

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
repo = PromiseRepository()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables, then launch background tasks
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create as task so that they both run in the background.
    poller_task   = asyncio.create_task(run_outbox_poller(KAFKA_BROKER))
    consumer_task = asyncio.create_task(run_event_consumer(KAFKA_BROKER))

    yield  # app is running, handle requests

    # Shutdown: cancel background tasks cleanly
    poller_task.cancel()
    consumer_task.cancel()
    await asyncio.gather(poller_task, consumer_task, return_exceptions=True)

app = FastAPI(title="Promises Service", lifespan=lifespan)

@app.post("/promises", response_model=PromiseResponse, status_code=201)
async def create_promise(cmd: CreatePromiseCommand, db: AsyncSession = Depends(get_db)):
    promise = await repo.create_promise(db, cmd)
    return promise

@app.patch("/promises/{promise_id}/status", response_model=PromiseResponse)
async def retract_promise(promise_id: str, db: AsyncSession = Depends(get_db)):
    promise = await repo.retract_promise(db, promise_id)
    if not promise:
        raise HTTPException(status_code=404, detail="Promise not found")
    return promise

@app.get("/promises/{promise_id}", response_model=PromiseResponse)
async def get_promise(promise_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Promise).where(Promise.id == promise_id))
    promise = result.scalar_one_or_none()
    if not promise:
        raise HTTPException(status_code=404, detail="Promise not found")
    return promise