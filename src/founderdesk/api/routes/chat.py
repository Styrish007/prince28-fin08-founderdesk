"""POST /v1/chat (streaming answers) and GET /v1/usage (today's bill)."""

from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import async_sessionmaker

from founderdesk.api.deps import GatewayDep, SettingsDep, UsageDep
from founderdesk.config import Settings
from founderdesk.db.llm_calls import UsageRepository
from founderdesk.llm.gateway import LLMGateway, LLMUnavailable

router = APIRouter(prefix="/chat", tags=["chat"])

MAX_MESSAGE_LENGTH = 4000


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)


def sse(data: dict) -> str:
    """One SSE event: `data: {...}` followed by a blank line."""
    import json

    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("")
async def chat(
    request: Request,
    body: ChatRequest,
    gateway: GatewayDep,
) -> StreamingResponse:
    """Stream an answer word by word. 200 is sent only after the first piece arrives."""
    system_prompt = request.app.state.system_prompt
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": body.message},
    ]
    request_id = request.headers.get("X-Request-ID")

    async def event_stream():
        try:
            stream = gateway.stream(messages, request_id=request_id)
            # Wait for the first piece before sending 200.
            first = await anext(stream)
            yield sse(
                {
                    "type": "start",
                    "text": first,
                    "provider": gateway.last_provider,
                    "model": gateway.last_model,
                    "fallback": gateway.last_fallback_used,
                }
            )
            async for chunk in stream:
                yield sse({"type": "token", "text": chunk})
            yield sse({"type": "end"})
        except LLMUnavailable as exc:
            yield sse({"type": "error", "detail": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("")
async def usage(
    settings: SettingsDep,
    usage_repo: UsageDep,
) -> dict:
    """Today's bill: calls, tokens, errors, fallbacks, rupees."""
    totals = await usage_repo.daily_totals(date.today())
    return totals


def anext(ait):
    """Async next: Python 3.12 has a built-in, but keep this alias for clarity."""
    return __import__("builtins").anext(ait)


def build_gateway(settings: Settings) -> LLMGateway:
    """Build the LLM gateway from settings (used by main.py at start-up)."""
    from founderdesk.llm.gateway import LLMGateway

    return LLMGateway(settings)


def make_recorder(sessionmaker: async_sessionmaker):
    """Build an async record() coroutine function that writes to Postgres.

    Opens its own session per call so it works from the gateway's background task.
    """

    async def record(payload: dict) -> None:
        async with sessionmaker() as session:
            repo = UsageRepository(session)
            await repo.record(payload)

    return record


__all__ = ["router", "build_gateway", "make_recorder"]
