"""GET /v1/usage (today's bill)."""

from datetime import date

from fastapi import APIRouter

from founderdesk.api.deps import UsageDep

router = APIRouter(tags=["usage"])


@router.get("/usage")
async def usage(
    usage_repo: UsageDep,
) -> dict:
    """Today's bill: calls, tokens, errors, fallbacks, rupees."""
    totals = await usage_repo.daily_totals(date.today())
    return totals
