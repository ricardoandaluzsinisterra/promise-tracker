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
    
    async def retract_promise(self, database: AsyncSession, promise: Promise):
        get_promise = await database.execute(select(Promise).where(Promise.id == promise.id))
        promise_from_db = get_promise.scalar_one_or_none()
        
        if promise_from_db == None:
            return None
        
        # Live SQL Alchemy instance, allows to set attributes directly
        promise_from_db.status = PromiseStatus.RETRACTING
        
        retract_promise_payload = build_promise_retracted_payload(
            promise_id=promise_from_db.id,
        )
        
        outbox_event = OutboxEvent(
            event_type= PROMISE_RETRACTED,
            aggregate_id= promise.id,
            payload= retract_promise_payload
        )
        
        database.add(outbox_event)
        
        await database.commit()
        
        return promise_from_db
        
        