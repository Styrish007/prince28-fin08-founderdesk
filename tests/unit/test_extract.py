"""Extraction tests: 8 tests, no network, no key."""

import asyncio

import pytest
from pydantic import ValidationError

from founderdesk.config import Settings
from founderdesk.llm.doc_meta import DocMeta
from founderdesk.llm.extract import _parse_json, extract
from founderdesk.llm.gateway import FakeLLM, LLMGateway

# ---------- _parse_json ----------


def test_parse_json_plain():
    """A plain JSON object parses through."""
    assert _parse_json('{"doc_kind": "faq", "year": 2023}') == {
        "doc_kind": "faq",
        "year": 2023,
    }


def test_parse_json_with_fences():
    """Markdown fences are stripped before parsing."""
    text = '```json\n{"doc_kind": "rule"}\n```'
    assert _parse_json(text) == {"doc_kind": "rule"}


def test_parse_json_invalid():
    """Non-JSON returns None."""
    assert _parse_json("not json at all") is None


# ---------- DocMeta validation ----------


def test_doc_meta_valid():
    """A valid record passes validation."""
    record = DocMeta(
        doc_kind="faq",
        year=2023,
        language="en",
        summary="A short summary of the document content.",
        topics=["recognition", "startup"],
        scheme=[],
        authority=[],
        state=[],
        benefit_type=[],
    )
    assert record.doc_kind == "faq"
    assert record.year == 2023


def test_doc_meta_extra_field_forbidden():
    """Unknown keys are rejected (extra='forbid')."""
    with pytest.raises(ValidationError):
        DocMeta(
            doc_kind="faq",
            year=2023,
            language="en",
            summary="A short summary of the document content.",
            topics=["recognition"],
            scheme=[],
            authority=[],
            state=[],
            benefit_type=[],
            unknown_field="nope",
        )


# ---------- extract with FakeLLM ----------


def _settings_with_keys() -> Settings:
    return Settings(
        app_env="ci",
        database_url="postgresql://localhost:5432/unused",
        _env_file=None,
    )


def _make_gateway(replies: list[str]) -> tuple[LLMGateway, FakeLLM]:
    fake = FakeLLM(replies=replies, name="extract", model="extract-model")
    return LLMGateway(_settings_with_keys(), providers=[fake]), fake


def test_extract_success():
    """A valid JSON reply validates into DocMeta."""
    ok_reply = (
        '{"doc_kind": "faq", "year": 2023, "language": "en", '
        '"summary": "A short summary of the document content.", '
        '"topics": ["startup"], "scheme": [], "authority": [], '
        '"state": [], "benefit_type": []}'
    )
    gateway, fake = _make_gateway([ok_reply])
    record = asyncio.run(
        extract(gateway, "Some document text about startup recognition.", "You are an extractor.")
    )
    assert record is not None
    assert record.doc_kind == "faq"
    assert record.year == 2023


def test_extract_invalid_then_repair():
    """An invalid reply is sent back; a valid reply on retry succeeds."""
    bad_reply = "not json"
    ok_reply = (
        '{"doc_kind": "rule", "year": 2024, "language": "en", '
        '"summary": "A short summary of the document content.", '
        '"topics": ["policy"], "scheme": [], "authority": [], '
        '"state": [], "benefit_type": []}'
    )
    gateway, fake = _make_gateway([bad_reply, ok_reply])
    record = asyncio.run(extract(gateway, "Some document text.", "You are an extractor."))
    assert record is not None
    assert record.doc_kind == "rule"
    assert fake.call_count == 2


def test_extract_all_attempts_fail():
    """Three invalid replies → None."""
    gateway, fake = _make_gateway(["bad", "also bad", "still bad"])
    record = asyncio.run(extract(gateway, "Some document text.", "You are an extractor."))
    assert record is None
    assert fake.call_count == 3
