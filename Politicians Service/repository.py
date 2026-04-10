import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from events import (
	POLITICIAN_TAGGED,
	POLITICIAN_TAGGING_FAILED,
	PROMISE_UNTAGGED,
	build_politician_tagged_payload,
	build_politician_tagging_failed_payload,
	build_promise_untagged_payload,
)
from models import Politician, PoliticianPromise, OutboxEvent, OutboxStatus
from schemas import CreatePoliticianCommand


class PoliticianRepository:
	async def create_politician(self, database: AsyncSession, command: CreatePoliticianCommand) -> Politician:
		politician = Politician(
			id=str(uuid.uuid4()),
			name=command.name,
			role=command.role,
		)

		database.add(politician)
		await database.commit()
		await database.refresh(politician)
		return politician

	async def get_politician(self, database: AsyncSession, politician_id: str) -> Politician | None:
		result = await database.execute(select(Politician).where(Politician.id == politician_id))
		return result.scalar_one_or_none()

	async def handle_promise_created(self, database: AsyncSession, promise_id: str, politician_id: str) -> str:
		async with database.begin():
			result = await database.execute(select(Politician).where(Politician.id == politician_id))
			politician = result.scalar_one_or_none()

			if politician:
				politician_promise = PoliticianPromise(
					id=str(uuid.uuid4()),
					politician_id=politician_id,
					promise_id=promise_id,
				)
				database.add(politician_promise)

				payload = build_politician_tagged_payload(
					promise_id=promise_id,
					politician_id=politician_id,
				)
				event_type = POLITICIAN_TAGGED
			else:
				payload = build_politician_tagging_failed_payload(
					promise_id=promise_id,
					politician_id=politician_id,
				)
				event_type = POLITICIAN_TAGGING_FAILED

			outbox_event = OutboxEvent(
				id=str(uuid.uuid4()),
				event_type=event_type,
				aggregate_id=promise_id,
				payload=payload,
				status=OutboxStatus.PENDING,
			)
			database.add(outbox_event)

			return event_type

	async def handle_promise_retracted(
		self,
		database: AsyncSession,
		promise_id: str,
		politician_id_from_event: str | None,
	) -> str:
		async with database.begin():
			result = await database.execute(
				select(PoliticianPromise).where(PoliticianPromise.promise_id == promise_id)
			)
			politician_promise = result.scalar_one_or_none()

			politician_id = politician_id_from_event or (
				politician_promise.politician_id if politician_promise else ""
			)

			if politician_promise is not None:
				await database.delete(politician_promise)

			payload = build_promise_untagged_payload(
				promise_id=promise_id,
				politician_id=politician_id,
			)

			outbox_event = OutboxEvent(
				id=str(uuid.uuid4()),
				event_type=PROMISE_UNTAGGED,
				aggregate_id=promise_id,
				payload=payload,
				status=OutboxStatus.PENDING,
			)
			database.add(outbox_event)

			return PROMISE_UNTAGGED
