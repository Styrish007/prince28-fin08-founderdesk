"""The worker process: takes jobs from Redis one by one."""

import logging

from founderdesk.config import get_settings
from founderdesk.db.ingest_jobs import IngestJobRepository
from founderdesk.db.session import make_engine, make_sessionmaker
from founderdesk.workers.ingest import ingest_document
from founderdesk.workers.queue import redis_settings

logger = logging.getLogger("founderdesk.workers.main")


class WorkerSettings:
    functions = [ingest_document]

    @staticmethod
    def redis_settings():
        return redis_settings(get_settings().redis_url)

    async def startup(self):
        """Put every unfinished item back in the queue.

        Recovery for a Redis that lost its memory: every item still marked
        queued or running in Postgres is re-queued.
        """
        settings = get_settings()
        engine = make_engine(settings)
        sessionmaker = make_sessionmaker(engine)
        async with sessionmaker() as session:
            repo = IngestJobRepository(session)
            items = await repo.claim_all_queued()
            logger.info("worker ready, %d unfinished item(s) put back in the queue", len(items))
        await engine.dispose()

    async def shutdown(self):
        pass
