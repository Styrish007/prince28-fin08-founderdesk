"""Ask, parse, validate, repair, store: metadata extraction pipeline."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from founderdesk.db.models import Document, Page
from founderdesk.llm.classify import latest_version
from founderdesk.llm.doc_meta import DocMeta
from founderdesk.llm.gateway import LLMGateway, LLMUnavailable

logger = logging.getLogger("founderdesk.llm.extract")

PROMPT_DIR = Path("prompts")
MAX_ATTEMPTS = 3


def _load_prompt(version: str | None = None) -> str:
    """Load the extraction prompt for ``version`` (e.g. ``extract_v1``)."""
    if version is None:
        path = latest_version("extract")
        if path is None:
            raise FileNotFoundError("no prompt file prompts/extract_v1.md")
    else:
        path = PROMPT_DIR / f"{version}.md"
    return path.read_text(encoding="utf-8")


def _parse_json(text: str) -> dict | None:
    """Parse a JSON object from the model's reply, forgiving of Markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


MAX_TEXT_CHARS = 12000  # truncate long documents to avoid provider payload limits


async def extract(
    gateway: LLMGateway,
    document_text: str,
    prompt: str,
) -> DocMeta | None:
    """Extract metadata from document text.

    Sends the prompt + document text, parses the JSON reply, validates against
    ``DocMeta``. On failure, sends back with the reason and retries (up to
    ``MAX_ATTEMPTS``). Returns ``None`` if all attempts fail.
    """

    # Truncate very long documents to avoid provider payload limits.
    text = document_text[:MAX_TEXT_CHARS] if len(document_text) > MAX_TEXT_CHARS else document_text

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": text},
    ]

    for _attempt in range(MAX_ATTEMPTS):
        try:
            reply = await gateway.generate(messages, response_format={"type": "json_object"})
        except LLMUnavailable:
            return None

        data = _parse_json(reply.text)
        if data is None:
            reason = "the reply contains no JSON object"
        else:
            try:
                return DocMeta(**data)
            except Exception as exc:
                reason = f"validation failed: {exc}"

        messages.append(
            {
                "role": "user",
                "content": f"Rejected: {reason}. Please fix and reply with one JSON object.",
            }
        )

    return None


async def pending(
    session: AsyncSession,
    prompt_version: str,
) -> list[tuple[int, str, str]]:
    """Return documents not yet processed by this prompt version.

    Each item is ``(document_id, title, concatenated_page_text)``.
    """
    subq = (
        select(Page.document_id, func.string_agg(Page.text, " ").label("full_text"))
        .group_by(Page.document_id)
        .subquery()
    )
    stmt = (
        select(Document.id, Document.title, subq.c.full_text)
        .join(subq, Document.id == subq.c.document_id)
        .where(Document.doc_type != "record")
        .where(~Document.metadata_.contains({"extract": {"prompt": prompt_version}}))
    )
    result = await session.execute(stmt)
    return [(row[0], row[1], row[2] or "") for row in result]


async def save(
    session: AsyncSession,
    document_id: int,
    record: DocMeta | None,
    prompt_version: str,
    error: str | None = None,
) -> None:
    """Merge the extracted record (or failure reason) into document metadata."""
    doc = await session.get(Document, document_id)
    if doc is None:
        return

    meta = dict(doc.metadata_) if doc.metadata_ else {}
    extract_entry: dict = {"prompt": prompt_version, "ok": record is not None}
    if record is not None:
        extract_entry["record"] = record.model_dump()
    if error is not None:
        extract_entry["error"] = error

    meta["extract"] = extract_entry
    doc.metadata_ = meta
    await session.flush()


async def run(
    gateway: LLMGateway,
    session: AsyncSession,
    prompt_version: str | None = None,
    rpm: int = 12,
) -> dict:
    """Process all pending documents.

    Paces calls at ``rpm`` per minute. Stops when no model can answer twice
    in a row. Returns a stats dict.
    """
    if prompt_version is None:
        path = latest_version("extract")
        if path is None:
            raise FileNotFoundError("no prompt file prompts/extract_v1.md")
        prompt_version = path.stem

    prompt = _load_prompt(prompt_version)
    docs = await pending(session, prompt_version)

    stats = {"ok": 0, "repaired": 0, "failed": 0, "total": len(docs)}
    consecutive_failures = 0
    min_interval = 60.0 / rpm

    for doc_id, title, text in docs:
        start = time.monotonic()
        try:
            record = await extract(gateway, text, prompt)
            if record is None:
                stats["failed"] += 1
                consecutive_failures += 1
                await save(session, doc_id, None, prompt_version, error="no model could answer")
                logger.info("failed %s %s", doc_id, title)
            else:
                stats["ok"] += 1
                consecutive_failures = 0
                await save(session, doc_id, record, prompt_version)
                logger.info("ok %s %s", doc_id, title)
        except LLMUnavailable:
            stats["failed"] += 1
            consecutive_failures += 1
            await save(session, doc_id, None, prompt_version, error="no model could answer")
            logger.info("failed %s %s (unavailable)", doc_id, title)

        if consecutive_failures >= 2:
            logger.info("stopped: no model can answer twice in a row")
            break

        elapsed = time.monotonic() - start
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)

    await session.commit()
    return stats
