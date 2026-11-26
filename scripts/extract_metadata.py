"""Command line around extract.run(): extract metadata from parsed documents."""

import argparse
import asyncio

from sqlalchemy import select

from founderdesk.config import get_settings
from founderdesk.db.models import Document
from founderdesk.db.session import make_engine, make_sessionmaker
from founderdesk.llm.extract import run
from founderdesk.llm.gateway import LLMGateway


async def _amain(
    limit: int | None,
    retry_failed: bool,
    rpm: int,
    schema: bool,
) -> None:
    settings = get_settings()
    engine = make_engine(settings)
    sessionmaker = make_sessionmaker(engine)

    gateway = LLMGateway(settings)

    async with sessionmaker() as session:
        if retry_failed:
            stmt = (
                select(Document.id)
                .where(Document.doc_type != "record")
                .where(Document.metadata_.contains({"extract": {"ok": False}}))
            )
            result = await session.execute(stmt)
            failed_ids = [row[0] for row in result]
            print(f"retrying {len(failed_ids)} failed documents")
            for doc_id in failed_ids:
                doc = await session.get(Document, doc_id)
                if doc:
                    meta = dict(doc.metadata_) if doc.metadata_ else {}
                    meta.pop("extract", None)
                    doc.metadata_ = meta
            await session.commit()

        stats = await run(gateway, session, rpm=rpm)
        print(
            f"prompt=extract_v1 pending={stats['total']} ok={stats['ok']} "
            f"repaired={stats['repaired']} failed={stats['failed']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract metadata from parsed documents")
    parser.add_argument("--limit", type=int, default=None, help="max documents to process")
    parser.add_argument(
        "--retry-failed", action="store_true", help="retry previously failed documents"
    )
    parser.add_argument("--rpm", type=int, default=12, help="requests per minute")
    parser.add_argument("--schema", action="store_true", help="send JSON schema as response_format")
    args = parser.parse_args()
    asyncio.run(_amain(args.limit, args.retry_failed, args.rpm, args.schema))


if __name__ == "__main__":
    main()
