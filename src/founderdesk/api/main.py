"""App factory: build a fully wired FastAPI app from settings."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI

from founderdesk.api.errors import register_error_handlers
from founderdesk.api.middleware import request_context
from founderdesk.api.routes import chat, documents, health, ingest, usage
from founderdesk.api.routes.chat import build_gateway, make_recorder
from founderdesk.config import Settings, get_settings
from founderdesk.db.ingest_jobs import IngestJobRepository
from founderdesk.db.session import make_engine, make_sessionmaker
from founderdesk.logging_setup import setup_logging

logger = logging.getLogger("founderdesk")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)
    engine = make_engine(settings)  # no connection is opened yet
    sessionmaker = make_sessionmaker(engine)

    # Load the system prompt at start-up: a missing prompt file stops the app at once.
    prompt_path = Path("prompts/chat_system_v1.md")
    system_prompt = prompt_path.read_text(encoding="utf-8")

    # Build the LLM gateway with a recorder that writes every call to Postgres.
    gateway = build_gateway(settings)
    gateway.record = make_recorder(sessionmaker)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("starting", extra={"status": settings.app_env})

        # Optionally run the worker inside the API (Render free plan has no worker service).
        if settings.worker_in_api:
            from arq import create_pool

            from founderdesk.workers.queue import redis_settings

            pool = await create_pool(redis_settings(settings.redis_url))
            async with sessionmaker() as session:
                repo = IngestJobRepository(session)
                items = await repo.claim_all_queued()
                logger.info("worker ready, %d unfinished item(s) put back in the queue", len(items))
            await pool.aclose()

        yield

        await engine.dispose()  # close every pooled connection on shutdown

    app = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.system_prompt = system_prompt
    app.state.gateway = gateway

    app.middleware("http")(request_context)
    register_error_handlers(app)

    v1 = APIRouter(prefix="/v1")
    v1.include_router(documents.router)
    v1.include_router(chat.router)
    v1.include_router(ingest.router)
    v1.include_router(usage.router)
    app.include_router(health.router)
    app.include_router(v1)
    return app
