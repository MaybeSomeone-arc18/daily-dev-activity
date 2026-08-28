import os
from pathlib import Path

import requests


NOTION_TOKEN = os.environ["NOTION_TOKEN"]
DATA_SOURCE_ID = os.environ["NOTION_DATA_SOURCE_ID"]

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2026-03-11",
    "Content-Type": "application/json",
}


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


def fetch_all_pages():
    """Fetch every page from the Notion data source (handles pagination)."""
    url = f"https://api.notion.com/v1/data_sources/{DATA_SOURCE_ID}/query"
    body = {"page_size": 100, "result_type": "page"}

    pages = []
    cursor = None

    while True:
        if cursor:
            body["start_cursor"] = cursor

        response = requests.post(url, headers=headers, json=body, timeout=30)

        if not response.ok:
            raise RuntimeError(
                f"Notion API {response.status_code}: {response.text}"
            )

        data = response.json()
        pages.extend(data.get("results", []))

        if not data.get("has_more"):
            break

        cursor = data.get("next_cursor")

    return pages


def main():
    pages = fetch_all_pages()

    # ---------------------------------------------------------
    # GROUP APPROVED TASKS BY THEIR OWN DATE
    #
    # The publishing switch is still "Publish to GitHub".
    # But we no longer care what day it is *right now* — each
    # task is filed under its own Date property. This removes
    # the IST/UTC midnight-drift bug entirely: a run that fires
    # late (or catches up days later) still lands correctly.
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
    #
    # A file is only created/updated when it gains a NEW line.
    # An empty day is never written, so it can never produce a
    # misleading "empty header" commit.
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
        for title in titles:
            line = f"- {title}"
            if line not in existing:
                existing += line + "\n"
                changed = True

        # Nothing new for this day → leave the file untouched.
        if not changed:
            continue

        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(existing.rstrip() + "\n", encoding="utf-8")

        published_ids.extend(ids_by_date[day])
        written += len(titles)

    Path("/tmp/notion_published_ids.txt").write_text(
        "\n".join(published_ids) + ("\n" if published_ids else ""),
        encoding="utf-8",
    )

    print(f"Synced {written} new task(s) across {len(tasks_by_date)} day(s).")


if __name__ == "__main__":
    main()
