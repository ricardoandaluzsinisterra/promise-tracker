import asyncio
import json
import logging
from aiokafka import AIOKafkaConsumer

from database import AsyncSessionFactory
from events import POLITICIAN_TAGGED, PROMISE_RETRACTED, PROMISE_UNTAGGED, CONSUMED_TOPIC
from repository import TrackingRepository


logger = logging.getLogger(__name__)
repo = TrackingRepository()
RETRY_DELAY_SECONDS = 3


async def run_event_consumer(kafka_broker: str):
    while True:
        consumer = AIOKafkaConsumer(
            CONSUMED_TOPIC,
            bootstrap_servers=kafka_broker,
            group_id="trackers-service-group",
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
        politician_id = payload.get("politician_id")

        if not promise_id:
            return

        async with AsyncSessionFactory() as database:
            if event_type == POLITICIAN_TAGGED:
                if not politician_id:
                    return

                emitted = await repo.handle_politician_tagged(
                    database=database,
                    promise_id=promise_id,
                    politician_id=politician_id,
                )
                logger.info(f"Handled PoliticianTagged for {promise_id}, queued {emitted}")
                logger.warning(
                    f"Trackers Service consumer: Handled PoliticianTagged for {promise_id}"
                )

            elif event_type in (PROMISE_RETRACTED, PROMISE_UNTAGGED):
                emitted = await repo.handle_promise_retracted(
                    database=database,
                    promise_id=promise_id,
                    politician_id_from_event=politician_id,
                )
                logger.info(
                    f"Handled {event_type} for {promise_id}, queued {emitted}"
                )
    except Exception as error:
        logger.error(f"Error handling message: {error}")