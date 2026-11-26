"""Question router tests: 7 tests, no network, no key."""

import asyncio

import pytest

from founderdesk.config import Settings
from founderdesk.llm.classify import build_messages, classify, find_leaks, parse_label
from founderdesk.llm.gateway import FakeLLM, LLMGateway

# ---------- build_messages ----------


def test_build_messages_structure():
    """System message is the prompt; user text goes inside <question> tags."""
    prompt = "You are a router."
    question = "What is DPIIT recognition?"
    messages = build_messages(prompt, question)
    assert len(messages) == 2
    assert messages[0] == {"role": "system", "content": prompt}
    assert messages[1] == {
        "role": "user",
        "content": "<question>\nWhat is DPIIT recognition?\n</question>",
    }


# ---------- parse_label ----------


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("docs", "docs"),
        ("personal", "personal"),
        ("off_topic", "off_topic"),
        ("Docs.", "docs"),
        ("DOCS", "docs"),
        (" Personal ", "personal"),
        ("off-topic", "off_topic"),
    ],
)
def test_parse_label_forgiving(reply, expected):
    """Forgives capitalisation and trailing punctuation."""
    assert parse_label(reply) == expected


@pytest.mark.parametrize(
    "reply",
    [
        "docs personal",
        "",
        "maybe",
        "documentation",
        "off topic",
        "docs, personal",
    ],
)
def test_parse_label_invalid(reply):
    """Two labels, no label, or unknown word → None."""
    assert parse_label(reply) is None


# ---------- find_leaks ----------


def test_find_leaks_no_test_set(tmp_path, monkeypatch):
    """No test set file → no leaks."""
    monkeypatch.chdir(tmp_path)
    assert find_leaks() == []


# ---------- classify with FakeLLM ----------


@pytest.fixture
def fake_gateway():
    """Gateway backed by a FakeLLM provider."""
    fake = FakeLLM(replies=["docs"])
    settings = Settings(
        app_env="ci",
        database_url="postgresql://localhost:5432/unused",
        _env_file=None,
    )
    return LLMGateway(settings, providers=[fake]), fake


def test_classify_returns_parsed_label(fake_gateway):
    """classify() routes through the gateway and returns the parsed label."""
    gateway, fake = fake_gateway
    label, raw = asyncio.run(classify(gateway, "What is DPIIT recognition?"))
    assert label == "docs"
    assert raw == "docs"
    assert fake.call_count == 1


def test_classify_records_seen_messages(fake_gateway):
    """FakeLLM.seen records every message list it was asked."""
    gateway, fake = fake_gateway

    async def main():
        await classify(gateway, "Will my startup get funded?")
        await classify(gateway, "What is seed fund?")

    asyncio.run(main())
    assert len(fake.seen) == 2
    assert "Will my startup get funded?" in fake.seen[0][1]["content"]
    assert "What is seed fund?" in fake.seen[1][1]["content"]


def test_classify_invalid_reply_returns_none(fake_gateway):
    """An invalid label reply → None label."""
    gateway, fake = fake_gateway
    fake.replies = ["maybe"]

    async def main():
        return await classify(gateway, "What is DPIIT recognition?")

    label, _ = asyncio.run(main())
    assert label is None
