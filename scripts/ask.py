"""Tiny client: prints the streamed answer and times it.

Usage:
  uv run python scripts/ask.py "Your question here"
  uv run python scripts/ask.py "Your question here" --json
  uv run python scripts/ask.py "Your question here" --url https://your-app.onrender.com
"""

import argparse
import json
import sys
import time

import httpx


async def ask(message: str, url: str, json_mode: bool) -> None:
    start = time.monotonic()
    first_words_after = None
    chunks = []
    provider = None
    model = None
    fallback = False

    try:
        async with (
            httpx.AsyncClient(timeout=120.0) as client,
            client.stream(
                "POST",
                f"{url}/v1/chat",
                json={"message": message},
            ) as resp,
        ):
            if resp.status_code >= 400:
                body = await resp.aread()
                print(f"HTTP {resp.status_code}: {body.decode()[:500]}", file=sys.stderr)
                return

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    break
                try:
                    data = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                if data.get("type") == "start":
                    first_words_after = time.monotonic() - start
                    chunks.append(data.get("text", ""))
                    provider = data.get("provider")
                    model = data.get("model")
                    fallback = data.get("fallback", False)
                    if json_mode:
                        print(
                            json.dumps(
                                {
                                    "type": "start",
                                    "text": data.get("text", ""),
                                    "provider": provider,
                                    "model": model,
                                    "fallback": fallback,
                                }
                            )
                        )
                    else:
                        print(data.get("text", ""), end="", flush=True)
                elif data.get("type") == "token":
                    chunks.append(data.get("text", ""))
                    if json_mode:
                        print(json.dumps({"type": "token", "text": data.get("text", "")}))
                    else:
                        print(data.get("text", ""), end="", flush=True)
                elif data.get("type") == "end":
                    if json_mode:
                        print(json.dumps({"type": "end"}))
                    break
                elif data.get("type") == "error":
                    if json_mode:
                        print(json.dumps({"type": "error", "detail": data.get("detail")}))
                    else:
                        print(f"\n[error] {data.get('detail')}", file=sys.stderr)
                    return

    except httpx.ConnectError:
        print(
            "ConnectError: is the API running? Start `uv run poe dev` in Terminal 1.",
            file=sys.stderr,
        )
        return

    total = time.monotonic() - start
    answer = "".join(chunks)

    if json_mode:
        print(
            json.dumps(
                {
                    "first_words_after_s": round(first_words_after or 0, 3),
                    "total_s": round(total, 3),
                    "provider": provider,
                    "model": model,
                    "fallback": fallback,
                    "answer": answer,
                }
            )
        )
    else:
        print()
        fb = " (fallback=YES)" if fallback else ""
        parts = [
            f"--- {provider} / {model}",
            f"first words after {first_words_after:.2f} s",
            f"total {total:.2f} s",
            fb,
        ]
        print(" ".join(p for p in parts if p))


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask FounderDesk a question via /v1/chat")
    parser.add_argument("message", help="Your question")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the running API (default: http://localhost:8000)",
    )
    args = parser.parse_args()
    import asyncio

    asyncio.run(ask(args.message, args.url, args.json))


if __name__ == "__main__":
    main()
