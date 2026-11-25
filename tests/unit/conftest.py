import pytest
from fastapi.testclient import TestClient

from founderdesk.api.deps import check_db, get_gateway, get_repo, get_usage_repo
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


@pytest.fixture
def settings():
    # _env_file=None: ignore your local .env so tests behave the same everywhere
    return Settings(app_env="ci", database_url="postgresql://localhost:5432/unused", _env_file=None)


@pytest.fixture
def db_state():
    return {"up": True}


@pytest.fixture
def llm():
    return FakeLLM(replies=["this is a fake answer"])


@pytest.fixture
def client(settings, db_state, llm):
    app = create_app(settings)
    app.dependency_overrides[get_repo] = lambda: FakeRepo(SAMPLE)
    app.dependency_overrides[check_db] = lambda: db_state["up"]
    app.dependency_overrides[get_gateway] = lambda: llm
    app.dependency_overrides[get_usage_repo] = lambda: FakeUsage()
    with TestClient(app) as c:
        yield c
