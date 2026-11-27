import pytest
from fastapi.testclient import TestClient

from founderdesk.api.deps import (
    check_db,
    get_gateway,
    get_ingest_repo,
    get_manifest,
    get_queue,
    get_repo,
    get_usage_repo,
)
from founderdesk.api.main import create_app
from founderdesk.config import Settings
from founderdesk.llm.gateway import FakeLLM

# Tiny fake records: unit tests never touch a real database or your data file.
SAMPLE = [
    {
        "id": "001",
        "title": "Alpha guideline",
        "year": 2023,
        "kind": "guideline",
        "pages": [
            {"page_no": 1, "text": "# Alpha\n\nGuideline content here.", "headings": ["Alpha"]},
            {"page_no": 2, "text": "More content on page 2.", "headings": ["Alpha", "Section 2"]},
        ],
    },
    {
        "id": "002",
        "title": "Beta circular",
        "year": 2024,
        "kind": "circular",
        "pages": [
            {"page_no": 1, "text": "# Beta\n\nCircular content.", "headings": ["Beta"]},
        ],
    },
    {
        "id": "003",
        "title": "Gamma notice",
        "year": 2025,
        "kind": "circular",
        "pages": [
            {"page_no": 1, "text": "# Gamma\n\nNotice content.", "headings": ["Gamma"]},
        ],
    },
]


class FakeRepo:
    """Behaves like DocumentRepository, but keeps rows in a Python list."""

    def __init__(self, rows):
        self.rows = rows

    async def list(self, *, q, filters, limit, offset):
        rows = [
            r
            for r in self.rows
            if (not q or q.lower() in str(r).lower())
            and all(str(r.get(k)) == v for k, v in filters.items())
        ]
        return len(rows), rows[offset : offset + limit]

    async def get(self, external_id):
        return next((r for r in self.rows if r["id"] == external_id), None)

    async def get_page(self, external_id, page_no):
        doc = next((r for r in self.rows if r["id"] == external_id), None)
        if doc is None:
            return None
        pages = doc.get("pages", [])
        return next((p for p in pages if p["page_no"] == page_no), None)


class FakeUsage:
    """Stand-in for UsageRepository in unit tests."""

    def __init__(self):
        self.totals = {
            "calls": 0,
            "errors": 0,
            "fallbacks": 0,
            "tokens_in": 0,
            "tokens_out": 0,
            "cost_inr": 0.0,
        }

    async def daily_totals(self, day=None):
        return dict(self.totals)


class FakeIngestJobRepository:
    """Stand-in for IngestJobRepository in unit tests."""

    def __init__(self):
        self.jobs = {}
        self.items = []
        self.session = _FakeSession(self)

    async def create_job(self, job_id: str, items_total: int):
        self.jobs[job_id] = {
            "id": job_id,
            "status": "queued",
            "items_total": items_total,
            "items_done": 0,
            "items_failed": 0,
            "items_skipped": 0,
        }
        return type("Job", (), {"id": job_id})()

    async def get_job(self, job_id: str):
        d = self.jobs.get(job_id)
        if d is None:
            return None
        return type("Job", (), d)()

    async def update_job(
        self,
        job_id: str,
        *,
        status=None,
        items_done=None,
        items_failed=None,
        items_skipped=None,
    ):
        if job_id in self.jobs:
            if status is not None:
                self.jobs[job_id]["status"] = status
            if items_done is not None:
                self.jobs[job_id]["items_done"] = items_done
            if items_failed is not None:
                self.jobs[job_id]["items_failed"] = items_failed
            if items_skipped is not None:
                self.jobs[job_id]["items_skipped"] = items_skipped

    async def save_item(
        self,
        job_id: str,
        path: str,
        *,
        status: str,
        error: str | None = None,
    ):
        self.items.append(
            {
                "job_id": job_id,
                "path": path,
                "status": status,
                "error": error,
            }
        )
        return type("Item", (), {"id": len(self.items), "job_id": job_id, "path": path})()

    async def claim_one(self):
        return None

    async def claim_all_queued(self):
        return []

    async def list_items(self, job_id: str, status=None):
        items = [i for i in self.items if i["job_id"] == job_id]
        if status is not None:
            items = [i for i in items if i["status"] == status]
        return len(items), items

    async def item_counts(self, job_id: str) -> dict[str, int]:
        items = [i for i in self.items if i["job_id"] == job_id]
        counts = {"done": 0, "failed": 0, "skipped": 0, "queued": 0, "running": 0}
        for item in items:
            counts[item["status"]] = counts.get(item["status"], 0) + 1
        return counts


class _Item:
    def __init__(self, d):
        self.__dict__.update(d)


class _FakeSession:
    def __init__(self, repo):
        self.repo = repo

    async def commit(self):
        pass

    async def flush(self):
        pass

    async def scalars(self, stmt):
        return [_Item(item) for item in self.repo.items if item.get("status") == "failed"]

    async def execute(self, stmt):
        class Result:
            def __init__(self, rows):
                self._rows = rows

            def all(self):
                return self._rows

        return Result([])


class FakeQueue:
    """Stand-in for Queue in unit tests."""

    def __init__(self):
        self.queued = []

    async def put(self, item_ids: list[int]) -> int:
        self.queued.extend(item_ids)
        return len(item_ids)

    async def close(self):
        pass


class FakeManifest:
    """Stand-in for Manifest in unit tests."""

    def __init__(self):
        self.entries = {}

    def values(self):
        return self.entries.values()


@pytest.fixture
def settings():
    # _env_file=None: ignore your local .env so tests behave the same everywhere
    return Settings(
        app_env="ci",
        database_url="postgresql://localhost:5432/unused",
        admin_token="test-token",
        _env_file=None,
    )


@pytest.fixture
def db_state():
    return {"up": True}


@pytest.fixture
def llm():
    return FakeLLM(replies=["this is a fake answer"])


@pytest.fixture
def fake_ingest_repo():
    return FakeIngestJobRepository()


@pytest.fixture
def fake_queue():
    return FakeQueue()


@pytest.fixture
def fake_manifest():
    return FakeManifest()


@pytest.fixture
def client(settings, db_state, llm, fake_ingest_repo, fake_queue, fake_manifest):
    app = create_app(settings)
    app.dependency_overrides[get_repo] = lambda: FakeRepo(SAMPLE)
    app.dependency_overrides[check_db] = lambda: db_state["up"]
    app.dependency_overrides[get_gateway] = lambda: llm
    app.dependency_overrides[get_usage_repo] = lambda: FakeUsage()
    app.dependency_overrides[get_ingest_repo] = lambda: fake_ingest_repo
    app.dependency_overrides[get_queue] = lambda: fake_queue
    app.dependency_overrides[get_manifest] = lambda: fake_manifest
    with TestClient(app) as c:
        yield c
