"""One door to every LLM provider.

The rest of the app calls gateway.generate() or gateway.stream() and never knows which
provider answered. The gateway adds what production needs: a timeout, retries with
backoff on 429 and 5xx, a fallback model, a circuit breaker, and a record of every call
(tokens, latency, cost in rupees).
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import httpx

from founderdesk.config import Settings

logger = logging.getLogger("founderdesk.llm")

# US dollars per 1 million tokens (input, output). List prices read on 22 Nov 2026:
# check the providers' pricing pages and update this table when they change.
PRICES_USD = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "openai/gpt-oss-20b": (0.075, 0.30),
    "openai/gpt-oss-120b": (0.15, 0.60),
}
MAX_WAIT = 20.0  # never sleep longer than this between two attempts

Message = dict[str, str]
Recorder = Callable[[dict], Awaitable[None]]


class LLMError(Exception):
    """One provider call failed. `retryable`: is trying the same provider again worth it?"""

    def __init__(self, message: str, *, retryable: bool, retry_after: float | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


class LLMUnavailable(Exception):
    """No provider could answer: all failed, are switched off, or none is configured."""


@dataclass
class Reply:
    """What a provider returns. When streaming, the provider fills in the token counts."""

    text: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0


class CircuitBreaker:
    """20-line circuit breaker: closed → open → half-open → closed."""

    def __init__(self, name: str, failure_threshold: int = 3, cooldown: float = 30.0) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown = cooldown
        self.state = "closed"
        self.failures = 0
        self.opened_at: float | None = None

    def record_success(self) -> None:
        self.failures = 0
        self.state = "closed"
        self.opened_at = None

    def record_failure(self, now: float) -> None:
        self.failures += 1
        if self.state == "half-open" or self.failures >= self.failure_threshold:
            self.state = "open"
            self.opened_at = now

    def allow(self, now: float) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if self.opened_at is not None and now - self.opened_at >= self.cooldown:
                self.state = "half-open"
                return True
            return False
        # half-open: allow one trial call
        return True


class OpenAICompatProvider:
    """HTTP client for any OpenAI-compatible chat/completions endpoint (Gemini, Groq, …)."""

    def __init__(self, name: str, base_url: str, api_key: str, model: str, timeout: float) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.last_usage: dict[str, int] | None = None

    async def generate(self, messages: list[Message]) -> Reply:
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0,
                        "stream": False,
                    },
                )
        except httpx.TimeoutException as exc:
            raise LLMError(f"{self.name}: request timed out", retryable=True) from exc
        except httpx.ConnectError as exc:
            raise LLMError(f"{self.name}: cannot connect", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.name}: HTTP error {exc}", retryable=False) from exc

        latency_ms = int((time.monotonic() - start) * 1000)

        if resp.status_code == 429:
            retry_after = None
            ra = resp.headers.get("retry-after")
            if ra:
                try:
                    retry_after = float(ra)
                except ValueError:
                    retry_after = None
            raise LLMError(
                f"{self.name}: rate limited (429)",
                retryable=True,
                retry_after=retry_after,
            )
        if resp.status_code in (401, 403):
            raise LLMError(
                f"{self.name}: invalid API key (HTTP {resp.status_code})",
                retryable=False,
            )
        if resp.status_code >= 500:
            raise LLMError(f"{self.name}: server error (HTTP {resp.status_code})", retryable=True)
        if resp.status_code >= 400:
            raise LLMError(f"{self.name}: bad request (HTTP {resp.status_code})", retryable=False)

        try:
            data = resp.json()
        except json.JSONDecodeError as exc:
            raise LLMError(f"{self.name}: invalid JSON response", retryable=False) from exc

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        text = message.get("content", "") or ""
        usage = data.get("usage", {}) or {}

        return Reply(
            text=text,
            tokens_in=int(usage.get("prompt_tokens", 0) or 0),
            tokens_out=int(usage.get("completion_tokens", 0) or 0),
            latency_ms=latency_ms,
        )

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        """Yield text chunks as they arrive from the provider."""
        time.monotonic()
        try:
            async with (
                httpx.AsyncClient(timeout=self.timeout) as client,
                client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0,
                        "stream": True,
                    },
                ) as resp,
            ):
                if resp.status_code == 429:
                    retry_after = None
                    ra = resp.headers.get("retry-after")
                    if ra:
                        try:
                            retry_after = float(ra)
                        except ValueError:
                            retry_after = None
                    raise LLMError(
                        f"{self.name}: rate limited (429)",
                        retryable=True,
                        retry_after=retry_after,
                    )
                if resp.status_code in (401, 403):
                    raise LLMError(
                        f"{self.name}: invalid API key (HTTP {resp.status_code})",
                        retryable=False,
                    )
                if resp.status_code >= 500:
                    raise LLMError(
                        f"{self.name}: server error (HTTP {resp.status_code})",
                        retryable=True,
                    )
                if resp.status_code >= 400:
                    raise LLMError(
                        f"{self.name}: bad request (HTTP {resp.status_code})",
                        retryable=False,
                    )

                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        return
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    # Some providers include usage in the final chunk.
                    if data.get("usage"):
                        self.last_usage = data["usage"]
                    delta = (data.get("choices") or [{}])[0].get("delta", {}) or {}
                    chunk = delta.get("content", "") or ""
                    if chunk:
                        yield chunk
        except httpx.TimeoutException as exc:
            raise LLMError(f"{self.name}: request timed out", retryable=True) from exc
        except httpx.ConnectError as exc:
            raise LLMError(f"{self.name}: cannot connect", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.name}: HTTP error {exc}", retryable=False) from exc


class LLMGateway:
    """Gemini first, Groq as fallback, with a circuit breaker on each provider."""

    def __init__(
        self,
        settings: Settings,
        record: Recorder | None = None,
        providers: list[OpenAICompatProvider] | None = None,
    ) -> None:
        self.settings = settings
        self.record = record
        self.breakers: dict[str, CircuitBreaker] = {}
        self.last_provider: str | None = None
        self.last_model: str | None = None
        self.last_fallback_used: bool = False

        if providers is not None:
            self.providers = providers
        else:
            self.providers = self._build_providers(settings)

        for p in self.providers:
            self.breakers[p.name] = CircuitBreaker(p.name)

    @staticmethod
    def _build_providers(settings: Settings) -> list[OpenAICompatProvider]:
        providers: list[OpenAICompatProvider] = []
        if settings.gemini_api_key:
            providers.append(
                OpenAICompatProvider(
                    "gemini",
                    settings.llm_primary_base_url,
                    settings.gemini_api_key,
                    settings.llm_primary_model,
                    settings.llm_request_timeout,
                )
            )
        if settings.groq_api_key:
            providers.append(
                OpenAICompatProvider(
                    "groq",
                    settings.llm_fallback_base_url,
                    settings.groq_api_key,
                    settings.llm_fallback_model,
                    settings.llm_request_timeout,
                )
            )
        return providers

    def _cost_usd(self, model: str, tokens_in: int, tokens_out: int) -> float:
        prices = PRICES_USD.get(model, (0.0, 0.0))
        return (tokens_in / 1_000_000) * prices[0] + (tokens_out / 1_000_000) * prices[1]

    async def _record_call(
        self,
        provider: str,
        model: str,
        status: str,
        error: str | None,
        tokens_in: int,
        tokens_out: int,
        latency_ms: int,
        cost_inr: float,
        fallback_used: bool,
        request_id: str | None,
    ) -> None:
        payload = {
            "provider": provider,
            "model": model,
            "status": status,
            "error": error,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms,
            "cost_inr": cost_inr,
            "fallback_used": fallback_used,
            "request_id": request_id,
        }
        logger.info(
            "llm call %s %s %s tokens_in=%d tokens_out=%d latency_ms=%d cost_inr=%.6f fallback=%s",
            provider,
            model,
            status,
            tokens_in,
            tokens_out,
            latency_ms,
            cost_inr,
            fallback_used,
        )
        if self.record is not None:
            try:
                await self.record(payload)
            except Exception:
                logger.exception("could not record the llm call")

    async def _try_provider(
        self,
        provider: OpenAICompatProvider,
        messages: list[Message],
        stream: bool,
        request_id: str | None,
    ) -> Reply:
        breaker = self.breakers[provider.name]
        now = time.monotonic()
        if not breaker.allow(now):
            raise LLMError(f"{provider.name}: circuit open", retryable=False)

        last_error: str | None = None
        for attempt in range(2):
            try:
                if stream:
                    # For streaming, we collect chunks and return a Reply at the end.
                    # The actual streaming is handled by stream() which calls this per-provider.
                    chunks: list[str] = []
                    async for chunk in provider.stream(messages):
                        chunks.append(chunk)
                    text = "".join(chunks)
                    # We don't know token counts from streaming unless provider reports them.
                    reply = Reply(text=text, latency_ms=int((time.monotonic() - now) * 1000))
                else:
                    reply = await provider.generate(messages)
                    reply.latency_ms = int((time.monotonic() - now) * 1000)
                breaker.record_success()
                return reply
            except (LLMError, LLMUnavailable) as exc:
                if isinstance(exc, LLMUnavailable):
                    exc = LLMError(str(exc), retryable=False)
                last_error = str(exc)
                if not exc.retryable:
                    breaker.record_failure(now)
                    raise
                if attempt == 0:
                    wait = exc.retry_after or 1.0
                    wait = min(wait, MAX_WAIT)
                    await asyncio.sleep(wait)
                else:
                    breaker.record_failure(now)
        raise LLMError(last_error or f"{provider.name}: failed", retryable=False)

    async def generate(self, messages: list[Message], request_id: str | None = None) -> Reply:
        """Try each provider in order: breaker check → up to 2 tries → next provider."""
        if not self.providers:
            raise LLMUnavailable("No LLM provider is configured")

        fallback_used = False
        last_error: str | None = None

        for idx, provider in enumerate(self.providers):
            if idx > 0:
                fallback_used = True
            try:
                reply = await self._try_provider(
                    provider, messages, stream=False, request_id=request_id
                )
                self.last_provider = provider.name
                self.last_model = provider.model
                self.last_fallback_used = fallback_used
                cost_usd = self._cost_usd(provider.model, reply.tokens_in, reply.tokens_out)
                cost_inr = cost_usd * self.settings.usd_inr
                await self._record_call(
                    provider.name,
                    provider.model,
                    "ok",
                    None,
                    reply.tokens_in,
                    reply.tokens_out,
                    reply.latency_ms,
                    cost_inr,
                    fallback_used,
                    request_id,
                )
                return reply
            except (LLMError, LLMUnavailable) as exc:
                last_error = f"{provider.name}: {exc}"
                logger.warning("llm call %s %s error: %s", provider.name, provider.model, exc)
                continue

        # All providers failed — record the failure on the last attempted provider.
        if self.providers:
            p = self.providers[-1]
            cost_inr = 0.0
            await self._record_call(
                p.name,
                p.model,
                "error",
                str(last_error),
                0,
                0,
                0,
                cost_inr,
                fallback_used,
                request_id,
            )
        raise LLMUnavailable(f"No model could answer: {last_error}")

    async def stream(
        self, messages: list[Message], request_id: str | None = None
    ) -> AsyncIterator[str]:
        """Stream chunks, changing provider only if nothing has been shown yet."""
        if not self.providers:
            raise LLMUnavailable("No LLM provider is configured")

        fallback_used = False
        last_error: str | None = None
        yielded_any = False

        for idx, provider in enumerate(self.providers):
            if idx > 0:
                fallback_used = True
            try:
                self.last_provider = provider.name
                self.last_model = provider.model
                self.last_fallback_used = fallback_used
                breaker = self.breakers[provider.name]
                now = time.monotonic()
                if not breaker.allow(now):
                    raise LLMError(f"{provider.name}: circuit open", retryable=False)

                async for chunk in provider.stream(messages):
                    if not yielded_any:
                        yielded_any = True
                    yield chunk

                breaker.record_success()
                usage = provider.last_usage or {}
                tokens_in = int(usage.get("prompt_tokens", 0) or 0)
                tokens_out = int(usage.get("completion_tokens", 0) or 0)
                cost_usd = self._cost_usd(provider.model, tokens_in, tokens_out)
                cost_inr = cost_usd * self.settings.usd_inr
                await self._record_call(
                    provider.name,
                    provider.model,
                    "ok",
                    None,
                    tokens_in,
                    tokens_out,
                    0,
                    cost_inr,
                    fallback_used,
                    request_id,
                )
                return
            except (LLMError, LLMUnavailable) as exc:
                last_error = f"{provider.name}: {exc}"
                logger.warning("llm stream %s %s error: %s", provider.name, provider.model, exc)
                breaker.record_failure(now)
                if yielded_any:
                    # Already showed something; can't switch mid-stream.
                    raise LLMUnavailable(f"The answer stopped: {last_error}") from exc
                continue

        if self.providers:
            p = self.providers[-1]
            cost_inr = 0.0
            await self._record_call(
                p.name,
                p.model,
                "error",
                str(last_error),
                0,
                0,
                0,
                cost_inr,
                fallback_used,
                request_id,
            )
        raise LLMUnavailable(f"No model could answer: {last_error}")


class FakeLLM:
    """Scripted stand-in: tests use this instead of calling real providers."""

    def __init__(
        self,
        replies: list[str] | None = None,
        fail: bool = False,
        name: str = "fake",
        model: str = "fake-model",
    ) -> None:
        self.replies = replies or ["pong"]
        self.fail = fail
        self.call_count = 0
        self.name = name
        self.model = model
        self.breakers: dict[str, CircuitBreaker] = {}
        self.last_provider: str | None = None
        self.last_model: str | None = None
        self.last_fallback_used: bool = False
        self.last_usage: dict[str, int] | None = None

    def set_replies(self, replies: list[str]) -> None:
        self.replies = replies

    async def generate(self, messages: list[Message], request_id: str | None = None) -> Reply:
        self.call_count += 1
        if self.fail:
            raise LLMUnavailable("FakeLLM is scripted to fail")
        text = self.replies[min(self.call_count - 1, len(self.replies) - 1)]
        return Reply(text=text, tokens_in=10, tokens_out=5, latency_ms=100)

    async def stream(
        self, messages: list[Message], request_id: str | None = None
    ) -> AsyncIterator[str]:
        self.call_count += 1
        if self.fail:
            raise LLMUnavailable("FakeLLM is scripted to fail")
        text = self.replies[min(self.call_count - 1, len(self.replies) - 1)]
        for word in text.split():
            yield word + " "
