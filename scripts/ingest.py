"""Start an ingestion through the API and watch it until it finishes."""

import argparse
import asyncio

import httpx


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Queue an ingestion through the API and watch progress."
    )
    parser.add_argument("--limit", type=int, default=0, help="ingest at most N documents")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--admin-token", default=None, help="Admin token (X-Admin-Token header)")
    parser.add_argument("--retry-failed", action="store_true", help="retry previously failed items")
    args = parser.parse_args()

    from founderdesk.config import Settings

    settings = Settings()
    token = args.admin_token or settings.admin_token
    headers = {"X-Admin-Token": token}

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Queue the ingestion.
        resp = await client.post(f"{args.url}/v1/ingest", headers=headers)
        if resp.status_code == 401:
            print("HTTP 401: Missing or wrong X-Admin-Token header.")
            return
        if resp.status_code >= 400:
            print(f"HTTP {resp.status_code}: {resp.text[:200]}")
            return

        body = resp.json()
        job_id = body["job_id"]
        print(f"HTTP 202: job {job_id}, {body['queued']} queued")

        # Poll for progress.
        last = ""
        while True:
            resp = await client.get(f"{args.url}/v1/ingest/{job_id}")
            if resp.status_code >= 400:
                print(f"HTTP {resp.status_code}: {resp.text[:200]}")
                return
            progress = resp.json()
            queued = (
                progress["items_total"]
                - progress["items_done"]
                - progress["items_failed"]
                - progress["items_skipped"]
            )
            line = (
                f"{progress['status']}   queued={queued} running=0 "
                f"done={progress['items_done']} skipped={progress['items_skipped']} "
                f"failed={progress['items_failed']}"
            )
            if line != last:
                print(line)
                last = line
            if progress["status"] in ("done", "failed"):
                break
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
