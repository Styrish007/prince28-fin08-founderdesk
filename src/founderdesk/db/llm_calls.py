"""Record every LLM call to Postgres, and roll them up per day."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from founderdesk.db.models import LLMCall


class UsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(self, payload: dict[str, Any]) -> None:
        row = LLMCall(
            provider=payload["provider"],
            model=payload["model"],
            status=payload["status"],
            error=payload.get("error"),
            tokens_in=payload.get("tokens_in", 0),
            tokens_out=payload.get("tokens_out", 0),
            latency_ms=payload.get("latency_ms", 0),
            cost_inr=payload.get("cost_inr", 0),
            fallback_used=payload.get("fallback_used", False),
            request_id=payload.get("request_id"),
        )
        self.session.add(row)
        await self.session.flush()
        await self.session.commit()

    async def daily_totals(self, day: date | None = None) -> dict[str, Any]:
        """Calls, errors, fallbacks, tokens and rupees for one day (default: today)."""
        if day is None:
            day = date.today()
        start = datetime(day.year, day.month, day.day)
        stmt = select(
            func.count(LLMCall.id).label("calls"),
            func.count(LLMCall.id).filter(LLMCall.status == "error").label("errors"),
            func.count(LLMCall.id).filter(LLMCall.fallback_used.is_(True)).label("fallbacks"),
            func.coalesce(func.sum(LLMCall.tokens_in), 0).label("tokens_in"),
            func.coalesce(func.sum(LLMCall.tokens_out), 0).label("tokens_out"),
            func.coalesce(func.sum(LLMCall.cost_inr), 0).label("cost_inr"),
        ).where(LLMCall.created_at >= start)
        row = await self.session.execute(stmt)
        calls, errors, fallbacks, tokens_in, tokens_out, cost_inr = row.first()
        return {
            "calls": calls or 0,
            "errors": errors or 0,
            "fallbacks": fallbacks or 0,
            "tokens_in": int(tokens_in or 0),
            "tokens_out": int(tokens_out or 0),
            "cost_inr": float(cost_inr or 0),
        }
