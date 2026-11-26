"""Extraction results are written to and read from a real Postgres."""

import pytest
from sqlalchemy import select

from founderdesk.config import Settings
from founderdesk.db.models import Document
from founderdesk.db.session import make_engine, make_sessionmaker
from founderdesk.llm.doc_meta import DocMeta


@pytest.fixture
async def session(database_url):
    engine = make_engine(Settings(app_env="ci", database_url=database_url, _env_file=None))
    async with make_sessionmaker(engine)() as db:
        await db.execute(Document.__table__.delete())
        await db.commit()
        yield db
    await engine.dispose()


async def test_extracted_record_is_stored_in_document_metadata(session):
    """An extracted DocMeta is merged into documents.metadata and can be read back."""
    doc = Document(
        external_id="extract-test-1",
        title="Test Document",
        doc_type="html",
        metadata_={},
    )
    session.add(doc)
    await session.flush()

    record = DocMeta(
        doc_kind="faq",
        year=2023,
        language="en",
        summary="A short summary of the document content.",
        topics=["startup", "recognition"],
        scheme=["dpiit_recognition"],
        authority=["DPIIT"],
        state=["other"],
        benefit_type=["recognition"],
    )

    from founderdesk.llm.extract import save

    await save(session, doc.id, record, "extract_v1")
    await session.commit()

    row = await session.scalar(select(Document).where(Document.external_id == "extract-test-1"))
    assert row is not None
    assert row.metadata_ is not None
    assert row.metadata_["extract"]["ok"] is True
    assert row.metadata_["extract"]["prompt"] == "extract_v1"
    assert row.metadata_["extract"]["record"]["doc_kind"] == "faq"
    assert row.metadata_["extract"]["record"]["year"] == 2023
