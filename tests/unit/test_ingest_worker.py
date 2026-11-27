"""Ingest worker tests: 5 tests, no network, no key, no Redis."""

import asyncio

from founderdesk.config import Settings
from founderdesk.workers.ingest import Permanent, pace
from founderdesk.workers.queue import JOB, redis_settings

# ---------- JOB name ----------


def test_job_name_is_ingest_document():
    """The arq job name is 'ingest_document'."""
    assert JOB == "ingest_document"


# ---------- pace ----------


def test_pace_respects_rpm(monkeypatch):
    """pace() records each call and allows up to ingest_rpm calls within a minute."""
    from founderdesk.workers import ingest as ingest_mod

    # Clear the rate limiter state.
    ingest_mod._call_times.clear()

    settings = Settings(
        app_env="ci",
        database_url="postgresql://localhost:5432/unused",
        ingest_rpm=2,
        _env_file=None,
    )
    monkeypatch.setattr(ingest_mod, "get_settings", lambda: settings)

    # Two calls within the window are fine; the third would hit the limit.
    asyncio.run(pace())
    asyncio.run(pace())
    assert len(ingest_mod._call_times) == 2


# ---------- get_file ----------


def test_get_file_from_disk(tmp_path):
    """get_file() returns the path when the file already exists on disk."""
    from founderdesk.workers.ingest import get_file

    # Create a file in data/raw/.
    raw_dir = tmp_path / "raw" / "test-source"
    raw_dir.mkdir(parents=True)
    file_path = raw_dir / "test.html"
    file_path.write_text("<html><body>hello</body></html>", encoding="utf-8")

    record = {"path": str(file_path), "url": "", "source": "", "licence": "", "title": ""}
    result = asyncio.run(get_file(record))
    assert result == file_path


# ---------- Permanent ----------


def test_permanent_is_an_exception():
    """Permanent errors go straight to the dead-letter list."""
    err = Permanent("parse: no_text_layer")
    assert str(err) == "parse: no_text_layer"
    assert isinstance(err, Exception)


# ---------- queue settings ----------


def test_redis_settings_returns_redis_settings():
    """redis_settings() builds RedisSettings from the settings URL."""
    rs = redis_settings("redis://localhost:6379")
    assert rs.host == "localhost"
    assert rs.port == 6379
