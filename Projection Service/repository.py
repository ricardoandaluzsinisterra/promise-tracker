import logging
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import PromiseSummary, PromiseSummaryStatus


logger = logging.getLogger(__name__)


class ProjectionRepository:
    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    async def get_summary(self, database: AsyncSession, promise_id: str) -> PromiseSummary | None:
        result = await database.execute(
            select(PromiseSummary).where(PromiseSummary.promise_id == promise_id)
        )
        return result.scalar_one_or_none()

    async def list_summaries(
        self,
        database: AsyncSession,
        politician_id: str | None = None,
    ) -> list[PromiseSummary]:
        statement = select(PromiseSummary).order_by(PromiseSummary.created_at)
        if politician_id:
            statement = statement.where(PromiseSummary.politician_id == politician_id)

        result = await database.execute(statement)
        return result.scalars().all()

    async def handle_promise_created(self, database: AsyncSession, payload: dict):
        promise_id = payload.get("promise_id") or payload.get("saga_id")
        title = payload.get("title")
        politician_id = payload.get("politician_id")

        if not promise_id or not title or not politician_id:
            logger.warning("PromiseCreated payload missing required fields")
            return

        existing = await self.get_summary(database, promise_id)
        if existing is not None:
            logger.warning(f"PromiseSummary already exists for {promise_id}; skipping insert")
            return

        now = self._utc_now()
        summary = PromiseSummary(
            id=promise_id,
            promise_id=promise_id,
            title=title,
            politician_id=politician_id,
            status=PromiseSummaryStatus.PENDING,
            progress=0,
            source_count=0,
            created_at=now,
            updated_at=now,
        )
        database.add(summary)
        await database.commit()

    async def handle_politician_tagged(self, database: AsyncSession, payload: dict):
        promise_id = payload.get("promise_id") or payload.get("saga_id")
        if not promise_id:
            return

        summary = await self.get_summary(database, promise_id)
        if summary is None:
            logger.warning(f"No PromiseSummary found for PoliticianTagged {promise_id}; skipping")
            return

        summary.status = PromiseSummaryStatus.ACTIVE
        politician_name = payload.get("politician_name")
        if politician_name:
            summary.politician_name = politician_name
        summary.updated_at = self._utc_now()
        await database.commit()

    async def handle_politician_tagging_failed(self, database: AsyncSession, payload: dict):
        promise_id = payload.get("promise_id") or payload.get("saga_id")
        if not promise_id:
            return

        summary = await self.get_summary(database, promise_id)
        if summary is None:
            logger.warning(
                f"No PromiseSummary found for PoliticianTaggingFailed {promise_id}; skipping"
            )
            return

        summary.status = PromiseSummaryStatus.FAILED
        summary.updated_at = self._utc_now()
        await database.commit()

    async def handle_tracking_creation_failed(self, database: AsyncSession, payload: dict):
        promise_id = payload.get("promise_id") or payload.get("saga_id")
        if not promise_id:
            return
        summary = await self.get_summary(database, promise_id)
        if summary is None:
            return
        summary.status = PromiseSummaryStatus.FAILED
        summary.updated_at = self._utc_now()
        await database.commit()

    async def handle_politician_untagging_failed(self, database: AsyncSession, payload: dict):
        promise_id = payload.get("promise_id") or payload.get("saga_id")
        if not promise_id:
            return
        summary = await self.get_summary(database, promise_id)
        if summary is None:
            return
        summary.status = PromiseSummaryStatus.FAILED
        summary.updated_at = self._utc_now()
        await database.commit()

    async def handle_sources_clear_failed(self, database: AsyncSession, payload: dict):
        promise_id = payload.get("promise_id") or payload.get("saga_id")
        if not promise_id:
            return
        summary = await self.get_summary(database, promise_id)
        if summary is None:
            return
        summary.status = PromiseSummaryStatus.FAILED
        summary.updated_at = self._utc_now()
        await database.commit()

    async def handle_tracking_archive_failed(self, database: AsyncSession, payload: dict):
        promise_id = payload.get("promise_id") or payload.get("saga_id")
        if not promise_id:
            return
        summary = await self.get_summary(database, promise_id)
        if summary is None:
            return
        summary.status = PromiseSummaryStatus.ACTIVE  # retraction rolled back, promise is still live
        summary.updated_at = self._utc_now()
        await database.commit()

    async def handle_tracking_updated(self, database: AsyncSession, payload: dict):
        promise_id = payload.get("promise_id") or payload.get("saga_id")
        if not promise_id:
            return

        summary = await self.get_summary(database, promise_id)
        if summary is None:
            logger.warning(f"No PromiseSummary found for TrackingUpdated {promise_id}; skipping")
            return

        progress = payload.get("progress")
        if progress is None:
            logger.warning(f"TrackingUpdated for {promise_id} missing progress; skipping")
            return

        summary.progress = int(progress)
        summary.updated_at = self._utc_now()
        await database.commit()

    async def handle_tracking_archived(self, database: AsyncSession, payload: dict):
        promise_id = payload.get("promise_id") or payload.get("saga_id")
        if not promise_id:
            return

        summary = await self.get_summary(database, promise_id)
        if summary is None:
            logger.warning(f"No PromiseSummary found for TrackingArchived {promise_id}; skipping")
            return

        summary.status = PromiseSummaryStatus.ARCHIVED
        summary.updated_at = self._utc_now()
        await database.commit()

    async def handle_source_linked(self, database: AsyncSession, payload: dict):
        promise_id = payload.get("promise_id") or payload.get("saga_id")
        if not promise_id:
            return

        summary = await self.get_summary(database, promise_id)
        if summary is None:
            logger.warning(f"No PromiseSummary found for SourceLinked {promise_id}; skipping")
            return

        summary.source_count = summary.source_count + 1
        summary.updated_at = self._utc_now()
        await database.commit()

    async def handle_sources_cleared(self, database: AsyncSession, payload: dict):
        promise_id = payload.get("promise_id") or payload.get("saga_id")
        if not promise_id:
            return

        summary = await self.get_summary(database, promise_id)
        if summary is None:
            logger.warning(f"No PromiseSummary found for SourcesCleared {promise_id}; skipping")
            return

        summary.source_count = 0
        summary.updated_at = self._utc_now()
        await database.commit()