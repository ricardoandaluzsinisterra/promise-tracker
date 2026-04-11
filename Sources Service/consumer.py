import asyncio
import json
import logging
from aiokafka import AIOKafkaConsumer

from database import AsyncSessionFactory
from events import CONSUMED_TOPIC, TRACKING_ARCHIVED, TRACKING_CREATED
from repository import SourceRepository


logger = logging.getLogger(__name__)
repo = SourceRepository()
RETRY_DELAY_SECONDS = 3


async def run_event_consumer(kafka_broker: str):
    while True:
        consumer = AIOKafkaConsumer(
            CONSUMED_TOPIC,
            bootstrap_servers=kafka_broker,
            group_id="sources-service-group",
            auto_offset_reset="earliest",
        )
        try:
            await consumer.start()
            logger.info("Event consumer started.")

            async for message in consumer:
                await _handle_message(message)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error(
                f"Event consumer connection failed: {error}. Retrying in {RETRY_DELAY_SECONDS}s"
            )
            await asyncio.sleep(RETRY_DELAY_SECONDS)
        finally:
            try:
                await consumer.stop()
            except Exception:
                pass


async def _handle_message(message):
    try:
        payload = json.loads(message.value.decode("utf-8"))
        event_type = payload.get("event_type")
        promise_id = payload.get("promise_id") or payload.get("saga_id")

        if not promise_id:
            return

        if event_type == TRACKING_CREATED:
            # Informational only for this service.
            logger.info(f"Received TrackingCreated for {promise_id}; no action needed")
            return

        if event_type == TRACKING_ARCHIVED:
            async with AsyncSessionFactory() as database:
                emitted = await repo.clear_sources_for_promise(database, promise_id)
                logger.info(f"Handled TrackingArchived for {promise_id}, queued {emitted}")
    except Exception as error:
        logger.error(f"Error handling message: {error}")