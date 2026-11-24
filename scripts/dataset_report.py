"""Measure the collected corpus and write DATASET.md and docs/CAPACITY.md.

Reads data/manifest.jsonl, opens every file: counts PDF pages (pypdf) and
samples their text, strips HTML to visible text, counts characters.
Tokens ≈ characters ÷ 4.

Only the block between the two `<!-- generated:start -->` /
`<!-- generated:end -->` markers is rewritten, so your own words survive a
re-run.

    uv run python scripts/dataset_report.py --full-pages 3000
    uv run python scripts/dataset_report.py --full-files 500
    uv run python scripts/dataset_report.py --help
"""

import argparse
import contextlib
import json
import re
from pathlib import Path

import pypdf

MANIFEST_PATH = Path("data/manifest.jsonl")
DATASET_PATH = Path("DATASET.md")
CAPACITY_PATH = Path("docs/CAPACITY.md")

START_MARKER = "<!-- generated:start -->"
END_MARKER = "<!-- generated:end -->"

CHARS_PER_TOKEN = 4
BYTES_PER_MB = 1024 * 1024


def strip_html(text: str) -> str:
    """Crude visible-text extraction from HTML (good enough for sizing)."""
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-z]+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def measure_file(path: Path) -> dict:
    """Return {chars, pages} for a file."""
    if not path.exists():
        return {"chars": 0, "pages": 0}
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            reader = pypdf.PdfReader(str(path))
            pages = len(reader.pages)
            chars = 0
            for page in reader.pages[:5]:  # sample first 5 pages
                with contextlib.suppress(Exception):
                    chars += len(page.extract_text() or "")
            # estimate total chars from the sample
            if pages > 0 and len(reader.pages) > 0:
                sample_pages = min(5, pages)
                if sample_pages > 0:
                    chars = int(chars / sample_pages * pages)
            return {"chars": chars, "pages": pages}
        except Exception:
            return {"chars": 0, "pages": 0}
    else:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return {"chars": 0, "pages": 0}
        if suffix in (".html", ".htm"):
            text = strip_html(text)
        return {"chars": len(text), "pages": 1}


def load_manifest() -> list[dict]:
    entries = []
    if not MANIFEST_PATH.exists():
        return entries
    with MANIFEST_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def replace_block(text: str, marker_block: str) -> str:
    """Replace text between START_MARKER and END_MARKER with marker_block."""
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start == -1 or end == -1 or end < start:
        return text
    return (
        text[:start]
        + START_MARKER
        + "\n"
        + marker_block
        + "\n"
        + END_MARKER
        + text[end + len(END_MARKER) :]
    )


def build_dataset_table(entries: list[dict], results: list[dict]) -> str:
    lines = ["| Source | File | Pages | Size kB | Chars | Tokens | Licence |"]
    lines.append("|---|---|---|---:|---:|---:|---|")
    for e, r in zip(entries, results, strict=False):
        path = Path(e.get("path", ""))
        size_kb = e.get("size", 0) / 1024
        lines.append(
            f"| {e.get('source', '')} | {path.name} | {r['pages']} | "
            f"{size_kb:,.1f} | {r['chars']:,} | {r['tokens']:,} | {e.get('licence', '')} |"
        )
    total_chars = sum(r["chars"] for r in results)
    total_pages = sum(r["pages"] for r in results)
    total_tokens = sum(r["tokens"] for r in results)
    lines.append(
        f"| **Total** | {len(results)} files | **{total_pages}** | "
        f"| **{total_chars:,}** | **{total_tokens:,}** | |"
    )
    return "\n".join(lines)


def build_capacity_table(
    entries: list[dict],
    results: list[dict],
    full_pages: int | None,
    full_files: int | None,
    args: argparse.Namespace,
) -> str:
    total_chars = sum(r["chars"] for r in results)
    total_pages = sum(r["pages"] for r in results)
    total_files = len(results)
    total_tokens = total_chars // CHARS_PER_TOKEN

    # Per-file averages for scaling
    avg_chars_per_file = total_chars / total_files if total_files else 0
    avg_pages_per_file = total_pages / total_files if total_files else 0

    # Full corpus estimates
    if full_files:
        full_n = full_files
        full_chars = avg_chars_per_file * full_n
        full_pages_est = avg_pages_per_file * full_n
    elif full_pages:
        full_n = int(full_pages / avg_pages_per_file) if avg_pages_per_file else full_files
        full_chars = avg_chars_per_file * full_n
        full_pages_est = full_pages
    else:
        full_n = total_files
        full_chars = total_chars
        full_pages_est = total_pages

    full_tokens = int(full_chars // CHARS_PER_TOKEN)
    chunks = max(1, int(full_tokens / args.chunk_tokens))
    # Embedding priced per 1M tokens (not per chunk)
    embed_cost_usd = (full_tokens / 1_000_000) * args.embed_usd_per_million
    embed_cost_inr = embed_cost_usd * args.usd_inr
    # rough vector size: dims * 4 bytes per chunk
    vectors_mb = chunks * args.dims * 4 / BYTES_PER_MB

    lines = []
    lines.append(
        "Measured corpus: "
        f"{total_files} files, {total_pages} pages, {total_chars:,} chars, "
        f"~{total_tokens:,} tokens."
    )
    lines.append("")
    lines.append(
        f"Full corpus target: {full_n} files ≈ {full_pages_est:.0f} pages ≈ "
        f"{full_chars:,.0f} chars ≈ {full_tokens:,} tokens."
    )
    lines.append("")
    lines.append(f"- Chunks (at {args.chunk_tokens} tokens/chunk): {chunks:,}")
    lines.append(
        "- Embedding cost: "
        f"{full_tokens:,} tokens ÷ 1M × ${args.embed_usd_per_million} = ${embed_cost_usd:,.2f} "
        f"≈ Rs {embed_cost_inr:,.0f} (at ₹{args.usd_inr}/$)"
    )
    lines.append(
        f"- Vector storage: {chunks:,} chunks × {args.dims} dims × 4 bytes ≈ {vectors_mb:,.1f} MB"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure corpus and write DATASET.md + CAPACITY.md"
    )
    parser.add_argument("--full-pages", type=int, help="Estimate full corpus size in pages")
    parser.add_argument("--full-files", type=int, help="Estimate full corpus size in files/records")
    parser.add_argument(
        "--embed-usd-per-million",
        type=float,
        default=0.20,
        help="USD per 1M tokens to embed",
    )
    parser.add_argument("--dims", type=int, default=1024, help="Embedding dimensions")
    parser.add_argument("--chunk-tokens", type=int, default=500, help="Tokens per chunk")
    parser.add_argument("--usd-inr", type=float, default=95.0, help="USD to INR rate")
    args = parser.parse_args(argv)

    entries = load_manifest()
    if not entries:
        print("nothing measurable yet: data/manifest.jsonl is empty or missing")
        print("Download PDF, HTML or text documents first")
        return 1

    results: list[dict] = []
    for e in entries:
        path = Path(e.get("path", ""))
        m = measure_file(path)
        m["tokens"] = m["chars"] // CHARS_PER_TOKEN
        results.append(m)

    total_chars = sum(r["chars"] for r in results)
    total_pages = sum(r["pages"] for r in results)
    total_files = len(results)
    total_tokens = total_chars // CHARS_PER_TOKEN
    total_mb = sum(e.get("size", 0) for e in entries) / BYTES_PER_MB

    print(
        f"files={total_files} pages={total_pages} chars={total_chars:,} "
        f"tokens≈{total_tokens:,} size={total_mb:.1f} MB"
    )

    # ---- DATASET.md ----
    dataset_text = DATASET_PATH.read_text(encoding="utf-8") if DATASET_PATH.exists() else ""
    table = build_dataset_table(entries, results)
    dataset_text = replace_block(dataset_text, table)
    DATASET_PATH.write_text(dataset_text, encoding="utf-8")

    # ---- docs/CAPACITY.md ----
    CAPACITY_PATH.parent.mkdir(parents=True, exist_ok=True)
    capacity_text = CAPACITY_PATH.read_text(encoding="utf-8") if CAPACITY_PATH.exists() else ""
    cap_block = build_capacity_table(entries, results, args.full_pages, args.full_files, args)
    capacity_text = replace_block(capacity_text, cap_block)
    CAPACITY_PATH.write_text(capacity_text, encoding="utf-8")

    print(f"wrote {DATASET_PATH} and {CAPACITY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
