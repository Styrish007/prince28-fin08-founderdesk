"""Compare every prompt version on every question → table in NOTES.md.

Caches answers in eval/cache/ so re-runs don't call the model again.
Prints how many new model calls were made.
Checks for LEAK: any test question appearing in a prompt file.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

from founderdesk.config import get_settings
from founderdesk.llm.classify import classify, parse_label
from founderdesk.llm.gateway import LLMGateway

CACHE_DIR = Path("eval/cache")
TESTSET_PATH = Path("eval/prompt_testset.jsonl")
NOTES_PATH = Path("NOTES.md")
PROMPTS_DIR = Path("prompts")


def _load_testset() -> list[dict[str, str]]:
    """Load questions and labels from the test set."""
    rows: list[dict[str, str]] = []
    for line in TESTSET_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _cache_path(version: str, line_no: int) -> Path:
    """Cache file for a version × question pair."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = version.replace("/", "_").replace("\\", "_")
    return CACHE_DIR / f"{safe}_line{line_no}.json"


def _get_cached(version: str, line_no: int) -> str | None:
    """Return cached reply text, or None if not cached."""
    path = _cache_path(version, line_no)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("reply")
    except (json.JSONDecodeError, OSError):
        return None


def _save_cache(version: str, line_no: int, reply: str) -> None:
    """Cache a reply text."""
    path = _cache_path(version, line_no)
    path.write_text(json.dumps({"reply": reply}, ensure_ascii=False), encoding="utf-8")


def _check_leaks() -> list[str]:
    """Return leaked test questions found in prompt files."""
    from founderdesk.llm.classify import find_leaks

    return find_leaks("prompts")


async def _run_comparison(
    gateway: LLMGateway, rows: list[dict[str, str]]
) -> tuple[dict[str, dict], int]:
    """Run every version × every question. Returns per-version stats and new call count."""
    all_versions = list(PROMPTS_DIR.glob("classify_v*.md"))
    version_names = [p.stem for p in all_versions]

    results: dict[str, dict] = {}
    for vname in version_names:
        results[vname] = {"correct": 0, "total": 0, "misses": []}

    new_calls = 0
    for line_no, row in enumerate(rows, 1):
        question = row["question"]
        true_label = row["label"]
        for vname in version_names:
            results[vname]["total"] += 1
            cached = _get_cached(vname, line_no)
            if cached is not None:
                reply = cached
            else:
                label, reply = await classify(
                    gateway, question, prompt_version=f"prompts/{vname}.md"
                )
                _save_cache(vname, line_no, reply)
                new_calls += 1
                await asyncio.sleep(5.0)  # 12 per minute
            predicted = parse_label(reply)
            if predicted == true_label:
                results[vname]["correct"] += 1
            else:
                results[vname]["misses"].append(
                    {
                        "line": line_no,
                        "wanted": true_label,
                        "got": predicted or "invalid",
                        "reply": reply[:80],
                    }
                )

    return results, new_calls


def _write_notes_table(results: dict[str, dict], new_calls: int) -> None:
    """Append the comparison table to NOTES.md."""
    lines: list[str] = []
    lines.append("")
    lines.append("## D09 · Prompt comparison")
    lines.append("")
    lines.append("| Version | Correct | Total | Accuracy |")
    lines.append("|---|---|---|---|")
    for vname in sorted(results):
        r = results[vname]
        acc = r["correct"] / r["total"] * 100 if r["total"] else 0
        lines.append(f"| {vname} | {r['correct']} | {r['total']} | {acc:.0f}% |")
    lines.append("")
    lines.append(f"Model calls made now: {new_calls}")
    lines.append("(the rest came from the cache) -> table in NOTES.md")
    lines.append("")

    existing = NOTES_PATH.read_text(encoding="utf-8") if NOTES_PATH.is_file() else ""
    existing = re.sub(r"\n## D09 · Prompt comparison.*", "", existing, flags=re.DOTALL)
    NOTES_PATH.write_text(existing + "\n".join(lines), encoding="utf-8")


async def _amain() -> None:
    settings = get_settings()
    gateway = LLMGateway(settings)
    rows = _load_testset()

    leaks = _check_leaks()
    if leaks:
        print("LEAK: test questions found in prompt files:")
        for leak in leaks:
            print(f"  - {leak[:80]}")
        sys.exit(1)

    results, new_calls = await _run_comparison(gateway, rows)
    _write_notes_table(results, new_calls)

    for vname in sorted(results):
        r = results[vname]
        acc = r["correct"] / r["total"] * 100 if r["total"] else 0
        print(f"{vname}    {r['correct']}/{r['total']}  {acc:.0f}%")

    print(f"Model calls made now: {new_calls}")
    print("(the rest came from the cache) -> table in NOTES.md")


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
