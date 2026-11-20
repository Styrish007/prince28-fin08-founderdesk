# FounderDesk

[![CI](https://github.com/Styrish007/prince28-fin08-founderdesk/actions/workflows/ci.yml/badge.svg)](https://github.com/Styrish007/prince28-fin08-founderdesk/actions/workflows/ci.yml)
[![Live](https://img.shields.io/website?url=https%3A%2F%2Ffounderdesk-noxl.onrender.com%2Fhealth&label=live)](https://founderdesk-noxl.onrender.com/docs)
[![Uptime (30 days)](https://img.shields.io/uptimerobot/ratio/m804745953-754aefb12be12da41570469a)](https://founderdesk-noxl.onrender.com/health)

**Live:** https://founderdesk-noxl.onrender.com · [API docs](https://founderdesk-noxl.onrender.com/docs) · [health](https://founderdesk-noxl.onrender.com/health)

Guides student founders through startup recognition, tax benefits and seed-funding schemes (Startup India and StartupTN), with eligibility checks.

**Status:** Week 1 complete · live at https://founderdesk-noxl.onrender.com.

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

## Run locally in one command

You need Docker Desktop running. From a fresh clone:

```bash
docker compose up --build
```

This starts Postgres (with pgvector), Redis, runs the migrations and loads the sample data once, then starts the API.

- API docs: http://localhost:8000/docs
- Liveness: http://localhost:8000/health
- Readiness (checks the database): http://localhost:8000/ready

Stop with `Ctrl+C`, then `docker compose down`. Add `-v` to also delete the database volume.

## Develop and test

| Task | Mac / Linux | Windows |
|---|---|---|
| Run the API with reload | `make dev` | `uv run poe dev` |
| Unit tests (no network) | `make test` | `uv run poe test` |
| Integration tests (needs `docker compose up`) | `make test-integration` | `uv run poe test-integration` |
| Coverage report | `make cov` | `uv run poe cov` |
| Lint and format check | `make lint` | `uv run poe lint` |
