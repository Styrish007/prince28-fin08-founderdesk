"""One raw HTTP call per LLM provider, no gateway in between.

Usage: uv run python scripts/llm_ping.py

Calls Gemini (primary) and Groq (fallback) with "Reply with one word: pong"
and prints how each responded, with timings and token counts.
"""

import asyncio
import time

import httpx

from founderdesk.config import get_settings


async def ping(settings) -> None:
    calls = [
        {
            "provider": "gemini",
            "url": f"{settings.llm_primary_base_url}/chat/completions",
            "key": settings.gemini_api_key,
            "model": settings.llm_primary_model,
        },
        {
            "provider": "groq",
            "url": f"{settings.llm_fallback_base_url}/chat/completions",
            "key": settings.groq_api_key,
            "model": settings.llm_fallback_model,
        },
    ]

    body = {
        "model": "{model}",
        "messages": [{"role": "user", "content": "Reply with one word: pong"}],
        "temperature": 0,
    }

    for call in calls:
        provider = call["provider"]
        url = call["url"]
        key = call["key"]
        model = call["model"]

        if not key:
            print(f"{provider:10s} NO KEY   (set {provider.upper()}_API_KEY in .env)")
            continue

        payload = dict(body)
        payload["model"] = model

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=settings.llm_request_timeout) as client:
                resp = await client.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            elapsed_ms = (time.monotonic() - start) * 1000
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            print(f"{provider:10s} FAILED   {type(exc).__name__}: {exc} ({elapsed_ms:.0f} ms)")
            continue

        if resp.status_code >= 400:
            print(
                f"{provider:10s} FAILED   HTTP {resp.status_code} "
                f"{resp.text[:200]} ({elapsed_ms:.0f} ms)"
            )
            continue

        data = resp.json()
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        print(
            f"{provider:10s} OK       {model} said '{text.strip()}' "
            f"in {elapsed_ms:.0f} ms, tokens in={tokens_in} out={tokens_out}"
        )


def main() -> None:
    settings = get_settings()
    asyncio.run(ping(settings))


if __name__ == "__main__":
    main()
