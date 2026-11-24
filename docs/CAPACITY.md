# Capacity plan: FounderDesk

Full corpus target: 200 documents across central and state startup schemes

<!-- generated:start -->
Measured corpus: 10 files, 65 pages, 274,852 chars, ~68,713 tokens.

Full corpus target: 200 files ≈ 1300 pages ≈ 5,497,040 chars ≈ 1,374,260 tokens.

- Chunks (at 500 tokens/chunk): 2,748
- Embedding cost: 1,374,260 tokens ÷ 1M × $0.2 = $0.27 ≈ Rs 26 (at ₹95.0/$)
- Vector storage: 2,748 chunks × 1024 dims × 4 bytes ≈ 10.7 MB
<!-- generated:end -->

## What I conclude

1. Is embedding cost a problem for this product? No — Rs 26 to embed 200 documents (per 1M tokens at $0.20) is well within the Rs 0.50/question budget, so I can embed the full corpus.
2. Do the vectors and text fit in my free Postgres? Yes — vectors are ~10.7 MB and text ~5.5 MB, far under the free Neon storage limit.
3. Which number above am I least sure about, and how will I measure it better? The chars ÷ 4 token estimate for HTML; I'll measure with a real tokenizer (tiktoken) on a sample of pages.
4. What changes if the corpus grows 10 times? 2,000 documents → ~107 MB vectors and ~Rs 260 embedding cost, still within budget; selective embedding may not be needed at this scale.
