# FounderDesk

Guides student founders through startup recognition, tax benefits and seed-funding schemes (Startup India and StartupTN), with eligibility checks.

**Status:** Day 1 foundation (FastAPI skeleton, quality gates). Live URL from Day 5.

## Who it's for

Final-year student founder in Chennai with an ed-tech MVP who wants DPIIT recognition and seed funding.

## The problem

Schemes have overlapping conditions (entity age, turnover, recognition, earlier funding) and changing cohorts and deadlines.

## Data sources

Startup India portal documents (DPIIT recognition, Seed Fund Scheme guidelines, Fund of Funds, Credit Guarantee), Startup India kit, StartupTN scheme documents.

- https://www.startupindia.gov.in/
- https://startuptn.in/
Terms: Public scheme documents. Cite scheme name and version date.

## Hardest problem (my interview story)

Eligibility across schemes: rules overlap and conflict (entity age, turnover, recognition, prior funding). They must be applied in code with the failing condition shown, plus deadlines kept current.

## Signature feature

Scheme matcher: answer 8 questions about your startup and see eligible schemes, near-misses and the reason for each.

## Target metric

Eligibility correct for 90%+ of 30 startup profiles.

## Run it locally

```bash
uv sync
cp .env.example .env   # Windows: copy .env.example .env
uv run uvicorn founderdesk.api.main:create_app --factory --reload
```

Then open http://localhost:8000/docs

## Checks

```bash
uv run pytest
uv run ruff check .
```
