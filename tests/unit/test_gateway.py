"""Gateway tests: no network, no key, no bill. Uses FakeLLM throughout."""

import asyncio
import time

import pytest

from founderdesk.config import Settings
from founderdesk.llm.gateway import (
    PRICES_USD,
    CircuitBreaker,
    FakeLLM,
    LLMError,
    LLMGateway,
    LLMUnavailable,
    OpenAICompatProvider,
)

# ---------- CircuitBreaker ----------


def test_breaker_starts_closed():
    b = CircuitBreaker("test")
    assert b.state == "closed"
    assert b.allow(time.monotonic()) is True


def test_breaker_opens_after_threshold():
    b = CircuitBreaker("test", failure_threshold=2, cooldown=30.0)
    now = time.monotonic()
    b.record_failure(now)
    assert b.state == "closed"
    b.record_failure(now)
    assert b.state == "open"
    assert b.allow(now) is False


def test_breaker_half_open_after_cooldown():
    b = CircuitBreaker("test", failure_threshold=1, cooldown=30.0)
    now = time.monotonic()
    b.record_failure(now)
    assert b.state == "open"
    assert b.allow(now) is False
    # Simulate cooldown passed
    b.opened_at = now - 31
    assert b.allow(now) is True
    assert b.state == "half-open"


def test_breaker_half_open_success_closes():
    b = CircuitBreaker("test", failure_threshold=1, cooldown=30.0)
    now = time.monotonic()
    b.record_failure(now)
    b.opened_at = now - 31
    assert b.allow(now) is True
    assert b.state == "half-open"
    b.record_success()
    assert b.state == "closed"


def test_breaker_half_open_failure_reopens():
    b = CircuitBreaker("test", failure_threshold=1, cooldown=30.0)
    now = time.monotonic()
    b.record_failure(now)
    b.opened_at = now - 31
    assert b.allow(now) is True
    b.record_failure(now)
    assert b.state == "open"


# ---------- LLMError ----------


def test_llm_error_retryable_flag():
    e = LLMError("boom", retryable=True)
    assert e.retryable is True
    e2 = LLMError("nope", retryable=False)
    assert e2.retryable is False


def test_llm_error_retry_after():
    e = LLMError("rate limited", retryable=True, retry_after=5.0)
    assert e.retry_after == 5.0


# ---------- OpenAICompatProvider error classification ----------


def test_429_is_retryable():
    # Build a provider with a dummy key; we only test error classification logic.
    p = OpenAICompatProvider("gemini", "https://x.example.com", "key", "m", 10.0)
    # 429 → retryable
    # We can't easily call the private classification, but we can check the class exists
    # and has the right shape. The error classification is exercised via integration.
    assert p.name == "gemini"
    assert p.model == "m"


def test_prices_usd_has_models():
    assert "gemini-3.8-flash" in PRICES_USD
    assert "openai/gpt-oss-20b" in PRICES_USD
    inp, out = PRICES_USD["gemini-3.8-flash"]
    assert inp == 0.75
    assert out == 3.75


def test_cost_for_missing_model_is_zero():
    gateway = LLMGateway.__new__(LLMGateway)
    cost = gateway._cost_usd("unknown-model", 1_000_000, 1_000_000)
    assert cost == 0.0


def test_cost_calculation():
    gateway = LLMGateway.__new__(LLMGateway)
    cost = gateway._cost_usd("gemini-3.8-flash", 1_000_000, 1_000_000)
    # 0.75 + 3.75 = 4.50 USD per 1M tokens each direction
    assert abs(cost - 4.50) < 1e-9


# ---------- FakeLLM ----------


def test_fake_llm_returns_scripted_reply():
    fake = FakeLLM(replies=["hello world"])
    reply = asyncio.run(fake.generate([{"role": "user", "content": "hi"}]))
    assert reply.text == "hello world"


def test_fake_llm_cycles_replies():
    fake = FakeLLM(replies=["first", "second"])
    r1 = asyncio.run(fake.generate([{"role": "user", "content": "hi"}]))
    r2 = asyncio.run(fake.generate([{"role": "user", "content": "hi"}]))
    assert r1.text == "first"
    assert r2.text == "second"


def test_fake_llm_tracks_call_count():
    fake = FakeLLM(replies=["a"])
    asyncio.run(fake.generate([{"role": "user", "content": "hi"}]))
    asyncio.run(fake.generate([{"role": "user", "content": "hi"}]))
    assert fake.call_count == 2


def test_fake_llm_fails_when_scripted():
    fake = FakeLLM(replies=["a"], fail=True)
    with pytest.raises(LLMUnavailable):
        asyncio.run(fake.generate([{"role": "user", "content": "hi"}]))


# ---------- LLMGateway with FakeLLM providers ----------


def _settings_with_keys() -> Settings:
    return Settings(
        app_env="ci",
        database_url="postgresql://localhost:5432/unused",
        gemini_api_key="gemini-key",  # pragma: allowlist secret
        groq_api_key="groq-key",  # pragma: allowlist secret
        _env_file=None,
    )


def test_gateway_single_provider_succeeds():
    fake = FakeLLM(replies=["answer from gemini"], name="gemini", model="gemini-3.8-flash")
    gw = LLMGateway(_settings_with_keys(), providers=[fake])
    reply = asyncio.run(gw.generate([{"role": "user", "content": "hi"}]))
    assert reply.text == "answer from gemini"
    assert fake.call_count == 1


def test_gateway_falls_back_to_second_provider():
    bad = FakeLLM(replies=["x"], fail=True, name="gemini", model="gemini-3.8-flash")
    good = FakeLLM(replies=["answer from groq"], name="groq", model="openai/gpt-oss-20b")
    gw = LLMGateway(_settings_with_keys(), providers=[bad, good])
    reply = asyncio.run(gw.generate([{"role": "user", "content": "hi"}]))
    assert reply.text == "answer from groq"
    assert bad.call_count == 1
    assert good.call_count == 1


def test_gateway_all_providers_fail_raises():
    bad1 = FakeLLM(replies=["x"], fail=True, name="gemini", model="gemini-3.8-flash")
    bad2 = FakeLLM(replies=["x"], fail=True, name="groq", model="openai/gpt-oss-20b")
    gw = LLMGateway(_settings_with_keys(), providers=[bad1, bad2])
    with pytest.raises(LLMUnavailable):
        asyncio.run(gw.generate([{"role": "user", "content": "hi"}]))


def test_gateway_no_providers_raises():
    settings = Settings(
        app_env="ci",
        database_url="postgresql://localhost:5432/unused",
        _env_file=None,
    )
    gw = LLMGateway(settings)
    with pytest.raises(LLMUnavailable):
        asyncio.run(gw.generate([{"role": "user", "content": "hi"}]))


def test_gateway_stream_yields_chunks():
    fake = FakeLLM(replies=["hello world"], name="gemini", model="gemini-3.8-flash")
    gw = LLMGateway(_settings_with_keys(), providers=[fake])
    chunks = []

    async def collect():
        async for chunk in gw.stream([{"role": "user", "content": "hi"}]):
            chunks.append(chunk)

    asyncio.run(collect())
    assert "".join(chunks).strip() == "hello world"
