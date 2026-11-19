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
