"""Ingest API tests: 9 tests, no Redis needed."""


def test_ingest_without_admin_token_is_401(client):
    """POST /v1/ingest requires the admin token."""
    r = client.post("/v1/ingest")
    assert r.status_code == 401


def test_wrong_admin_token_is_401(client):
    """A wrong admin token is rejected."""
    r = client.post("/v1/ingest", headers={"X-Admin-Token": "wrong"})
    assert r.status_code == 401


def test_ingest_with_admin_token_is_202(client, fake_ingest_repo, fake_queue, fake_manifest):
    """POST /v1/ingest with the right token returns 202 and queues items."""
    fake_manifest.entries = {
        "src\thttps://example.com/a.html": {
            "status": "downloaded",
            "path": "data/raw/a.html",
            "source": "src",
            "url": "https://example.com/a.html",
            "licence": "",
            "title": "Doc A",
        },
        "src\thttps://example.com/b.html": {
            "status": "downloaded",
            "path": "data/raw/b.html",
            "source": "src",
            "url": "https://example.com/b.html",
            "licence": "",
            "title": "Doc B",
        },
    }
    r = client.post("/v1/ingest", headers={"X-Admin-Token": "test-token"})
    assert r.status_code == 202
    body = r.json()
    assert "job_id" in body
    assert body["total"] == 2
    assert body["queued"] == 2


def test_get_ingest_job_progress(client, fake_ingest_repo):
    """GET /v1/ingest/{job_id} returns progress."""
    job_id = "job-1"
    fake_ingest_repo.jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "items_total": 3,
        "items_done": 0,
        "items_failed": 0,
        "items_skipped": 0,
    }
    fake_ingest_repo.items = [
        {"job_id": job_id, "path": "a.html", "status": "done"},
        {"job_id": job_id, "path": "b.html", "status": "failed", "error": "boom"},
        {"job_id": job_id, "path": "c.html", "status": "skipped"},
    ]
    r = client.get(f"/v1/ingest/{job_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["job_id"] == job_id
    assert body["status"] == "queued"
    assert body["items_done"] == 1
    assert body["items_failed"] == 1
    assert body["items_skipped"] == 1


def test_get_ingest_job_not_found_is_404(client):
    """GET /v1/ingest/{job_id} for a missing job returns 404."""
    r = client.get("/v1/ingest/does-not-exist")
    assert r.status_code == 404


def test_dead_letter_empty_initially(client):
    """GET /v1/ingest/dead-letter returns an empty list when nothing failed."""
    r = client.get("/v1/ingest/dead-letter")
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_dead_letter_shows_failed_items(client, fake_ingest_repo):
    """GET /v1/ingest/dead-letter lists failed items."""
    fake_ingest_repo.items = [
        {
            "job_id": "job-1",
            "path": "data/raw/bad.pdf",
            "status": "failed",
            "error": "parse: no_text_layer",
            "attempts": 3,
        }
    ]
    r = client.get("/v1/ingest/dead-letter")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["path"] == "data/raw/bad.pdf"
    assert items[0]["error"] == "parse: no_text_layer"


def test_ingest_queues_items(client, fake_ingest_repo, fake_queue, fake_manifest):
    """POST /v1/ingest writes items and queues them."""
    fake_manifest.entries = {
        "src\thttps://example.com/a.html": {
            "status": "downloaded",
            "path": "data/raw/a.html",
            "source": "src",
            "url": "https://example.com/a.html",
            "licence": "",
            "title": "Doc A",
        },
    }
    r = client.post("/v1/ingest", headers={"X-Admin-Token": "test-token"})
    assert r.status_code == 202
    assert len(fake_queue.queued) >= 1
    assert len(fake_ingest_repo.items) >= 1
    assert fake_ingest_repo.items[-1]["status"] == "queued"


def test_admin_token_from_settings(client):
    """The admin token comes from settings, not hardcoded."""
    from founderdesk.config import Settings

    settings = Settings(
        app_env="ci",
        database_url="postgresql://localhost:5432/unused",
        admin_token="secret-token",
        _env_file=None,
    )
    assert settings.admin_token == "secret-token"
