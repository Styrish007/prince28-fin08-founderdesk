"""All SQL for ingest jobs and items. Endpoints and workers never write SQL themselves."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from founderdesk.db.models import IngestItem, IngestJob


class IngestJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_job(self, job_id: str, items_total: int) -> IngestJob:
        job = IngestJob(id=job_id, status="queued", items_total=items_total)
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_job(self, job_id: str) -> IngestJob | None:
        return await self.session.scalar(select(IngestJob).where(IngestJob.id == job_id))

    async def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        items_done: int | None = None,
        items_failed: int | None = None,
        items_skipped: int | None = None,
    ) -> None:
        job = await self.get_job(job_id)
        if job is None:
            return
        if status is not None:
            job.status = status
        if items_done is not None:
            job.items_done = items_done
        if items_failed is not None:
            job.items_failed = items_failed
        if items_skipped is not None:
            job.items_skipped = items_skipped
        job.updated_at = datetime.now(UTC)
        await self.session.flush()

    async def list_items(
        self, job_id: str, status: str | None = None
    ) -> tuple[int, list[IngestItem]]:
        stmt = select(IngestItem).where(IngestItem.job_id == job_id)
        if status is not None:
            stmt = stmt.where(IngestItem.status == status)
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = await self.session.scalars(stmt)
        return total or 0, list(rows)

    async def claim_one(self) -> IngestItem | None:
        """Mark one queued item as running and return it, so another worker won't take it.

        Items with a lock older than ingest_job_timeout seconds are also claimed
        (recovery after a worker crash).
        """
        from founderdesk.config import get_settings

        settings = get_settings()
        cutoff = datetime.now(UTC) - __import__("timedelta", fromlist=["timedelta"]).timedelta(
            seconds=settings.ingest_job_timeout
        )
        stmt = (
            select(IngestItem)
            .where(IngestItem.status == "queued")
            .where((IngestItem.updated_at.is_(None)) | (IngestItem.updated_at < cutoff))
            .limit(1)
        )
        item = await self.session.scalar(stmt)
        if item is None:
            return None
        item.status = "running"
        item.attempts = (item.attempts or 0) + 1
        item.updated_at = datetime.now(UTC)
        await self.session.flush()
        return item

    async def claim_all_queued(self) -> list[IngestItem]:
        """Put every queued or stale-running item back in the queue (recovery)."""
        from founderdesk.config import get_settings

        settings = get_settings()
        cutoff = datetime.now(UTC) - __import__("timedelta", fromlist=["timedelta"]).timedelta(
            seconds=settings.ingest_job_timeout
        )
        stmt = select(IngestItem).where(
            (IngestItem.status == "queued")
            | ((IngestItem.status == "running") & (IngestItem.updated_at < cutoff))
        )
        rows = await self.session.scalars(stmt)
        items = list(rows)
        for item in items:
            item.status = "queued"
            item.updated_at = datetime.now(UTC)
        await self.session.flush()
        return items

    async def save_item(
        self,
        job_id: str,
        path: str,
        *,
        status: str,
        error: str | None = None,
    ) -> IngestItem:
        item = IngestItem(
            job_id=job_id,
            path=path,
            status=status,
            error=error,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def item_counts(self, job_id: str) -> dict[str, int]:
        stmt = (
            select(
                IngestItem.status,
                func.count(IngestItem.id),
            )
            .where(IngestItem.job_id == job_id)
            .group_by(IngestItem.status)
        )
        rows = await self.session.execute(stmt)
        counts = {"done": 0, "failed": 0, "skipped": 0, "queued": 0, "running": 0}
        for status, count in rows:
            counts[status] = count or 0
        return counts
