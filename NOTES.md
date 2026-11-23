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

- **Merge clicked at:** __:__ → **"Smoke test passed" at:** __:__ → **Lead time:** ___ min

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
- Collected today: 10 files, ~2.9 MB (from data/manifest.jsonl)
- Doors used: URL list

### Licence check

| Source | Licence or terms, in my words | May I show full text in answers? |
|---|---|---|
| startup-india | Government of India portal; public scheme information, reproduce with attribution | Yes |
| startuptn | Government of Tamil Nadu portal; public scheme information, reproduce with attribution | Yes |
| sidbi | Government of India institution; public information, reproduce with attribution | Yes |
| wikipedia | CC BY-SA 4.0; attribution required, share-alike | Yes |

### robots.txt

- Site: wikipedia.org. Its robots.txt says (2 lines): allows bots, crawl delay respected
- Site: startupindia.gov.in, startuptn.in, sidbi.in. robots.txt fetched without 5xx; nothing blocked
- Was anything blocked for my bot? No. All 10 sources allowed `examate-student-bot`.

### Kill and resume

- Run 1: I pressed Ctrl+C after 7 files
- Run 2: downloaded=3 skipped=7
- Run 3: downloaded=0 skipped=10

### Capacity (from docs/CAPACITY.md)

- Tokens per page, measured: ~7,000 (70,516 tokens ÷ 10 pages)
- Full corpus: ~1.4 M tokens, 2,820 chunks, embedding about Rs 53,580, vectors 11 MB
- The number that surprised me most, and why (2 lines): Embedding 200 documents costs ~Rs 53,580, which blows the Rs 0.50-per-question budget. That means I can't embed everything — I'll need selective embedding of the most relevant scheme documents only.

### One thing that went wrong today, and how I fixed it

- `protego.parse()` is a classmethod returning a new instance; calling `Protego(); robot.parse(text)` left the parser empty. Fixed to `robot = Protego.parse(text)`.
