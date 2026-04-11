import json
import logging
from aiokafka import AIOKafkaConsumer

from database import AsyncSessionFactory
from events import (
    CONSUMED_TOPICS,
    POLITICIAN_TAGGED,
    POLITICIAN_TAGGING_FAILED,
    POLITICIAN_UNTAGGING_FAILED,
    PROMISE_CREATED,
    SOURCE_LINKED,
    SOURCES_CLEAR_FAILED,
    SOURCES_CLEARED,
    TRACKING_ARCHIVE_FAILED,
    TRACKING_CREATION_FAILED,
    TRACKING_ARCHIVED,
    TRACKING_UPDATED,
)
from repository import ProjectionRepository


logger = logging.getLogger(__name__)
repo = ProjectionRepository()


async def run_event_consumer(kafka_broker: str):
    consumer = AIOKafkaConsumer(
        bootstrap_servers=kafka_broker,
        group_id="projection-service-group",
        auto_offset_reset="earliest",
    )
    consumer.subscribe(topics=CONSUMED_TOPICS)
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

        async with AsyncSessionFactory() as database:
            if event_type == PROMISE_CREATED:
                await repo.handle_promise_created(database, payload)
            elif event_type == POLITICIAN_TAGGED:
                await repo.handle_politician_tagged(database, payload)
            elif event_type == POLITICIAN_TAGGING_FAILED:
                await repo.handle_politician_tagging_failed(database, payload)
            elif event_type == TRACKING_CREATION_FAILED:
                await repo.handle_tracking_creation_failed(database, payload)
            elif event_type == TRACKING_ARCHIVE_FAILED:
                await repo.handle_tracking_archive_failed(database, payload)
            elif event_type == POLITICIAN_UNTAGGING_FAILED:
                await repo.handle_politician_untagging_failed(database, payload)
            elif event_type == SOURCES_CLEAR_FAILED:
                await repo.handle_sources_clear_failed(database, payload)
            elif event_type == TRACKING_UPDATED:
                await repo.handle_tracking_updated(database, payload)
            elif event_type == TRACKING_ARCHIVED:
                await repo.handle_tracking_archived(database, payload)
            elif event_type == SOURCE_LINKED:
                await repo.handle_source_linked(database, payload)
            elif event_type == SOURCES_CLEARED:
                await repo.handle_sources_cleared(database, payload)
    except Exception as error:
        logger.error(f"Error handling message: {error}")