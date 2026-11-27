"""Dependencies: endpoints ask for these instead of building them."""

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from founderdesk.config import Settings
from founderdesk.db.ingest_jobs import IngestJobRepository
from founderdesk.db.llm_calls import UsageRepository
from founderdesk.db.repository import DocumentRepository
from founderdesk.ingest.fetch import Manifest
from founderdesk.llm.gateway import LLMGateway
from founderdesk.workers.queue import Queue


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """One session per request, closed automatically afterwards."""
    async with request.app.state.sessionmaker() as session:
        yield session


async def get_repo(session: Annotated[AsyncSession, Depends(get_session)]) -> DocumentRepository:
    return DocumentRepository(session)


async def get_ingest_repo(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IngestJobRepository:
    return IngestJobRepository(session)


async def get_usage_repo(session: Annotated[AsyncSession, Depends(get_session)]) -> UsageRepository:
    return UsageRepository(session)


async def get_gateway(request: Request) -> LLMGateway:
    return request.app.state.gateway


_queue: Queue | None = None


async def get_queue(request: Request) -> Queue:
    """Connect to Redis on first use, so the API starts even when Redis is down."""
    global _queue
    if _queue is None:
        _queue = await Queue.connect(request.app.state.settings.redis_url)
    return _queue


async def get_manifest() -> Manifest:
    return Manifest()


async def require_admin(request: Request) -> None:
    """Require the admin token for write endpoints."""
    token = request.headers.get("X-Admin-Token", "")
    settings = request.app.state.settings
    if not settings.admin_token or token != settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or wrong X-Admin-Token header.",
        )


async def check_db(request: Request) -> bool:
    """Can we run SELECT 1 within 2 seconds?"""
    try:
        async with request.app.state.engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=2)
        return True
    except Exception:
        return False


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
RepoDep = Annotated[DocumentRepository, Depends(get_repo)]
UsageDep = Annotated[UsageRepository, Depends(get_usage_repo)]
GatewayDep = Annotated[LLMGateway, Depends(get_gateway)]
IngestJobRepoDep = Annotated[IngestJobRepository, Depends(get_ingest_repo)]
ManifestDep = Annotated[Manifest, Depends(get_manifest)]
QueueDep = Annotated[Queue, Depends(get_queue)]
DbCheckDep = Annotated[bool, Depends(check_db)]
