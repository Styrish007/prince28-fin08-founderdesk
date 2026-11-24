# Capacity plan: FounderDesk

Full corpus target: 200 documents across central and state startup schemes

<!-- generated:start -->
Measured corpus: 10 files, 65 pages, 120,231 chars, ~30,057 tokens.

Full corpus target: 200 files ≈ 1300 pages ≈ 2,404,620 chars ≈ 601,155 tokens.

- Chunks (at 500 tokens/chunk): 1,202
- Embedding cost: 601,155 tokens ÷ 1M × $0.2 = $0.12 ≈ Rs 11 (at ₹95.0/$)
- Vector storage: 1,202 chunks × 1024 dims × 4 bytes ≈ 4.7 MB
<!-- generated:end -->

## What I conclude

1. Is embedding cost a problem for this product? No — Rs 11 to embed 200 documents (per 1M tokens at $0.20) is well within the Rs 0.50/question budget, so I can embed the full corpus.
2. Do the vectors and text fit in my free Postgres? Yes — vectors are ~4.7 MB and text ~1.5 MB, far under the free Neon storage limit.
3. Which number above am I least sure about, and how will I measure it better? The chars ÷ 4 token estimate for HTML; I'll measure with a real tokenizer (tiktoken) on a sample of pages.
4. What changes if the corpus grows 10 times? 2,000 documents → ~47 MB vectors and ~Rs 110 embedding cost, still within budget; selective embedding may not be needed at this scale.
