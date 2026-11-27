"""Ingest job tests against a real Postgres: the four-test checklist."""

import pytest

from founderdesk.config import Settings
from founderdesk.db.ingest_jobs import IngestJobRepository
from founderdesk.db.models import IngestItem, IngestJob
from founderdesk.db.session import make_engine, make_sessionmaker


@pytest.fixture
async def session(database_url):
    engine = make_engine(Settings(app_env="ci", database_url=database_url, _env_file=None))
    async with make_sessionmaker(engine)() as db:
        await db.execute(IngestItem.__table__.delete())
        await db.execute(IngestJob.__table__.delete())
        await db.commit()
        yield db
    await engine.dispose()


async def test_create_and_get_job(session):
    """A job can be created and read back."""
    repo = IngestJobRepository(session)
    await repo.create_job("job-1", items_total=10)
    await session.commit()

    got = await repo.get_job("job-1")
    assert got is not None
    assert got.id == "job-1"
    assert got.status == "queued"
    assert got.items_total == 10


async def test_claim_one_marks_running(session):
    """claim_one() marks a queued item as running and bumps attempts."""
    repo = IngestJobRepository(session)
    await repo.create_job("job-1", items_total=2)
    await repo.save_item("job-1", "data/raw/a.html", status="queued")
    await repo.save_item("job-1", "data/raw/b.html", status="queued")
    await session.commit()

    item = await repo.claim_one()
    assert item is not None
    assert item.status == "running"
    assert item.attempts == 1


async def test_save_item_and_counts(session):
    """save_item() stores results; item_counts() tallies by status."""
    repo = IngestJobRepository(session)
    await repo.create_job("job-1", items_total=3)
    await repo.save_item("job-1", "data/raw/a.html", status="done")
    await repo.save_item("job-1", "data/raw/b.html", status="failed", error="parse: no_text_layer")
    await repo.save_item("job-1", "data/raw/c.html", status="skipped")
    await session.commit()

    counts = await repo.item_counts("job-1")
    assert counts["done"] == 1
    assert counts["failed"] == 1
    assert counts["skipped"] == 1


async def test_update_job_status(session):
    """update_job() changes status and counters."""
    repo = IngestJobRepository(session)
    await repo.create_job("job-1", items_total=5)
    await session.commit()

    await repo.update_job("job-1", status="running", items_done=2, items_failed=1)
    await session.commit()

    got = await repo.get_job("job-1")
    assert got.status == "running"
    assert got.items_done == 2
    assert got.items_failed == 1
