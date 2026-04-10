'''
AI Prompt:
Could you write a kafka consumer that has the following:
- One async function that listens to Kafka topics from downstream services.
- run_event_consumer: starts a Kafka consumer subscribed to politician.events and tracking.events. For each incoming message, parse the JSON, read the event_type field, and route to the correct handler.
- _handle_politician_tagged: calls repo.mark_active with the promise_id from the event
- _handle_politician_tagging_failed: calls repo.mark_failed with the promise_id
- _handle_tracking_archive_failed: reverts a promise from retracting back to active

This consumer will consume messages from the saga, either coming from the politician service or the tracking service.
'''
import json
import logging
from aiokafka import AIOKafkaConsumer
from database import AsyncSessionFactory
from repository import PromiseRepository
from events import POLITICIAN_TAGGED, POLITICIAN_TAGGING_FAILED, TRACKING_ARCHIVE_FAILED

logger = logging.getLogger(__name__)
repo = PromiseRepository()

# These are the topics this service listens to for saga outcomes
CONSUMED_TOPICS = ["politician.events", "tracking.events"]

async def run_event_consumer(kafka_broker: str):
    consumer = AIOKafkaConsumer(
        *CONSUMED_TOPICS,
        bootstrap_servers=kafka_broker,
        group_id="promises-service-group",  # consumer group ensures each message is processed once per group
        auto_offset_reset="earliest"
    )
    await consumer.start()
    logger.info("Event consumer started.")

    try:
        async for message in consumer:
            await _handle_message(message)
    finally:
        await consumer.stop()

async def _handle_message(message):
    try:
        payload = json.loads(message.value.decode("utf-8"))
        event_type = payload.get("event_type")
        promise_id = payload.get("promise_id") or payload.get("saga_id")

        if not promise_id:
            return  # not our event

        async with AsyncSessionFactory() as db:
            if event_type == POLITICIAN_TAGGED:
                # Downstream succeeded, promise is now active
                await repo.mark_active(db, promise_id)
                logger.info(f"Promise {promise_id} marked ACTIVE after PoliticianTagged")

            elif event_type == POLITICIAN_TAGGING_FAILED:
                # Downstream failed, compensate by marking promise FAILED
                await repo.mark_failed(db, promise_id)
                logger.warning(f"Promise {promise_id} marked FAILED after PoliticianTaggingFailed")

            elif event_type == TRACKING_ARCHIVE_FAILED:
                # Retraction saga failed, roll back to ACTIVE
                async with AsyncSessionFactory() as db2:
                    await db2.execute(
                        __import__("sqlalchemy").update(__import__("models").Promise)
                        .where(__import__("models").Promise.id == promise_id)
                        .values(status=__import__("models").PromiseStatus.ACTIVE)
                    )
                    await db2.commit()
                logger.warning(f"Retraction of {promise_id} failed, rolled back to ACTIVE")

    except Exception as e:
        logger.error(f"Error handling message: {e}")