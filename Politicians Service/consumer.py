import json
import logging
from aiokafka import AIOKafkaConsumer

from database import AsyncSessionFactory
from events import CONSUMED_TOPIC, PROMISE_CREATED, PROMISE_RETRACTED
from repository import PoliticianRepository


logger = logging.getLogger(__name__)
repo = PoliticianRepository()


async def run_event_consumer(kafka_broker: str):
	consumer = AIOKafkaConsumer(
		CONSUMED_TOPIC,
		bootstrap_servers=kafka_broker,
		group_id="politicians-service-group",
		auto_offset_reset="earliest",
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
		politician_id = payload.get("politician_id")

		if not promise_id:
			return

		async with AsyncSessionFactory() as database:
			if event_type == PROMISE_CREATED:
				if not politician_id:
					return
				emitted = await repo.handle_promise_created(
					database=database,
					promise_id=promise_id,
					politician_id=politician_id,
				)
				logger.info(f"Handled PromiseCreated for {promise_id}, queued {emitted}")

			elif event_type == PROMISE_RETRACTED:
				emitted = await repo.handle_promise_retracted(
					database=database,
					promise_id=promise_id,
					politician_id_from_event=politician_id,
				)
				logger.info(f"Handled PromiseRetracted for {promise_id}, queued {emitted}")

	except Exception as error:
		logger.error(f"Error handling message: {error}")
