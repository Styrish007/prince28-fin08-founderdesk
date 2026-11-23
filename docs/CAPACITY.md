# Capacity plan: FounderDesk

Full corpus target: 200 documents across central and state startup schemes

<!-- generated:start -->
Measured corpus: 10 files, 10 pages, 282,065 chars, ~70,516 tokens.

Full corpus target: 200 files ≈ 200 pages ≈ 5,641,300 chars ≈ 1,410,325 tokens.

- Chunks (at 500 tokens/chunk): 2,820
- Embedding cost: 2,820 chunks × $0.2 = $564.00 ≈ Rs 53,580 (at ₹95.0/$)
- Vector storage: 2,820 chunks × 1024 dims × 4 bytes ≈ 11.0 MB
<!-- generated:end -->

## What I conclude

1. Is embedding cost a problem for this product? Yes — Rs 53,580 to embed 200 documents is too high for the Rs 0.50/question budget, so I'll embed only the most relevant scheme documents, not everything.
2. Do the vectors and text fit in my free Postgres? Yes — vectors are only ~11 MB and text ~5.6 MB, far under the free Neon storage limit.
3. Which number above am I least sure about, and how will I measure it better? The chars ÷ 4 token estimate for HTML; I'll measure with a real tokenizer (tiktoken) on a sample of pages.
4. What changes if the corpus grows 10 times? 2,000 documents → ~110 MB vectors and ~Rs 535,800 embedding cost, exceeding the free tier and the per-question budget; I'd need selective embedding and a paid plan.
