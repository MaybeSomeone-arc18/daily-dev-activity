import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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

    return "".join(
        item.get("plain_text", "")
        for item in title
    ).strip()


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
    """
    Get the Notion Date property.

    Returns:
        YYYY-MM-DD

    Example:
        2026-08-16
    """

    date_property = props.get("Date") or {}
    date_data = date_property.get("date") or {}
    start = date_data.get("start")

    if not start:
        return None

    return start[:10]


def fetch_all_pages():
    """
    Fetch every page from the Notion data source.
    Handles pagination automatically.
    """

    url = (
        f"https://api.notion.com/v1/"
        f"data_sources/{DATA_SOURCE_ID}/query"
    )

    body = {
        "page_size": 100,
        "result_type": "page",
    }

    pages = []
    cursor = None

    while True:
        if cursor:
            body["start_cursor"] = cursor

        response = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=30,
        )

        if not response.ok:
            raise RuntimeError(
                f"Notion API {response.status_code}: "
                f"{response.text}"
            )

        data = response.json()

        pages.extend(
            data.get("results", [])
        )

        if not data.get("has_more"):
            break

        cursor = data.get("next_cursor")

    return pages


def main():
    # ---------------------------------------------------------
    # TODAY
    # ---------------------------------------------------------

    today = (
        datetime.now(
            ZoneInfo("Asia/Kolkata")
        )
        .date()
        .isoformat()
    )

    print(f"Syncing Notion tasks for: {today}")

    # ---------------------------------------------------------
    # FETCH NOTION
    # ---------------------------------------------------------

    pages = fetch_all_pages()

    # ---------------------------------------------------------
    # ONLY TODAY'S PUBLISHED TASKS
    #
    # IMPORTANT:
    #
    # Date = today
    # Publish to GitHub = checked
    #
    # Nothing else matters.
    #
    # We DO NOT check:
    # - Done
    # - GitHub Status
    # - private/public keywords
    # - programming keywords
    # ---------------------------------------------------------

    today_tasks = []

    for page in pages:
        props = page.get("properties", {})

        # Ignore tasks from other dates.
        page_date = task_date(props)

        if page_date != today:
            continue

        # This is the ONLY publishing switch.
        if not prop_value(
            props,
            "Publish to GitHub",
        ):
            continue

        title = rich_text_title(page)

        if not title:
            continue

        today_tasks.append(
            title
        )

    # ---------------------------------------------------------
    # TODAY'S GITHUB FILE
    # ---------------------------------------------------------

    output_file = Path(
        f"{today[:4]}/"
        f"{today[5:7]}/"
        f"{today}.md"
    )

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ---------------------------------------------------------
    # READ EXISTING TODAY FILE
    #
    # IMPORTANT:
    #
    # We ONLY touch today's file.
    #
    # Old files are never opened, changed, deleted,
    # or synchronized.
    # ---------------------------------------------------------

    if output_file.exists():
        existing = output_file.read_text(
            encoding="utf-8"
        )
    else:
        existing = (
            f"# {today}\n\n"
            "## Development & Learning\n"
        )

    # ---------------------------------------------------------
    # ADD TODAY'S SELECTED TASKS
    #
    # Existing lines are preserved.
    # A task is only added if it isn't already present.
    # ---------------------------------------------------------

    for title in today_tasks:
        line = f"- {title}"

        if line not in existing:
            existing += line + "\n"

    # ---------------------------------------------------------
    # WRITE ONLY TODAY'S FILE
    # ---------------------------------------------------------

    output_file.write_text(
        existing.rstrip() + "\n",
        encoding="utf-8",
    )

    # ---------------------------------------------------------
    # SAVE TODAY'S PUBLISHED PAGE IDS
    #
    # Keep this file compatible with the rest of the workflow.
    # ---------------------------------------------------------

    today_page_ids = []

    for page in pages:
        props = page.get("properties", {})

        if task_date(props) != today:
            continue

        if not prop_value(
            props,
            "Publish to GitHub",
        ):
            continue

        title = rich_text_title(page)

        if not title:
            continue

        today_page_ids.append(
            page["id"]
        )

    Path(
        "/tmp/notion_published_ids.txt"
    ).write_text(
        "\n".join(today_page_ids)
        + (
            "\n"
            if today_page_ids
            else ""
        ),
        encoding="utf-8",
    )

    print(
        f"Synced {len(today_tasks)} task(s) "
        f"to {output_file}"
    )


if __name__ == "__main__":
    main()
