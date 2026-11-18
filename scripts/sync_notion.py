import os
import re
import time
from pathlib import Path
from datetime import date

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
# Do not release old selections when repairing the publication rules.
# Earlier dates require a separately reviewed backfill. Existing logs stay intact.
PUBLISH_FROM_DATE = "2026-11-18"

# Explicit publication approval is the gate. Do not guess technical intent
# from title keywords: short project names and course abbreviations are valid.
PRIVATE_OR_NONTECHNICAL = re.compile(
    r"\b(journal|diary|personal|relationship|family|friend|meeting|call|"
    r"travel|flight|ticket|packing|pg|house|rent|shopping|grocery|"
    r"gym|health|doctor|therapy|finance|payment|salary|birthday|"
    r"party|outing|date|romantic|office pravesh|follow.?up)\b",
    re.IGNORECASE,
)


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


def exclusion_reason(props, title):
    if not prop_value(props, "Publish to GitHub"):
        return "not_selected"
    # Support checkbox and status/select completion schemas.
    # Never treat an arbitrary nonempty status as done.
    if prop_value(props, "Done") not in (True, "Done"):
        return "not_done"
    if not title:
        return "empty_title"
    if PRIVATE_OR_NONTECHNICAL.search(title):
        return "private_title"
    return None


def is_public_technical_task(props, title):
    return exclusion_reason(props, title) is None


def task_date(props):
    date_property = props.get("Date") or {}
    date_data = date_property.get("date") or {}
    start = date_data.get("start")
    return start[:10] if start else None


def post_with_retry(url, body):
    last_status = None
    last_text = None

    for attempt in range(MAX_RETRIES + 1):
        response = requests.post(url, headers=headers, json=body, timeout=30)
        if response.ok:
            return response

        last_status, last_text = response.status_code, response.text
        if response.status_code not in {429, 500, 502, 503, 504}:
            response.raise_for_status()
        if attempt == MAX_RETRIES:
            break

        retry_after = response.headers.get("Retry-After")
        try:
            delay = max(float(retry_after), 0.0) if retry_after else BASE_BACKOFF_SECONDS * (2**attempt)
        except ValueError:
            delay = BASE_BACKOFF_SECONDS * (2**attempt)
        delay += 0.25 * (attempt + 1)
        print(f"Notion API {response.status_code}; retrying in {delay:.2f}s (attempt {attempt + 1}/{MAX_RETRIES})...")
        time.sleep(delay)

    raise RuntimeError(f"Notion API {last_status} after {MAX_RETRIES + 1} attempts: {last_text}")


def fetch_all_pages():
    url = f"https://api.notion.com/v1/data_sources/{DATA_SOURCE_ID}/query"
    body = {"page_size": 50, "result_type": "page"}
    pages, cursor = [], None

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
    tasks_by_date, ids_by_date = {}, {}
    counts = {"fetched": len(pages), "not_selected": 0, "not_done": 0,
              "empty_title": 0, "private_title": 0, "invalid_date": 0, "historical_held": 0, "eligible": 0}

    completion_types = {}
    for page in pages:
        props = page.get("properties", {})
        completion_type = (props.get("Done") or {}).get("type", "missing")
        completion_types[completion_type] = completion_types.get(completion_type, 0) + 1
        title = rich_text_title(page)
        reason = exclusion_reason(props, title)
        if reason:
            counts[reason] += 1
            continue

        day = task_date(props)
        if not day or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day):
            counts["invalid_date"] += 1
            continue
        try:
            date.fromisoformat(day)
        except ValueError:
            counts["invalid_date"] += 1
            continue
        if day < PUBLISH_FROM_DATE:
            counts["historical_held"] += 1
            continue
        counts["eligible"] += 1

        tasks_by_date.setdefault(day, []).append(title)
        ids_by_date.setdefault(day, []).append(page["id"])

    published_ids, written = [], 0

    for day, titles in sorted(tasks_by_date.items()):
        output_file = Path(f"{day[:4]}/{day[5:7]}/{day}.md")
        existing = output_file.read_text(encoding="utf-8") if output_file.exists() else (
            f"# {day}\n\n## Development & Learning\n"
        )

        existing_lines = set(existing.splitlines())
        changed, day_published_ids = False, []
        for title, page_id in zip(titles, ids_by_date[day]):
            line = "- " + " ".join(title.splitlines())
            if line not in existing_lines:
                existing += line + "\n"
                existing_lines.add(line)
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
    # Counts only: private Notion task titles must not appear in public CI logs.
    print("Completion property types: " + ", ".join(f"{key}={value}" for key, value in sorted(completion_types.items())))
    print("Task counts: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    print(f"Synced {written} approved task(s) across {len(tasks_by_date)} day(s).")


if __name__ == "__main__":
    main()
