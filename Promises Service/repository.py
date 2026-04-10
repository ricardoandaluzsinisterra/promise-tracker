# repository.py
import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from models import Promise, OutboxEvent, PromiseStatus, OutboxStatus
from schemas import CreatePromiseCommand, UpdatePromiseCommand
from events import (
    build_promise_created_payload,
    build_promise_retracted_payload,
    PROMISE_CREATED, PROMISE_RETRACTED, KAFKA_TOPIC
)

class PromiseRepository:
    
    async def create_promise(self, database: AsyncSession, command: CreatePromiseCommand):
        promise = Promise(
            title= CreatePromiseCommand.title,
            description= CreatePromiseCommand.description,
            politician_id= CreatePromiseCommand.politician_id
        )
        
        create_promise_payload = build_promise_created_payload(
            promise_id=promise.id,
            title=promise.title,
            politician_id= promise.politician_id
        )

        outbox_event = OutboxEvent(
            event_type= PROMISE_CREATED,
            aggregate_id= promise.id,
            payload= create_promise_payload
        )
        
        # Add both atomically
        database.add(promise)
        database.add(outbox_event)

        #Commit both at the same time
        await database.commit()
        