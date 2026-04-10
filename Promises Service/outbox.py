import asyncio
import logging
from aiokafka import AIOKafkaProducer
from sqlalchemy import select, update
from database import AsyncSessionFactory
from models import OutboxEvent, OutboxStatus
from events import KAFKA_TOPIC


logger = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 2

async def run_outbox_poller(kafka_broker: str):
    producer = AIOKafkaProducer(bootstrap_servers=kafka_broker)
    await producer.start()
    logger.info("Outbox poller started.")

    try:
        while True:
            await _poll_and_publish(producer)
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
    finally:
        await producer.stop()
        logger.info("Outbox poller stopped.")

async def _poll_and_publish(producer: AIOKafkaProducer):
    async with AsyncSessionFactory() as database:
        result = await database.execute(
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxStatus.PENDING)
            .order_by(OutboxEvent.created_at)
            .limit(10)  # process in small batches, not the whole table at once
        )
        pending_events = result.scalars().all() # returns a list of the results

        for event in pending_events:
            try:
                await producer.send_and_wait(
                    KAFKA_TOPIC,
                    value=event.payload.encode("utf-8"),
                    key=event.aggregate_id.encode("utf-8")  # key = promise_id, ensures ordering per promise
                )

                # Only mark SENT after successful publish
                await database.execute(
                    update(OutboxEvent)
                    .where(OutboxEvent.id == event.id)
                    .values(status=OutboxStatus.SENT)
                )
                await database.commit()
                logger.info(f"Published and marked SENT: {event.event_type} / {event.aggregate_id}")

            except Exception as e:
                logger.error(f"Failed to publish {event.id}: {e}. Will retry.")
                # Do NOT commit, row stays PENDING, retried next loop