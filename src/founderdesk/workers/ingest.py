"""One job = one document: get the file, parse it, extract its record, store everything.

A job can run twice (the worker died, or a retry). That is safe, because every step first
checks what is already in the database: a document is identified by its content hash.
"""

import asyncio
import hashlib
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
from arq import Retry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from founderdesk.config import get_settings
from founderdesk.db.models import Document
from founderdesk.db.session import make_engine, make_sessionmaker
from founderdesk.ingest.fetch import HostGate, Manifest, Robots, fetch_one
from founderdesk.ingest.parse import ParseError, parse_file
from founderdesk.ingest.store import document_id, save_document

logger = logging.getLogger("founderdesk.workers.ingest")


class Permanent(Exception):
    """The error for things that will never work. Goes straight to the dead-letter list."""

    pass


# Rate limiter: at most ingest_rpm model calls a minute, shared by all jobs of the worker.
_call_times: list[float] = []


async def pace() -> None:
    """Wait until a model call slot is free (ingest_rpm per minute)."""
    settings = get_settings()
    now = time.monotonic()
    while _call_times and now - _call_times[0] > 60.0:
        _call_times.pop(0)
    if len(_call_times) >= settings.ingest_rpm:
        wait = 60.0 - (now - _call_times[0])
        if wait > 0:
            await asyncio.sleep(wait)
            now = time.monotonic()
            while _call_times and now - _call_times[0] > 60.0:
                _call_times.pop(0)
    _call_times.append(time.monotonic())


async def get_file(record: dict) -> Path:
    """The file from data/raw/ if it's there; otherwise download it politely."""
    path = Path(record["path"])
    if path.is_file():
        return path

    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.llm_request_timeout) as client:
        robots = Robots(client)
        gate = HostGate(0.5)
        semaphore = asyncio.Semaphore(1)
        manifest = Manifest()
        result = await fetch_one(
            url=record["url"],
            source=record["source"],
            licence=record.get("licence", ""),
            title=record.get("title", ""),
            client=client,
            robots=robots,
            gate=gate,
            semaphore=semaphore,
            manifest=manifest,
            delay=0.5,
            max_concurrency=1,
        )
        if result.path is None:
            raise Permanent(f"download: {result.error or 'failed'}")
        return result.path


async def process(item_id: int, item_path: str, session: AsyncSession) -> None:
    """Get the file, hash it, parse unless the document exists, extract unless current."""
    # Get the file and hash it to identify the document by content.
    full_path = await get_file(
        {"path": item_path, "url": "", "source": "", "licence": "", "title": ""}
    )
    sha = hashlib.sha256(full_path.read_bytes()).hexdigest()
    external_id = document_id(sha)

    # Idempotency: skip if this document already exists.
    existing = await session.scalar(select(Document).where(Document.external_id == external_id))
    if existing is not None:
        return

    # Parse unless the document exists.
    try:
        parsed = parse_file(full_path)
    except ParseError as error:
        raise Permanent(f"parse: {error.reason}") from error

    # Store the document.
    record = {
        "path": item_path,
        "url": "",
        "source": "",
        "licence": "",
        "title": parsed.title,
        "sha256": sha,
    }
    await save_document(session, record, parsed)

    # Extract unless its record is current.
    await pace()
    prompt_path = Path("prompts/extract_v1.md")
    if not prompt_path.is_file():
        raise Permanent("extract: no prompt file")
    prompt = prompt_path.read_text(encoding="utf-8")
    from founderdesk.llm.gateway import LLMGateway

    gateway = LLMGateway(get_settings())
    try:
        reply = await gateway.generate(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "\n".join(p.text for p in parsed.pages)},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        raise Permanent(f"extract: {exc}") from exc

    import json

    try:
        data = json.loads(reply.text)
    except json.JSONDecodeError:
        raise Permanent("extract: no JSON in reply") from None

    from founderdesk.llm.doc_meta import DocMeta

    try:
        DocMeta(**data)
    except Exception as exc:
        raise Permanent(f"extract: validation failed: {exc}") from exc

    await save_document(session, record, parsed)


async def ingest_document(ctx, item_id: int) -> None:
    """One arq job: process one document, deciding done / failed / retry.

    Counts the start in Postgres, runs process(), and on failure decides whether
    to retry (raise Retry) or set aside for good (Permanent).
    """
    from founderdesk.db.ingest_jobs import IngestJobRepository

    settings = get_settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)

    async with sessionmaker() as session:
        repo = IngestJobRepository(session)
        item = await repo.get_item(item_id)
        if item is None or item.status != "queued":
            return

        item.status = "running"
        item.attempts = (item.attempts or 0) + 1
        item.updated_at = datetime.now(UTC)
        await session.flush()

        try:
            await process(item_id, item.path, session)
            item.status = "done"
            await session.commit()
            logger.info("done item=%s path=%s", item_id, item.path)
        except Permanent as exc:
            item.status = "failed"
            item.error = str(exc)
            await session.commit()
            logger.warning("permanent item=%s path=%s error=%s", item_id, item.path, exc)
        except Exception as exc:
            item.status = "queued"
            item.error = str(exc)
            await session.commit()
            delay = 30.0 if item.attempts < 2 else 60.0
            logger.warning("retry item=%s path=%s error=%s in %ss", item_id, item.path, exc, delay)
            raise Retry(delay) from None
        finally:
            await engine.dispose()
