import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from events import (
    TRACKING_ARCHIVED,
    TRACKING_ARCHIVE_FAILED,
    TRACKING_CREATION_FAILED,
    TRACKING_CREATED,
    TRACKING_UPDATED,
    build_tracking_archived_payload,
    build_tracking_archive_failed_payload,
    build_tracking_creation_failed_payload,
    build_tracking_created_payload,
    build_tracking_updated_payload,
)
from models import OutboxEvent, OutboxStatus, TrackingRecord, TrackingStatus
from schemas import CreateTrackingCommand, UpdateTrackingProgressCommand


class TrackingRepository:
    async def create_tracking_record(
        self,
        database: AsyncSession,
        command: CreateTrackingCommand,
    ) -> TrackingRecord:
        tracking = TrackingRecord(
            id=str(uuid.uuid4()),
            promise_id=command.promise_id,
            politician_id=command.politician_id,
            progress=command.progress,
            status=TrackingStatus.ACTIVE,
        )

        database.add(tracking)
        await database.commit()
        await database.refresh(tracking)
        return tracking

    async def get_tracking_by_promise_id(
        self,
        database: AsyncSession,
        promise_id: str,
    ) -> TrackingRecord | None:
        result = await database.execute(
            select(TrackingRecord).where(TrackingRecord.promise_id == promise_id)
        )
        return result.scalar_one_or_none()

    async def update_progress(
        self,
        database: AsyncSession,
        promise_id: str,
        command: UpdateTrackingProgressCommand,
    ) -> TrackingRecord | None:
        async with database.begin():
            result = await database.execute(
                select(TrackingRecord).where(TrackingRecord.promise_id == promise_id)
            )
            tracking = result.scalar_one_or_none()
            if tracking is None:
                return None

            tracking.progress = command.progress

            payload = build_tracking_updated_payload(
                promise_id=tracking.promise_id,
                politician_id=tracking.politician_id,
                progress=tracking.progress,
            )
            outbox_event = OutboxEvent(
                id=str(uuid.uuid4()),
                event_type=TRACKING_UPDATED,
                aggregate_id=tracking.promise_id,
                payload=payload,
                status=OutboxStatus.PENDING,
            )
            database.add(outbox_event)

            return tracking

    async def handle_politician_tagged(
        self,
        database: AsyncSession,
        promise_id: str,
        politician_id: str,
    ) -> str:
        async with database.begin():
            try:
                tracking = TrackingRecord(
                    id=str(uuid.uuid4()),
                    promise_id=promise_id,
                    politician_id=politician_id,
                    progress=0,
                    status=TrackingStatus.ACTIVE,
                )
                database.add(tracking)

                payload = build_tracking_created_payload(promise_id, politician_id, 0)
                event_type = TRACKING_CREATED
            except Exception:
                payload = build_tracking_creation_failed_payload(promise_id, politician_id)
                event_type = TRACKING_CREATION_FAILED

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
                select(TrackingRecord).where(TrackingRecord.promise_id == promise_id)
            )
            tracking = result.scalar_one_or_none()

            if tracking is not None:
                try:
                    tracking.status = TrackingStatus.ARCHIVED
                    payload = build_tracking_archived_payload(
                        promise_id=tracking.promise_id,
                        politician_id=tracking.politician_id,
                        progress=tracking.progress,
                    )
                    event_type = TRACKING_ARCHIVED
                except Exception:
                    payload = build_tracking_archive_failed_payload(
                        promise_id=promise_id,
                        politician_id=tracking.politician_id or politician_id_from_event or "",
                    )
                    event_type = TRACKING_ARCHIVE_FAILED
            else:
                payload = build_tracking_archive_failed_payload(
                    promise_id=promise_id,
                    politician_id=politician_id_from_event or "",
                )
                event_type = TRACKING_ARCHIVE_FAILED

            outbox_event = OutboxEvent(
                id=str(uuid.uuid4()),
                event_type=event_type,
                aggregate_id=promise_id,
                payload=payload,
                status=OutboxStatus.PENDING,
            )
            database.add(outbox_event)

            return event_type