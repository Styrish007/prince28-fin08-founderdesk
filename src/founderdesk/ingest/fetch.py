"""Polite, resumable downloader for your corpus.

The rules it follows, in order:
1. Ask robots.txt first (RFC 9309). Not allowed means never requested.
2. At most `max_concurrency` downloads at once, and a pause between two requests to one site.
3. A timeout on every request. Only errors that can heal are retried (429, 5xx, network),
   with exponential backoff + jitter, and Retry-After is obeyed.
4. Write to <name>.part and rename when complete: a killed run never leaves a half file.
5. One line per file in data/manifest.jsonl, so the next run skips what is already there.
"""

import asyncio
import hashlib
import json
import random
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit

import httpx
from protego import Protego

# Say who you are and where to complain. Site owners see this in their logs.
CONTACT = "https://github.com/Styrish007/prince28-fin08-founderdesk"
ROBOTS_TOKEN = "examate-student-bot"  # the name robots.txt rules are matched against
USER_AGENT = f"{ROBOTS_TOKEN}/0.1 (student project; +{CONTACT})"

RETRYABLE = {408, 425, 429, 500, 502, 503, 504}  # these can heal; 403 or 404 will not
MAX_WAIT = 120.0  # never sleep longer than this between attempts
MAX_BYTES = 200 * 1024 * 1024  # refuse files above 200 MB
ATTEMPT_TIMEOUT = 300.0  # one attempt may take at most 5 minutes in total
KNOWN_EXT = {
    ".pdf", ".html", ".htm", ".json", ".txt", ".md", ".mdx", ".rst", ".adoc", ".csv",
    ".xml", ".yaml", ".yml", ".zip", ".docx", ".xlsx", ".xls",
}  # fmt: skip
EXT_BY_TYPE = {
    "application/pdf": ".pdf",
    "text/html": ".html",
    "text/plain": ".txt",
    "application/json": ".json",
    "text/markdown": ".md",
    "application/xml": ".xml",
    "text/xml": ".xml",
}

# Sentinel returned by Robots._fetch when robots.txt is a server error or
# unreachable: the whole site must be skipped (not treated as "404 allowed").
_ROBOTS_BLOCKED: object = object()


@dataclass
class Source:
    url: str
    source: str
    licence: str
    title: str = ""


@dataclass
class Result:
    source: str
    url: str
    path: Path | None
    status: str  # downloaded | skipped | blocked | failed
    size: int = 0
    sha256: str = ""
    error: str = ""
    attempts: int = 0
    seconds: float = 0.0


def source_folder(source: str) -> Path:
    return Path("data/raw") / source


def manifest_path() -> Path:
    return Path("data/manifest.jsonl")


def load_manifest() -> dict[str, dict]:
    """Read existing manifest lines keyed by url+source."""
    mp = manifest_path()
    if not mp.exists():
        return {}
    entries: dict[str, dict] = {}
    with mp.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = f"{rec.get('source', '')}\t{rec.get('url', '')}"
            entries[key] = rec
    return entries


def append_manifest(record: dict) -> None:
    manifest_path().parent.mkdir(parents=True, exist_ok=True)
    with manifest_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def filename_for(url: str, content_type: str | None, source: str) -> str:
    path = urlsplit(url).path
    name = unquote(path.rstrip("/").split("/")[-1] or "index")
    if "." not in name:
        ext = EXT_BY_TYPE.get((content_type or "").split(";")[0].strip(), ".html")
        name = name + ext
    elif not any(name.lower().endswith(e) for e in KNOWN_EXT):
        ext = EXT_BY_TYPE.get((content_type or "").split(";")[0].strip())
        if ext:
            name = name + ext
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return safe or "document"


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class Robots:
    """Fetches and caches each site's robots.txt once."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client
        self._cache: dict[str, Protego | None | object] = {}

    async def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._cache:
            self._cache[base] = await self._fetch(base)
        robot = self._cache[base]
        if robot is _ROBOTS_BLOCKED:
            return False  # robots.txt 5xx / unreachable → skip the whole site
        if robot is None:
            return True  # 404 → allowed, per RFC 9309
        return robot.can_fetch(url, USER_AGENT)

    async def _fetch(self, base: str) -> Protego | None | object:
        try:
            resp = await self.client.get(
                base + "/robots.txt",
                headers={"User-Agent": USER_AGENT},
                timeout=30.0,
            )
        except (httpx.HTTPError, OSError):
            return _ROBOTS_BLOCKED  # network error → skip the whole site
        if resp.status_code >= 500:
            return _ROBOTS_BLOCKED  # server error → skip the whole site
        if resp.status_code == 404:
            return None  # not found → allowed, per RFC 9309
        if resp.status_code >= 400:
            return _ROBOTS_BLOCKED  # other client error → skip the whole site
        try:
            return Protego.parse(resp.text)
        except Exception:
            return _ROBOTS_BLOCKED


class HostGate:
    """A pause between two hits on one site."""

    def __init__(self, min_delay: float) -> None:
        self.min_delay = min_delay
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def gate(self, url: str) -> None:
        host = urlsplit(url).netloc
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            last = self._last.get(host, 0.0)
            wait = self.min_delay - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last[host] = time.monotonic()


def retryable_status(status: int) -> bool:
    return status in RETRYABLE


def backoff_with_jitter(attempt: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return min(retry_after, MAX_WAIT)
    base = min(2**attempt, MAX_WAIT)
    return min(base + random.random() * base, MAX_WAIT)


@dataclass
class ManifestRecord:
    url: str
    source: str
    licence: str
    title: str
    path: str
    sha256: str
    size: int
    fetched_at: str
    status: str


class Manifest:
    """One JSON line per file in data/manifest.jsonl."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or manifest_path()
        self._entries: dict[str, ManifestRecord] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._loaded = True
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = f"{rec.get('source', '')}\t{rec.get('url', '')}"
                self._entries[key] = ManifestRecord(
                    url=rec.get("url", ""),
                    source=rec.get("source", ""),
                    licence=rec.get("licence", ""),
                    title=rec.get("title", ""),
                    path=rec.get("path", ""),
                    sha256=rec.get("sha256", ""),
                    size=rec.get("size", 0),
                    fetched_at=rec.get("fetched_at", ""),
                    status=rec.get("status", ""),
                )
        self._loaded = True

    def has(self, source: str, url: str) -> bool:
        self._load()
        return f"{source}\t{url}" in self._entries

    def add(self, record: ManifestRecord) -> None:
        self._load()
        key = f"{record.source}\t{record.url}"
        self._entries[key] = record
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "url": record.url,
                        "source": record.source,
                        "licence": record.licence,
                        "title": record.title,
                        "path": record.path,
                        "sha256": record.sha256,
                        "size": record.size,
                        "fetched_at": record.fetched_at,
                        "status": record.status,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


async def fetch_one(
    url: str,
    source: str,
    licence: str,
    title: str,
    client: httpx.AsyncClient,
    robots: Robots,
    gate: HostGate,
    semaphore: asyncio.Semaphore,
    manifest: Manifest,
    delay: float,
    max_concurrency: int,
    attempts: int = 5,
) -> Result:
    """Download one URL politely, resume-safe, with retries."""
    start = time.monotonic()
    if manifest.has(source, url):
        return Result(
            source=source,
            url=url,
            path=None,
            status="skipped",
            seconds=time.monotonic() - start,
        )

    if not await robots.allowed(url):
        return Result(
            source=source,
            url=url,
            path=None,
            status="blocked",
            seconds=time.monotonic() - start,
        )

    last_error = ""
    status = "failed"
    path: Path | None = None
    size = 0
    sha256 = ""

    async with semaphore:
        for attempt in range(attempts):
            await gate.gate(url)
            retry_after: float | None = None
            try:
                path, size, sha256, retry_after = await _download(url, source, client, attempt)
                status = "downloaded"
                last_error = ""
                break
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                last_error = f"HTTP {code}"
                if code in (403, 404):
                    status = "failed"
                    break
                if code in RETRYABLE and attempt < attempts - 1:
                    wait = backoff_with_jitter(attempt, retry_after)
                    await asyncio.sleep(min(wait, MAX_WAIT))
                    continue
                status = "failed"
                break
            except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout, OSError) as exc:
                last_error = type(exc).__name__
                if attempt < attempts - 1:
                    wait = backoff_with_jitter(attempt, None)
                    await asyncio.sleep(min(wait, MAX_WAIT))
                    continue
                status = "failed"
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                status = "failed"
                break

    if path is not None:
        manifest.add(
            ManifestRecord(
                url=url,
                source=source,
                licence=licence,
                title=title,
                path=str(path),
                sha256=sha256,
                size=size,
                fetched_at=datetime.now(UTC).isoformat(),
                status=status,
            )
        )

    return Result(
        source=source,
        url=url,
        path=path,
        status=status,
        size=size,
        sha256=sha256,
        error=last_error,
        attempts=attempts if status == "failed" else 1,
        seconds=time.monotonic() - start,
    )


async def _download(
    url: str, source: str, client: httpx.AsyncClient, attempt: int
) -> tuple[Path, int, str, float | None]:
    folder = source_folder(source)
    folder.mkdir(parents=True, exist_ok=True)
    resp = await client.get(url, headers={"User-Agent": USER_AGENT}, timeout=ATTEMPT_TIMEOUT)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type")
    name = filename_for(url, content_type, source)
    final_path = folder / name
    part_path = folder / (name + ".part")

    h = hashlib.sha256()
    total = 0
    with part_path.open("wb") as f:
        async for chunk in resp.aiter_bytes(65536):
            total += len(chunk)
            if total > MAX_BYTES:
                part_path.unlink(missing_ok=True)
                raise httpx.HTTPStatusError("file too large", request=resp.request, response=resp)
            h.update(chunk)
            f.write(chunk)
    sha256 = h.hexdigest()
    part_path.rename(final_path)

    retry_after: float | None = None
    ra = resp.headers.get("retry-after")
    if ra:
        try:
            retry_after = float(ra)
        except ValueError:
            try:
                dt = parsedate_to_datetime(ra)
                retry_after = max(0.0, (dt - datetime.now(UTC)).total_seconds())
            except Exception:
                retry_after = None

    return final_path, total, sha256, retry_after
