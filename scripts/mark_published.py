import os
import time
from pathlib import Path

import requests

TOKEN = os.environ["NOTION_TOKEN"]
IDS_FILE = Path("/tmp/notion_published_ids.txt")

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2026-03-11",
    "Content-Type": "application/json",
}

MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 2


def patch_with_retry(url, payload):
    last_status = None
    last_text = None

    for attempt in range(MAX_RETRIES + 1):
        response = requests.patch(
            url,
            headers=headers,
            json=payload,
            timeout=30,
        )

        if response.ok:
            return response

        last_status = response.status_code
        last_text = response.text

        if response.status_code not in {429, 500, 502, 503, 504}:
            response.raise_for_status()

        if attempt == MAX_RETRIES:
            break

        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                delay = max(float(retry_after), 0.0)
            except ValueError:
                delay = BASE_BACKOFF_SECONDS * (2**attempt)
        else:
            delay = BASE_BACKOFF_SECONDS * (2**attempt)

        delay += 0.25 * (attempt + 1)
        print(
            f"Notion API {response.status_code}; retrying in "
            f"{delay:.2f}s (attempt {attempt + 1}/{MAX_RETRIES})..."
        )
        time.sleep(delay)

    raise RuntimeError(
        f"Notion API {last_status} after {MAX_RETRIES + 1} attempts: {last_text}"
    )


if IDS_FILE.exists():
    for page_id in IDS_FILE.read_text(encoding="utf-8").splitlines():
        if not page_id:
            continue

        url = f"https://api.notion.com/v1/pages/{page_id}"
        payload = {
            "properties": {
                "GitHub Status": {"select": {"name": "Published"}}
            }
        }
        patch_with_retry(url, payload)
