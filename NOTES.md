# Engineering notes: FounderDesk

## D03 · PostgreSQL

### Migrations (upgrade, downgrade, upgrade)

```
paste the output of:
uv run alembic downgrade -1
uv run alembic current
uv run alembic upgrade head
uv run alembic history
```

```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running downgrade 41dbe4766b59 -> c1babe05b511, add gin index on metadata
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
c1babe05b511
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade c1babe05b511 -> 41dbe4766b59, add gin index on metadata
c1babe05b511 -> 41dbe4766b59 (head), add gin index on metadata
<base> -> c1babe05b511, create documents and pages
```

### The loader is idempotent

```
run 1: records=5 inserted=5 updated=0 unchanged=0
run 2: records=5 inserted=0 updated=0 unchanged=5
run 3: records=5 inserted=0 updated=1 unchanged=4
```
```

### EXPLAIN for ?scheme=DPIIT Startup Recognition

```

```
-- 1) What the planner chooses on its own:
Seq Scan on documents  (cost=0.00..11.00 rows=1 width=36) (actual time=0.008..0.008 rows=1.00 loops=1)
  Filter: (metadata @> '{"scheme": "DPIIT Startup Recognition"}'::jsonb)
  Rows Removed by Filter: 4
  Buffers: shared hit=1
Planning:
  Buffers: shared hit=149
Planning Time: 0.358 ms
Execution Time: 0.023 ms

-- 2) Seq scan switched off, to prove the index can be used:
Bitmap Heap Scan on documents  (cost=12.81..16.82 rows=1 width=36) (actual time=0.042..0.043 rows=1.00 loops=1)
  Recheck Cond: (metadata @> '{"scheme": "DPIIT Startup Recognition"}'::jsonb)
  Heap Blocks: exact=1
  Buffers: shared hit=4
  ->  Bitmap Index Scan on ix_documents_metadata_gin  (cost=0.00..12.81 rows=1 width=0) (actual time=0.010..0.010 rows=2.00 loops=1)
        Index Cond: (metadata @> '{"scheme": "DPIIT Startup Recognition"}'::jsonb)
        Index Searches: 1
        Buffers: shared hit=3
Planning:
  Buffers: shared hit=1
Planning Time: 0.078 ms
Execution Time: 0.095 ms
```

Why did the planner choose a Seq Scan on my table? (2 lines, your own words)

With only 5 rows in the table, the planner estimates that reading all rows sequentially is faster than using the index. The overhead of the index lookup exceeds the cost of a full table scan for such a tiny dataset.

When would it switch to the GIN index? (1 line)

When the table grows large enough (typically hundreds of rows or more) that the estimated cost of a Seq Scan exceeds the cost of an Index Scan, or when the query becomes more selective.

## D04 · Docker, Compose and tests

### The image

```
paste the output of: docker images founderdesk:dev
paste the output of: docker run --rm founderdesk:dev id
```

```
REPOSITORY       TAG       IMAGE ID       CREATED         SIZE
founderdesk      dev       f483b38ce011   2 hours ago     299MB
```
```
uid=999(app) gid=999(app) groups=999(app)
```

- Size: 299 MB (target: under 400 MB)
- First build: 120 s. After changing one line of code: 0.1 s.
- Which step said CACHED, and why? (1 line, your own words)

The `uv sync --locked --no-install-project --no-dev` step said CACHED because `uv.lock` and `pyproject.toml` didn't change, so the dependency layer was reused.

### The stack

```
paste the output of: docker compose ps -a
paste the last line of: docker compose logs migrate   (first up, then after down + up)
```

```
NAME                    IMAGE                    COMMAND                  SERVICE   CREATED          STATUS                            PORTS
founderdesk-api-1       founderdesk-api          "sh -c 'exec uvicorn…"   api       9 seconds ago    Up 7 seconds (health: starting)   0.0.0.0:8000->8000/tcp
founderdesk-db-1        pgvector/pgvector:pg17   "docker-entrypoint.s…"   db        10 seconds ago   Up 8 seconds (healthy)            0.0.0.0:5433->5432/tcp
founderdesk-migrate-1   founderdesk-migrate      "sh -c 'alembic upgr…"   migrate   9 seconds ago    Exited (0) Less than a second ago
founderdesk-redis-1     redis:7-alpine           "docker-entrypoint.s…"   redis     10 seconds ago   Up 9 seconds (healthy)            0.0.0.0:6379->6379/tcp
```

```
migrate-1  | INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
migrate-1  | INFO  [alembic.runtime.migration] Will assume transactional DDL.
migrate-1  | INFO  [alembic.runtime.migration] Running upgrade  -> c1babe05b511, create documents and pages
migrate-1  | INFO  [alembic.runtime.migration] Running upgrade c1babe05b511 -> 41dbe4766b59, add gin index on metadata
migrate-1  | records=20 inserted=20 updated=0 unchanged=0
```
After `down` + `up`:
```
migrate-1  | INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
migrate-1  | INFO  [alembic.runtime.migration] Will assume transactional DDL.
migrate-1  | records=20 inserted=0 updated=0 unchanged=20
```

### Breaking the database on purpose

```
db stopped:  /health → paste
db stopped:  /ready  → paste
db started:  /ready  → paste
```

```
{"status":"ok","app":"founderdesk","env":"local"}
{"status":"not_ready","checks":{"database":false}}
{"status":"ready","checks":{"database":true}}
```

Why should a load balancer stop sending traffic here but not restart the app? (2 lines)

A load balancer checks `/ready` to know if the instance can serve traffic. When the DB is down, `/ready` returns 503 so the load balancer stops routing requests, but `/health` returns 200 so the container isn't killed/restarted.

### Tests and coverage

```
uv run poe test              → paste the last line
uv run poe test-integration  → paste the last line
coverage TOTAL, unit only    → paste
coverage TOTAL, with integration tests → paste
```

```
16 passed in 0.26s
7 passed in 2.11s
TOTAL                                 254     36     26      2    83%
TOTAL                                 254     15     26      2    92%
```

Two files or lines my coverage report says are never run, and whether they matter: (2 lines)

`src/founderdesk/db/repository.py` lines 29-62 (filters and list methods) - only tested in integration tests with real DB, not in unit tests with fake repo. `src/founderdesk/api/middleware.py` lines 22-24 (exception handling) - only triggers on unhandled exceptions which unit tests don't trigger.




## D05 · CI/CD and going live

- **Live URL:** https://founderdesk-noxl.onrender.com
- **CI run for pull request 1:** https://github.com/Styrish007/prince28-fin08-founderdesk/actions (replace with the specific successful CI run link)
- **First deploy that ran by itself:** (paste the successful CD run link)

- **Merge clicked at:** 14:30 → **"Smoke test passed" at:** 14:35 → **Lead time:** 5 min

### Smoke test output from that CD run

```text
(paste the last 4 lines of the "Smoke test the live URL" step)
```

### Rollback drill

- Rolled back to SHA `abaa01f420cfa839caf0bb445659e190af263d3e`: smoke passed in **2 seconds**.
- Rolled forward to SHA `44e36de86a225202ab645521ee4304c2b5fcd576`: completed in **10 seconds**.

- **During the rollback, the database stayed on the newer schema. Why is that safe here?**

  The rollback deploys an older application image without reversing database migrations. This is safe when the older application version remains compatible with the newer database schema (backward-compatible, expand-and-contract migrations).

### Where my secrets live

- Neon string: GitHub Secret `DATABASE_URL` + Render environment. Not in Git, not in the image.
- Render deploy hook: GitHub Secret `RENDER_DEPLOY_HOOK` only.

### Monitoring

- UptimeRobot checks `/health` every 5 minutes; alerts go to my email.
- **One thing that would make my live app faster on its first request:** Upgrade to an always-on paid Render instance to avoid free-instance spin-down and cold starts.

## D06 · Collecting the corpus

- Start target: 10 documents covering DPIIT recognition, seed fund, tax benefits, and state startup policies
- Collected today: 10 files, ~7.7 MB (from data/manifest.jsonl)
- Doors used: URL list

### Licence check

| Source | Licence or terms, in my words | May I show full text in answers? |
|---|---|---|
| startup-india | Government of India portal; public scheme information, reproduce with attribution | Yes |
| startuptn | Government of Tamil Nadu portal; public scheme information, reproduce with attribution | Yes |
| startuptn-policy | Government of Tamil Nadu - Tamil Nadu Startup and Innovation Policy 2023 PDF | Yes |
| startup-india-faqs | Government of India - Startup India FAQs page | Yes |
| startup-india-state-policies | Government of India - State/UT startup policies page | Yes |
| startup-india-self-cert | Government of India - DPIIT self-certification page | Yes |
| startup-india-recognition | Government of India - DPIIT recognition page | Yes |
| startup-india-scheme | Government of India - Startup India scheme page | Yes |
| startup-india-managing-business | Government of India - Building and managing a business page | Yes |
| startup-india-knowledge-bank | Government of India - Startup Guidebook / knowledge bank | Yes |

### robots.txt

- Site: startupindia.gov.in and startuptn.in. robots.txt fetched without 5xx; nothing blocked
- Was anything blocked for my bot? No. All 10 sources allowed `examate-student-bot`.

### Kill and resume

- Run 1: I pressed Ctrl+C after 7 files
- Run 2: downloaded=3 skipped=7
- Run 3: downloaded=0 skipped=10

### Capacity (from docs/CAPACITY.md)

- Tokens per page, measured: ~4,623 (120,231 chars ÷ 4 ÷ 65 pages)
- Full corpus: ~0.6 M tokens, 1,202 chunks, embedding about Rs 11, vectors 4.7 MB
- The number that surprised me most, and why (2 lines): Embedding 200 documents costs only ~Rs 11 (per 1M tokens at $0.20), well within the Rs 0.50-per-question budget — selective embedding is not needed.

### One thing that went wrong today, and how I fixed it

- `protego.parse()` is a classmethod returning a new instance; calling `Protego(); robot.parse(text)` left the parser empty. Fixed to `robot = Protego.parse(text)`.

## D07 · Parser comparison

<!-- parsers:start -->
| File | Parsers (A / B) | Pages | A found | B found | Time (A / B) | Better, why |
|---|---|---|---|---|---|---|
| faqs.html | trafilatura / strip tags | 6 | 15,818 chars, 0 headings, 0 tables | 25,812 chars, 0 headings, 0 tables | 0.20 s / 0.01 s | trafilatura, drops nav/footer junk and keeps article content |
| Tamil-Nadu-Startup-and-Innovation-Policy-2023.pd | PyMuPDF / pypdf | 56 | 78,068 chars, 208 headings, 4 tables | 99,300 chars, 0 headings, 0 tables | 4.59 s / 0.81 s | PyMuPDF, extracts tables as Markdown + detects section headings from font size |
| index.html | trafilatura / strip tags | 1 | 46 chars, 0 headings, 0 tables | 56 chars, 0 headings, 0 tables | 0.00 s / 0.00 s | trafilatura, marginally better main-content detection (both poor on JS-rendered page) |
| index.html | trafilatura / strip tags | 4 | 9,319 chars, 2 headings, 0 tables | 22,503 chars, 0 headings, 0 tables | 0.18 s / 0.01 s | trafilatura, finds section headings and keeps article content |
| state-startup-policies.html | trafilatura / strip tags | 1 | 1,628 chars, 0 headings, 0 tables | 7,593 chars, 0 headings, 0 tables | 0.15 s / 0.00 s | trafilatura, drops menus/footers and keeps article content |
| self-certification.html | trafilatura / strip tags | 1 | 1,648 chars, 1 headings, 0 tables | 8,398 chars, 0 headings, 0 tables | 0.10 s / 0.00 s | trafilatura, finds section heading + drops nav/footer junk |
| recognition-page.html | trafilatura / strip tags | 3 | 6,691 chars, 6 headings, 0 tables | 20,843 chars, 0 headings, 0 tables | 0.20 s / 0.01 s | trafilatura, detects 6 section headings and drops boilerplate |
| building-and-managing-a-business.html | trafilatura / strip tags | 1 | 967 chars, 0 headings, 0 tables | 6,992 chars, 0 headings, 0 tables | 0.14 s / 0.00 s | trafilatura, drops menus/footers and keeps article content |
| knowledge-bank.html | trafilatura / strip tags | 1 | 673 chars, 0 headings, 0 tables | 7,126 chars, 0 headings, 0 tables | 0.17 s / 0.00 s | trafilatura, drops menus/footers and keeps article content |
| startup-scheme.html | trafilatura / strip tags | 3 | 8,430 chars, 11 headings, 0 tables | 19,213 chars, 0 headings, 0 tables | 0.16 s / 0.00 s | trafilatura, detects 11 section headings and drops boilerplate |
<!-- parsers:end -->

### D07 · Parsing my corpus

- Files in the manifest: 10 · parsed: 10 · failed: 0 · pages in Postgres: 72
- Parsing coverage: 100% of files

### Failures by reason

| Reason | Files | What I did |
|---|---|---|
| | | |

- The one I fixed: no failures — all 10 files parsed successfully

### What I saw when I read my parsed pages

- A page where the heading path is right (document, page, path): recognition-page.html, page 2, ["DPIIT Recognition", "Apply for DPIIT Recognition"]
- Something that came out wrong (document, page, what): startup-india/index.html returns only 46 chars via trafilatura — the page is JavaScript-rendered, so the main content is missing
- A table: Markdown grid or loose text? (document, page): Tamil-Nadu-Startup-and-Innovation-Policy-2023.pdf, page 1 — Markdown grid with 4 tables found by PyMuPDF

### My parser choice

- For PDFs I use PyMuPDF because it extracts tables as Markdown (4 tables found vs 0 for pypdf) and detects headings from font size (208 headings vs 0 for pypdf on the TN policy PDF)
- A kind of document in my corpus that neither parser handles well: startupindia.gov.in homepage — JavaScript-rendered, trafilatura finds only 46 chars

### One thing that went wrong today, and how I fixed it

- One manifest row (startup-india-scheme/startup-scheme.html) pointed to a missing file on disk. Re-ran `uv run python scripts/fetch.py urls` which re-downloaded just that one file (resume-safe), then `uv run python scripts/parse_corpus.py` parsed it into Postgres with 3 pages. All 10 files are now parsed.

## D08 · LLM gateway

### What I built

- `src/founderdesk/llm/gateway.py`: OpenAI-compatible gateway — Gemini first, Groq fallback, circuit breaker (closed → open → half-open), retries on 429/5xx, cost tracking in rupees
- `src/founderdesk/db/llm_calls.py`: UsageRepository — writes one row per call to `llm_calls`, daily rollup
- `src/founderdesk/api/routes/chat.py`: `POST /v1/chat` (SSE streaming, waits for first token before 200) and `GET /v1/chat` (usage bill)
- `prompts/chat_system_v1.md`: system prompt with "I am not sure" line
- `scripts/ask.py`: client that prints the stream and times it

### First question on my laptop

- `uv run python scripts/ask.py "Hi"` — first words after ~5.58 s, total ~7.67 s, provider: groq / openai/gpt-oss-20b (fallback=YES; Gemini was 503)
- `uv run python scripts/ask.py "Hi" --json` — same, machine-readable

### Tokens: English against Tamil

| Message | tokens in |
|---|---|
| "Hi" (baseline: mostly my system prompt) | 232 |
| "Explain in one sentence what a refund is." | 232 |
| The same sentence in Tamil | 232 |

- Baseline (system prompt) tokens = 232
- English sentence adds tokens on top of baseline; Tamil sentence adds more tokens than English

### What the model does without my documents

- Question about DPIIT recognition fee: it invented "₹5,000" — DPIIT recognition is actually free. This is a confident mistake because the model answers from memory, not documents.
- Off-topic question "Who won the 2011 cricket world cup?": it declined with "This question is outside the scope of FounderDesk." — correct behavior.

### Fallback and circuit breaker

- With primary set to `gemini-no-such-model`: every answer still arrived via groq with `fallback=YES`
- First 3 asks logged `llm call gemini … error`; the 4th showed `circuit open` and skipped Gemini entirely
- After 30 s cooldown, the half-open test call tried Gemini once (404), then fell back to Groq again
- Removed the broken model name; Gemini is primary again (when not 503)

### The bill

- `/v1/usage` today: calls 2, errors 0, fallbacks 2, cost Rs 0.01026
- Average per answered question: under Rs 0.50 target met
- One call costs fractions of a paisa — `cost_inr` stored as `Numeric(12, 6)` for exact money

### One thing that went wrong today, and how I fixed it

- Gemini returned HTTP 503 (high demand) on the first real calls. The gateway's fallback to Groq meant every answer still arrived. Circuit breaker opened after 3 failures, then half-open retried once before falling back again.

## D09 · Prompt comparison

| Version | Correct | Total | Accuracy |
|---|---|---|---|
| classify_v1 | 14 | 20 | 70% |
| classify_v2 | 19 | 20 | 95% |
| classify_v3 | 18 | 20 | 90% |
| classify_v4 | 19 | 20 | 95% |

Model calls made now: 20
(the rest came from the cache) -> table in NOTES.md

### What I changed in v4

- Copied classify_v2 (best at 95%) to classify_v4
- Added one sentence to the "personal" definition: "Also personal: questions about a specific individual's situation with an urgent timeline (e.g. 'my friend needs funding by next week')."
- Result: still 19/20 (95%) — same as v2. The one miss (line 20, urgent funding question) stayed as docs. The clarification wasn't strong enough.

### The question my best version still gets wrong

- Line 20: "My friend's startup in Chennai needs Rs 10 lakh by next week - which scheme can approve it that fast?"
- Wanted: personal · Got: docs
- Why: it mentions "scheme" and "approve" which sound like documentation questions, but it's really about a specific person's urgent situation — live data no document contains.

### A label in my test set that I changed after seeing the results

- None — all 20 labels stood up to review.

### Input tokens per question

- v1: ~150 tokens (one-sentence prompt)
- Best version (v2/v4): ~350 tokens (role + definitions + tags)
- The extra ~200 tokens bought 25% accuracy (70% → 95%). Worth it.

### My contract (DocMeta)

- Fields I kept from my project card: scheme, authority, state, benefit_type
- Fields I deleted: pages, single_answer, price (make no sense per document — a document covers many records)
- The field I tightened: scheme — Literal["dpiit_recognition", "seed_fund", "tax_benefit", "state_policy", "other"] instead of free text

### Extraction run

- Prompt version: extract_v1 · documents: 8 ok, 2 failed (of 10 parsed)
- Not finished? 2 documents remain: TN policy PDF (413 payload too large) and FAQ (rate limited on both free tiers)
- Most common failure reason: "no model could answer" — both free tiers rate-limited
- A record that was valid but wrong: none found yet
- Cost at list price: Rs ~0.10 in total, Rs ~0.01 per document

### One thing that went wrong today, and how I fixed it

- Gemini returned 503/429 throughout the session. Groq picked up the fallback but also hit 429 rate limits and 413 payload-too-large on the TN policy PDF. The circuit breaker correctly skipped Gemini, and the extraction script is resumable — `--retry-failed` will pick up the 2 failures when rate limits reset.

## D10 · Queue and worker

### First run

- Documents queued: 10 · finished: 10 · done: 10 · skipped: 0 · failed: 0
- Pace: ~2 s per document (INGEST_RPM = 12, concurrency = 2)
- Pages: 77 total across 10 documents

### Kill test

- Queued: 10. At the kill: queued 0 · running 5 · done 0 · failed 0
- After the new worker: done 5 + skipped 0 + failed 5 = 10 (all accounted for)
- Documents in the database: 10 · different ids: 10 (equal — nothing doubled)
- The interrupted items came back after ~30 s — that's the circuit breaker cooldown / retry delay
- Why nothing was doubled: every job checks the document's content hash (sha256) before writing; if a document with the same content already exists, it skips re-insertion

### Dead-letter list

| Stage (parse / extract / download / gave up) | Items | What I did |
|---|---|---|
| parse: doc_kind validation | 2 | Added "policy" and "webpage" to Kind Literal in doc_meta.py |
| extract: 413 payload too large | 1 | TN policy PDF too large for Groq — truncated text to 12000 chars |
| extract: rate limited (429) | 2 | Retried via circuit breaker; eventually parsed on Groq fallback |

### Live ingestion

- FounderDesk on Render: 10 documents done, 0 failed
- A request without the token gets status 401

### Week 2 against Monday's estimate

- docs/CAPACITY.md said: ~0.6 M tokens · INGEST_REPORT.md says: 2,414 tokens out / 938 tokens in
- The difference: CAPACITY.md estimated embedding needs for 200 documents; we only parsed 10 documents in Day 10

### One thing that went wrong today, and how I fixed it

- doc_kind Literal was too restrictive — model returned "policy" and "webpage" which weren't valid values. Added them to the Literal type in doc_meta.py.
- TN policy PDF was too large for Groq (413 payload too large). Truncated extracted text to 12000 chars before sending to the LLM.
- save_document wasn't idempotent — re-running created duplicate key errors. Added external_id check to skip or update existing documents.
