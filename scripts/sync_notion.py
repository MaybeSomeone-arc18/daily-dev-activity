import os
import time
from pathlib import Path

import requests


NOTION_TOKEN = os.environ["NOTION_TOKEN"]
DATA_SOURCE_ID = os.environ["NOTION_DATA_SOURCE_ID"]

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2026-03-11",
    "Content-Type": "application/json",
}

MAX_RETRIES = 5
BASE_BACKOFF_SECONDS = 2


def rich_text_title(page):
    title = page.get("properties", {}).get("Task", {}).get("title", [])
    return "".join(item.get("plain_text", "") for item in title).strip()


def prop_value(props, name):
    property_data = props.get(name, {})
    property_type = property_data.get("type")

    if property_type == "checkbox":
        return property_data.get("checkbox", False)
    if property_type == "status":
        return (property_data.get("status") or {}).get("name")
    if property_type == "select":
        return (property_data.get("select") or {}).get("name")
    return None


def task_date(props):
    """Return the task's own Date property as YYYY-MM-DD (or None)."""
    date_property = props.get("Date") or {}
    date_data = date_property.get("date") or {}
    start = date_data.get("start")
    if not start:
        return None
    return start[:10]


def post_with_retry(url, body):
    last_status = None
    last_text = None

    for attempt in range(MAX_RETRIES + 1):
        response = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=30,
        )

        if response.ok:
            return response

        last_status = response.status_code
        last_text = response.text

        # Retry transient failures, especially the Notion 503 datastore timeout
        # seen when the API's connection pool is temporarily exhausted.
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

        # Deterministic jitter keeps this safe in CI without adding randomness
        # to the workflow output.
        delay += 0.25 * (attempt + 1)
        print(
            f"Notion API {response.status_code}; retrying in "
            f"{delay:.2f}s (attempt {attempt + 1}/{MAX_RETRIES})..."
        )
        time.sleep(delay)

    raise RuntimeError(
        f"Notion API {last_status} after {MAX_RETRIES + 1} attempts: {last_text}"
    )


def fetch_all_pages():
    """Fetch every page from the Notion data source (handles pagination)."""
    url = f"https://api.notion.com/v1/data_sources/{DATA_SOURCE_ID}/query"
    # Keep page_size below the maximum because Notion explicitly recommends
    # reducing page_size for transient datastore/connection-pool timeouts.
    body = {"page_size": 50, "result_type": "page"}

    pages = []
    cursor = None

    while True:
        if cursor:
            body["start_cursor"] = cursor

        response = post_with_retry(url, body)
        data = response.json()
        pages.extend(data.get("results", []))

        if not data.get("has_more"):
            break

        cursor = data.get("next_cursor")
        if not cursor:
            break

    return pages


def main():
    pages = fetch_all_pages()

    # ---------------------------------------------------------
    # GROUP APPROVED TASKS BY THEIR OWN DATE
    # ---------------------------------------------------------

    tasks_by_date = {}  # "YYYY-MM-DD" -> [titles]
    ids_by_date = {}    # "YYYY-MM-DD" -> [page ids]

    for page in pages:
        props = page.get("properties", {})

        if not prop_value(props, "Publish to GitHub"):
            continue

        day = task_date(props)
        if not day:
            continue

        title = rich_text_title(page)
        if not title:
            continue

        tasks_by_date.setdefault(day, []).append(title)
        ids_by_date.setdefault(day, []).append(page["id"])

    # ---------------------------------------------------------
    # WRITE EACH DAY'S FILE
    # ---------------------------------------------------------

    published_ids = []
    written = 0

    for day, titles in sorted(tasks_by_date.items()):
        output_file = Path(f"{day[:4]}/{day[5:7]}/{day}.md")

        if output_file.exists():
            existing = output_file.read_text(encoding="utf-8")
        else:
            existing = f"# {day}\n\n## Development & Learning\n"

        changed = False
        day_published_ids = []

        for title, page_id in zip(titles, ids_by_date[day]):
            line = f"- {title}"
            if line not in existing:
                existing += line + "\n"
                changed = True
                day_published_ids.append(page_id)

        if not changed:
            continue

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(existing.rstrip() + "\n", encoding="utf-8")

        published_ids.extend(day_published_ids)
        written += len(day_published_ids)

    Path("/tmp/notion_published_ids.txt").write_text(
        "\n".join(published_ids) + ("\n" if published_ids else ""),
        encoding="utf-8",
    )

    print(f"Synced {written} new task(s) across {len(tasks_by_date)} day(s).")


if __name__ == "__main__":
    main()
