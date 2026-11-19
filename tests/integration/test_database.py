import asyncio
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from founderdesk.api.main import create_app
from founderdesk.config import Settings
from founderdesk.db.models import Document
from founderdesk.db.repository import DocumentRepository
from founderdesk.db.session import make_engine, make_sessionmaker

ROWS = [
    {"id": "001", "title": "Alpha", "kind": "circular", "year": 2024, "tags": ["a", "b"]},
    {"id": "002", "title": "Beta", "kind": "guideline", "year": 2025, "tags": ["b"]},
    {"id": "003", "title": "Gamma", "kind": "circular", "year": 2025, "tags": []},
]


@pytest.fixture
def settings(database_url):
    return Settings(app_env="ci", database_url=database_url, _env_file=None)


@pytest.fixture
async def seeded(settings):
    """Fresh rows for each test: delete, insert, and hand back the settings."""
    engine = make_engine(settings)
    async with make_sessionmaker(engine)() as session, session.begin():
        await session.execute(text("DELETE FROM documents"))
        for r in ROWS:
            meta = {k: v for k, v in r.items() if k not in ("id", "title")}
            session.add(
                Document(external_id=r["id"], title=r["title"], sha256=r["id"] * 21, metadata_=meta)
            )
    await engine.dispose()
    return settings


async def test_migrations_created_the_tables(settings):
    engine = make_engine(settings)
    async with engine.connect() as conn:
        tables = set(
            await conn.scalars(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        )
        version = await conn.scalar(text("SELECT version_num FROM alembic_version"))
    await engine.dispose()
    assert {"documents", "pages", "alembic_version"} <= tables
    assert version


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"kind": "circular"}, ["001", "003"]),
        ({"year": "2025"}, ["002", "003"]),  # text in the URL, number in JSONB
        ({"tags": "b"}, ["001", "002"]),  # an item inside a list
        ({"kind": "circular", "year": "2025"}, ["003"]),
    ],
)
async def test_repository_filters(seeded, filters, expected):
    engine = make_engine(seeded)
    async with make_sessionmaker(engine)() as session:
        total, items = await DocumentRepository(session).list(
            q=None, filters=filters, limit=10, offset=0
        )
    await engine.dispose()
    assert [i["id"] for i in items] == expected
    assert total == len(expected)


def test_api_against_real_database(seeded):
    with TestClient(create_app(seeded)) as client:
        assert client.get("/ready").json()["checks"]["database"] is True
        assert client.get("/v1/documents/002").json()["title"] == "Beta"
        assert client.get("/v1/documents", params={"q": "gamm"}).json()["total"] == 1


def test_loader_is_idempotent(database_url, tmp_path):
    data = tmp_path / "records.json"
    data.write_text(json.dumps(ROWS))
    settings = Settings(app_env="ci", database_url=database_url, data_file=data, _env_file=None)
    engine = make_engine(settings)
    make_sessionmaker(engine)

    async def run_load():
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "scripts/load_db.py",
            env={
                **os.environ,
                "APP_ENV": "ci",
                "DATABASE_URL": database_url,
                "DATA_FILE": str(data),
            },
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"load_db.py failed: {stderr.decode()}")
        return stdout.decode().strip()

    out1 = asyncio.run(run_load())
    out2 = asyncio.run(run_load())
    assert "inserted=3" in out1 and "updated=0" in out1
    assert "inserted=0" in out2 and "updated=0" in out2
    await engine.dispose()
