import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from events import (
    SOURCE_LINKED,
    SOURCES_CLEARED,
    SOURCES_CLEAR_FAILED,
    build_source_linked_payload,
    build_sources_clear_failed_payload,
    build_sources_cleared_payload,
)
from models import OutboxEvent, OutboxStatus, PromiseSource, Source
from schemas import CreateSourceCommand, LinkSourceCommand


class SourceRepository:
    async def create_source(self, database: AsyncSession, command: CreateSourceCommand) -> Source:
        source = Source(
            id=str(uuid.uuid4()),
            name=command.name,
            url=command.url,
        )

        database.add(source)
        await database.commit()
        await database.refresh(source)
        return source

    async def get_source(self, database: AsyncSession, source_id: str) -> Source | None:
        result = await database.execute(select(Source).where(Source.id == source_id))
        return result.scalar_one_or_none()

    async def link_source_to_promise(
        self,
        database: AsyncSession,
        command: LinkSourceCommand,
    ) -> PromiseSource:
        async with database.begin():
            promise_source = PromiseSource(
                id=str(uuid.uuid4()),
                promise_id=command.promise_id,
                source_id=command.source_id,
            )
            database.add(promise_source)

            payload = build_source_linked_payload(
                promise_id=command.promise_id,
                source_id=command.source_id,
            )
            outbox_event = OutboxEvent(
                id=str(uuid.uuid4()),
                event_type=SOURCE_LINKED,
                aggregate_id=command.promise_id,
                payload=payload,
                status=OutboxStatus.PENDING,
            )
            database.add(outbox_event)

            return promise_source

    async def get_sources_for_promise(self, database: AsyncSession, promise_id: str) -> list[Source]:
        result = await database.execute(
            select(Source)
            .join(PromiseSource, PromiseSource.source_id == Source.id)
            .where(PromiseSource.promise_id == promise_id)
        )
        return result.scalars().all()

    async def clear_sources_for_promise(self, database: AsyncSession, promise_id: str) -> str:
        async with database.begin():
            try:
                result = await database.execute(
                    select(PromiseSource).where(PromiseSource.promise_id == promise_id)
                )
                linked_rows = result.scalars().all()

                for linked_row in linked_rows:
                    await database.delete(linked_row)

                payload = build_sources_cleared_payload(promise_id=promise_id)
                event_type = SOURCES_CLEARED
            except Exception:
                payload = build_sources_clear_failed_payload(promise_id=promise_id)
                event_type = SOURCES_CLEAR_FAILED

            outbox_event = OutboxEvent(
                id=str(uuid.uuid4()),
                event_type=event_type,
                aggregate_id=promise_id,
                payload=payload,
                status=OutboxStatus.PENDING,
            )
            database.add(outbox_event)
            return event_type