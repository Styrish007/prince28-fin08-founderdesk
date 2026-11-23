"""Tests for the polite resumable downloader. No internet needed.

httpx.MockTransport plays the website: the tests decide what each URL answers
(503, 429, a broken connection) and check what the downloader does.
"""

import asyncio
import time
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from founderdesk.ingest.fetch import (
    HostGate,
    Manifest,
    Robots,
    backoff_with_jitter,
    fetch_one,
    filename_for,
    retryable_status,
    sha256_of_file,
)


def make_client(handler):
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


def respond(status, body=b"", headers=None):
    return httpx.Response(
        status_code=status,
        content=body,
        headers=headers or {},
        request=httpx.Request("GET", "https://example.com/doc.pdf"),
    )


# --- Robots ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_robots_404_allowed():
    async def handler(request):
        return respond(404)

    async with make_client(handler) as client:
        robots = Robots(client)
        assert await robots.allowed("https://example.com/page") is True


@pytest.mark.asyncio
async def test_robots_5xx_skips_site():
    async def handler(request):
        return respond(503)

    async with make_client(handler) as client:
        robots = Robots(client)
        assert await robots.allowed("https://example.com/page") is False


@pytest.mark.asyncio
async def test_robots_disallows_path():
    async def handler(request):
        body = "User-agent: *\nDisallow: /private/\nAllow: /public/\n"
        return respond(200, body=body.encode())

    async with make_client(handler) as client:
        robots = Robots(client)
        assert await robots.allowed("https://example.com/private/x") is False
        assert await robots.allowed("https://example.com/public/y") is True


# --- HostGate --------------------------------------------------------------


@pytest.mark.asyncio
async def test_hostgate_spaces_requests():
    gate = HostGate(min_delay=0.05)
    start = time.monotonic()
    await gate.gate("https://example.com/a")
    await gate.gate("https://example.com/b")
    elapsed = time.monotonic() - start
    # Same host, two requests with a 0.05s gap between them.
    assert elapsed >= 0.04


@pytest.mark.asyncio
async def test_hostgate_different_hosts_no_delay():
    gate = HostGate(min_delay=1.0)
    start = time.monotonic()
    await gate.gate("https://one.example.com/a")
    await gate.gate("https://two.example.com/b")
    elapsed = time.monotonic() - start
    assert elapsed < 0.5


# --- retryable / backoff ---------------------------------------------------


@pytest.mark.parametrize(
    "status,expected",
    [
        (200, False),
        (403, False),
        (404, False),
        (429, True),
        (500, True),
        (502, True),
        (503, True),
        (504, True),
    ],
)
def test_retryable_status(status, expected):
    assert retryable_status(status) is expected


def test_backoff_respects_retry_after():
    wait = backoff_with_jitter(attempt=0, retry_after=10.0)
    assert wait == 10.0


def test_backoff_capped():
    wait = backoff_with_jitter(attempt=100, retry_after=None)
    assert wait <= 120.0


# --- filename_for ----------------------------------------------------------


def test_filename_keeps_pdf():
    name = filename_for("https://site.com/reports/annual-2024.pdf", "application/pdf", "src")
    assert name == "annual-2024.pdf"


def test_filename_adds_ext_for_html():
    name = filename_for("https://site.com/page", "text/html", "src")
    assert name.endswith(".html")


def test_filename_sanitizes():
    name = filename_for("https://site.com/a weird! name.pdf", "application/pdf", "src")
    assert "!" not in name


# --- sha256_of_file --------------------------------------------------------


def test_sha256_of_file(tmp_path):
    p = tmp_path / "f.txt"
    p.write_bytes(b"hello world")
    h = sha256_of_file(p)
    import hashlib

    assert h == hashlib.sha256(b"hello world").hexdigest()


# --- Manifest --------------------------------------------------------------


def test_manifest_roundtrip(tmp_path):
    mp = tmp_path / "manifest.jsonl"
    m = Manifest(path=mp)
    m.add(
        type(
            "R",
            (),
            {
                "url": "https://example.com/a.pdf",
                "source": "src",
                "licence": "CC BY",
                "title": "a",
                "path": "data/raw/src/a.pdf",
                "sha256": "abc",
                "size": 10,
                "fetched_at": "2026-01-01T00:00:00+00:00",
                "status": "downloaded",
            },
        )()
    )
    assert m.has("src", "https://example.com/a.pdf") is True
    assert m.has("src", "https://example.com/b.pdf") is False
    assert m.has("other", "https://example.com/a.pdf") is False


# --- fetch_one -------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_one_skips_manifested():
    mp = Path(tmp_manifest())
    m = Manifest(path=mp)
    m.add(
        type(
            "R",
            (),
            {
                "url": "https://example.com/a.pdf",
                "source": "src",
                "licence": "CC BY",
                "title": "a",
                "path": "data/raw/src/a.pdf",
                "sha256": "abc",
                "size": 10,
                "fetched_at": "2026-01-01T00:00:00+00:00",
                "status": "downloaded",
            },
        )()
    )

    async def handler(request):
        return respond(200, body=b"data")

    async with make_client(handler) as client:
        robots = Robots(client)
        gate = HostGate(min_delay=0)
        sem = asyncio.Semaphore(4)
        res = await fetch_one(
            "https://example.com/a.pdf",
            "src",
            "CC BY",
            "a",
            client,
            robots,
            gate,
            sem,
            m,
            delay=0,
            max_concurrency=4,
        )
    assert res.status == "skipped"


@pytest.mark.asyncio
async def test_fetch_one_blocks_robots():
    mp = Path(tmp_manifest())
    m = Manifest(path=mp)

    async def handler(request):
        if request.url.path == "/robots.txt":
            return respond(
                200,
                body=b"User-agent: *\nDisallow: /\n",
            )
        return respond(200, body=b"data")

    async with make_client(handler) as client:
        robots = Robots(client)
        gate = HostGate(min_delay=0)
        sem = asyncio.Semaphore(4)
        res = await fetch_one(
            "https://example.com/a.pdf",
            "src",
            "CC BY",
            "a",
            client,
            robots,
            gate,
            sem,
            m,
            delay=0,
            max_concurrency=4,
        )
    assert res.status == "blocked"


@pytest.mark.asyncio
async def test_fetch_one_downloads_and_hashes(tmp_path):
    mp = tmp_path / "manifest.jsonl"
    m = Manifest(path=mp)
    body = b"PDF content here"

    async def handler(request):
        if request.url.path == "/robots.txt":
            return respond(200, body=b"User-agent: *\nAllow: /\n")
        return respond(200, body=body, headers={"content-type": "application/pdf"})

    async with make_client(handler) as client:
        robots = Robots(client)
        gate = HostGate(min_delay=0)
        sem = asyncio.Semaphore(4)
        res = await fetch_one(
            "https://example.com/a.pdf",
            "src",
            "CC BY",
            "a",
            client,
            robots,
            gate,
            sem,
            m,
            delay=0,
            max_concurrency=4,
        )
    assert res.status == "downloaded"
    assert res.path is not None
    assert res.path.read_bytes() == body
    assert res.sha256 == __import__("hashlib").sha256(body).hexdigest()
    assert res.size == len(body)
    assert m.has("src", "https://example.com/a.pdf")


@pytest.mark.asyncio
async def test_fetch_one_retries_then_fails_on_503(tmp_path):
    mp = tmp_path / "manifest.jsonl"
    m = Manifest(path=mp)
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        if request.url.path == "/robots.txt":
            return respond(200, body=b"User-agent: *\nAllow: /\n")
        if calls["n"] < 3:
            return respond(503)
        return respond(200, body=b"ok")

    async with make_client(handler) as client:
        robots = Robots(client)
        gate = HostGate(min_delay=0)
        sem = asyncio.Semaphore(4)
        with patch("founderdesk.ingest.fetch.backoff_with_jitter", return_value=0.01):
            res = await fetch_one(
                "https://example.com/a.pdf",
                "src",
                "CC BY",
                "a",
                client,
                robots,
                gate,
                sem,
                m,
                delay=0,
                max_concurrency=4,
                attempts=5,
            )
    assert res.status == "downloaded"
    assert calls["n"] == 3  # robots.txt + 1 x 503 + success


@pytest.mark.asyncio
async def test_fetch_one_fails_on_404_without_retry(tmp_path):
    mp = tmp_path / "manifest.jsonl"
    m = Manifest(path=mp)
    calls = {"n": 0}

    async def handler(request):
        calls["n"] += 1
        if request.url.path == "/robots.txt":
            return respond(200, body=b"User-agent: *\nAllow: /\n")
        return respond(404)

    async with make_client(handler) as client:
        robots = Robots(client)
        gate = HostGate(min_delay=0)
        sem = asyncio.Semaphore(4)
        res = await fetch_one(
            "https://example.com/a.pdf",
            "src",
            "CC BY",
            "a",
            client,
            robots,
            gate,
            sem,
            m,
            delay=0,
            max_concurrency=4,
            attempts=5,
        )
    assert res.status == "failed"
    assert calls["n"] == 2  # robots.txt + 404 (not retried)


def tmp_manifest():
    import tempfile

    return tempfile.mktemp(suffix=".jsonl")
