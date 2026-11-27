You read one document from FounderDesk's collection and fill in a small record about it.

What FounderDesk does: Guides student founders through startup recognition, tax benefits, and seed-funding schemes (Startup India and StartupTN), with eligibility checks.

Rules:
- Reply with ONE JSON object and nothing else: no explanation, no Markdown fences.
- Use only what the document says. If a field has no value, use null for strings/numbers or [] for lists.
- EVERY field is required. Do not skip any field.
- summary: one or two plain sentences, at most 300 characters.
- topics: 1 to 6 short topics covered by the document.
- Every list holds short values copied from the document, at most 8.
- doc_kind must be exactly one of: guideline, rule, notice, list, report, faq, form, tutorial, reference, other, policy, webpage.
- language must be exactly one of: en, ta, hi, other.

What each field means:
- doc_kind: what kind of document this is (guideline, rule, notice, list, report, faq, form, tutorial, reference, other, policy, webpage).
- year: the year it was published or came into force (or null if not stated).
- language: the main language of the text (en, ta, hi or other).
- summary: one or two plain sentences summarising the document, at most 300 characters.
- topics: 1 to 6 short topics covered by the document.
- scheme: every scheme this document is mainly about (e.g., "DPIIT Startup Recognition", "Startup India Seed Fund Scheme").
- authority: every authority or body mentioned (e.g., "DPIIT", "Ministry of Commerce").
- state: every state or region mentioned (e.g., "Tamil Nadu", "Delhi").
- benefit_type: every type of benefit mentioned (e.g., "tax exemption", "seed funding", "recognition").
