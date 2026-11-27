# LLM Ingestion Report

Generated: 2026-11-27 09:30:28 UTC

## Corpus

- Documents: 10
- Pages: 77
- Distinct documents: 10

## Bill

- Calls: 4
- Errors: 0
- Fallbacks: 4
- Tokens in: 938
- Tokens out: 2,414
- Cost at list price: Rs 0.0755
- Cost per document: Rs 0.0075

## Dead-letter list

- Items: 5

## What I learnt

- Parsing 10 documents through the queue took approximately 8 pages per document.
- The LLM gateway falls back from Gemini to Groq when Gemini is rate-limited (HTTP 503/429).
- The circuit breaker opens after 3 consecutive failures and half-opens after 30 seconds.
- The worker persists job state in Postgres so a crash doesn't lose work: killed workers are
  recovered on restart via `claim_all_queued()`.
- Cost per document is under the Rs 0.50 target.
