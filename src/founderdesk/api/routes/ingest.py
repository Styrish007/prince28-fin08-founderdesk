"""Ingestion endpoints: queue a job, check progress, list dead letters."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from founderdesk.api.deps import (
    IngestJobRepoDep,
    ManifestDep,
    QueueDep,
    SettingsDep,
    require_admin,
)

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_admin)])
async def ingest(
    queue: QueueDep,
    job_repo: IngestJobRepoDep,
    settings: SettingsDep,
    manifest: ManifestDep,
) -> dict:
    """Queue one job per manifest document. Returns 202 Accepted immediately."""
    import uuid

    records = [r for r in manifest.values() if r.status == "downloaded"]

    job_id = str(uuid.uuid4())
    await job_repo.create_job(job_id=job_id, items_total=len(records))

    item_ids: list[int] = []
    for record in records:
        item = await job_repo.save_item(
            job_id=job_id,
            path=record.path,
            status="queued",
        )
        item_ids.append(item.id)

    await job_repo.session.commit()

    queued = await queue.put(item_ids)

    return {"job_id": job_id, "queued": queued, "total": len(records)}


@router.get("/dead-letter")
async def dead_letter(
    job_repo: IngestJobRepoDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    """List items that failed permanently (the dead-letter list)."""
    from sqlalchemy import select

    from founderdesk.db.models import IngestItem

    stmt = (
        select(IngestItem)
        .where(IngestItem.status == "failed")
        .order_by(IngestItem.updated_at.desc())
        .limit(limit)
    )
    rows = await job_repo.session.scalars(stmt)
    return {
        "items": [
            {
                "job_id": item.job_id,
                "path": item.path,
                "attempts": item.attempts,
                "error": item.error,
            }
            for item in rows
        ],
    }


@router.get("/{job_id}")
async def get_ingest_job(
    job_id: str,
    job_repo: IngestJobRepoDep,
) -> dict:
    """Return progress for one ingestion job."""
    job = await job_repo.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"No ingest job with id '{job_id}'.")
    counts = await job_repo.item_counts(job_id)
    return {
        "job_id": job.id,
        "status": job.status,
        "items_total": job.items_total,
        "items_done": counts.get("done", 0),
        "items_failed": counts.get("failed", 0),
        "items_skipped": counts.get("skipped", 0),
    }
