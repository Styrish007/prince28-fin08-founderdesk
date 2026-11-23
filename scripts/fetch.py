"""The polite corpus fetcher: four doors.

    uv run python scripts/fetch.py urls [--delay N] [--max-concurrency N]
    uv run python scripts/fetch.py repo OWNER/REPO --path DIR --ext .md \
        --source NAME --licence "TERMS"
    uv run python scripts/fetch.py sitemap URL --include /path/ --limit N \
        --source NAME --licence "TERMS"
    uv run python scripts/fetch.py manual FOLDER --from-url URL --source NAME \
        --licence "TERMS"
"""

import argparse
import asyncio
import datetime
import hashlib
import re as _re
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

from founderdesk.ingest.fetch import (
    USER_AGENT,
    HostGate,
    Manifest,
    ManifestRecord,
    Robots,
    Source,
    fetch_one,
)

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
MANIFEST_PATH = DATA_DIR / "manifest.jsonl"
SOURCES_PATH = DATA_DIR / "sources.csv"
MAX_CONCURRENCY = 4
DEFAULT_DELAY = 0.5


def load_sources() -> list[Source]:
    sources: list[Source] = []
    if not SOURCES_PATH.exists():
        print(
            f"error: {SOURCES_PATH} not found; create it first (Milestone 1)",
            file=sys.stderr,
        )
        sys.exit(2)
    import csv

    with SOURCES_PATH.open("r", encoding="utf-8", newline="") as f:
        # Skip comment lines (start with #) so csv.DictReader uses the real header.
        non_comment = (line for line in f if not line.lstrip().startswith("#"))
        reader = csv.DictReader(non_comment)
        for row in reader:
            url = (row.get("url") or "").strip()
            source = (row.get("source") or "").strip()
            licence = (row.get("licence") or "").strip()
            title = (row.get("title") or "").strip()
            if not url:
                continue
            if not url.startswith("http://") and not url.startswith("https://"):
                print(
                    f"error: sources row: not an http(s) URL: {url!r}",
                    file=sys.stderr,
                )
                sys.exit(2)
            if not source or not licence:
                print(
                    "error: sources row: source and licence are required",
                    file=sys.stderr,
                )
                sys.exit(2)
            sources.append(Source(url=url, source=source, licence=licence, title=title))
    return sources


async def download_all(sources: list[Source], delay: float, max_concurrency: int) -> list:
    manifest = Manifest()
    limits = httpx.Limits(
        max_connections=max_concurrency,
        max_keepalive_connections=max_concurrency,
    )
    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:
        robots = Robots(client)
        gate = HostGate(min_delay=delay)
        semaphore = asyncio.Semaphore(max_concurrency)
        tasks = [
            fetch_one(
                s.url,
                s.source,
                s.licence,
                s.title,
                client,
                robots,
                gate,
                semaphore,
                manifest,
                delay,
                max_concurrency,
            )
            for s in sources
        ]
        results = await asyncio.gather(*tasks)
    return results


def cmd_urls(args: argparse.Namespace) -> None:
    sources = load_sources()
    results = asyncio.run(download_all(sources, args.delay, args.max_concurrency))
    downloaded = sum(1 for r in results if r.status == "downloaded")
    skipped = sum(1 for r in results if r.status == "skipped")
    blocked = sum(1 for r in results if r.status == "blocked")
    failed = sum(1 for r in results if r.status == "failed")
    seconds = sum(r.seconds for r in results)
    print(
        f"sources={len(sources)} downloaded={downloaded} skipped={skipped} "
        f"blocked={blocked} failed={failed} seconds={seconds:.1f}"
    )
    for r in results:
        if r.status != "skipped":
            tag = {"downloaded": "downloaded", "blocked": "blocked robots.txt"}.get(
                r.status, f"failed {r.error}"
            )
            size = f"{r.size / 1024:.1f} kB" if r.size else ""
            print(f"  [{tag:18}] {size:>12} {r.url}")


def _manifest_record(
    source: str,
    key: str,
    url: str,
    title: str,
    path: Path,
    content: bytes,
) -> ManifestRecord:
    sha256 = hashlib.sha256(content).hexdigest()
    return ManifestRecord(
        url=url,
        source=source,
        licence="",
        title=title,
        path=str(path),
        sha256=sha256,
        size=len(content),
        fetched_at=datetime.datetime.now(datetime.UTC).isoformat(),
        status="downloaded",
    )


def cmd_repo(args: argparse.Namespace) -> None:
    repo = args.repo
    source = args.source
    licence = args.licence
    ref_args = []
    if args.ref:
        ref_args.extend(["--ref", args.ref])

    with tempfile.TemporaryDirectory() as td:
        clone_dir = Path(td) / "repo"
        cmd = (
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--no-tags",
            ]
            + ref_args
            + [f"https://github.com/{repo}", str(clone_dir)]
        )
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        result = subprocess.run(
            ["git", "-C", str(clone_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        commit = result.stdout.strip()

        RAW_DIR.mkdir(parents=True, exist_ok=True)
        dest = RAW_DIR / source
        dest.mkdir(parents=True, exist_ok=True)

        manifest = Manifest()
        added = 0
        unchanged = 0
        exts = {e.lower() for e in args.ext}
        for folder in args.path:
            src_folder = clone_dir / folder
            if not src_folder.exists():
                print(f"warning: path not found in repo: {folder}", file=sys.stderr)
                continue
            for file in src_folder.rglob("*"):
                if not file.is_file():
                    continue
                if file.suffix.lower() not in exts:
                    continue
                rel = file.relative_to(clone_dir)
                out_path = dest / rel
                out_path.parent.mkdir(parents=True, exist_ok=True)
                key = f"{source}\t{str(rel)}"
                if manifest.has(source, str(rel)):
                    unchanged += 1
                    continue
                content = file.read_bytes()
                rec = _manifest_record(
                    source,
                    key,
                    f"https://github.com/{repo}/blob/{commit}/{rel}",
                    str(rel),
                    out_path,
                    content,
                )
                rec.licence = licence
                manifest.add(rec)
                added += 1
        print(f"repo={repo} commit={commit[:8]} added={added} unchanged={unchanged}")


def cmd_sitemap(args: argparse.Namespace) -> None:
    try:
        resp = httpx.get(args.url, headers={"User-Agent": USER_AGENT}, timeout=30.0)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"error: could not read the sitemap: {exc}", file=sys.stderr)
        sys.exit(2)

    text = resp.text
    if "<urlset" not in text and "<sitemapindex" not in text:
        print("error: could not read the sitemap (not XML)", file=sys.stderr)
        sys.exit(2)

    urls = _re.findall(r"<loc>(.*?)</loc>", text)
    if args.include:
        matched = [u for u in urls if any(inc in u for inc in args.include)]
    else:
        matched = list(urls)
    if args.exclude:
        matched = [u for u in matched if not any(exc in u for exc in args.exclude)]
    matched = matched[: args.limit]

    SOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: set[str] = set()
    file_empty = not SOURCES_PATH.exists() or SOURCES_PATH.stat().st_size == 0
    if SOURCES_PATH.exists() and not file_empty:
        import csv

        with SOURCES_PATH.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing.add((row.get("url") or "").strip())

    new_rows = 0
    with SOURCES_PATH.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        if file_empty:
            writer.writerow(["url", "source", "licence", "title"])
        for u in matched:
            if u in existing:
                continue
            writer.writerow([u, args.source, args.licence, u])
            new_rows += 1

    print(f"sitemap_urls={len(urls)} matched={len(matched)} added_to_sources={new_rows}")


def cmd_manual(args: argparse.Namespace) -> None:
    folder = Path(args.folder)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = Manifest()
    added = 0
    for file in sorted(folder.rglob("*")):
        if not file.is_file():
            continue
        rel = str(file.relative_to(folder))
        key = f"{args.source}\t{rel}"
        if manifest.has(args.source, rel):
            continue
        content = file.read_bytes()
        rec = _manifest_record(
            args.source,
            key,
            args.from_url or str(file),
            rel,
            file,
            content,
        )
        rec.licence = args.licence
        manifest.add(rec)
        added += 1
    print(f"folder={folder} added={added}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Polite resumable corpus fetcher")
    sub = p.add_subparsers(dest="command", required=True)

    p_urls = sub.add_parser("urls", help="Download all URLs in data/sources.csv")
    p_urls.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help="Seconds between requests to one site",
    )
    p_urls.add_argument(
        "--max-concurrency",
        type=int,
        default=MAX_CONCURRENCY,
        help="Max downloads at once",
    )
    p_urls.set_defaults(func=cmd_urls)

    p_repo = sub.add_parser("repo", help="Clone a Git repo folder into the corpus")
    p_repo.add_argument("repo", help="OWNER/REPO")
    p_repo.add_argument(
        "--path",
        action="append",
        required=True,
        help="Folder inside the repo (repeatable)",
    )
    p_repo.add_argument(
        "--ext",
        action="append",
        required=True,
        help="File types to keep (repeatable)",
    )
    p_repo.add_argument("--source", required=True, help="Source name for the manifest")
    p_repo.add_argument("--licence", required=True, help="Licence or terms for the manifest")
    p_repo.add_argument("--ref", help="Branch or tag name")
    p_repo.set_defaults(func=cmd_repo)

    p_sitemap = sub.add_parser("sitemap", help="Add sitemap URLs to sources.csv")
    p_sitemap.add_argument("url", help="Sitemap URL")
    p_sitemap.add_argument(
        "--include",
        action="append",
        required=True,
        help="Substring to include (repeatable)",
    )
    p_sitemap.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Substring to exclude (repeatable)",
    )
    p_sitemap.add_argument("--limit", type=int, default=300, help="Max URLs to add")
    p_sitemap.add_argument("--source", required=True, help="Source name for new rows")
    p_sitemap.add_argument("--licence", required=True, help="Licence for new rows")
    p_sitemap.set_defaults(func=cmd_sitemap)

    p_manual = sub.add_parser("manual", help="Register by-hand downloaded files")
    p_manual.add_argument("folder", help="Folder under data/raw/")
    p_manual.add_argument("--from-url", help="Page where links were found")
    p_manual.add_argument("--source", required=True, help="Source name")
    p_manual.add_argument("--licence", required=True, help="Licence or terms")
    p_manual.set_defaults(func=cmd_manual)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
