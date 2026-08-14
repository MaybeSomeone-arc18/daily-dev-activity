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
    return "".join(x.get("plain_text", "") for x in title).strip()


def prop_value(props, name):
    p = props.get(name, {})
    typ = p.get("type")

    if typ == "checkbox":
        return p.get("checkbox", False)

    if typ == "status":
        return (p.get("status") or {}).get("name")

    if typ == "select":
        return (p.get("select") or {}).get("name")

    return None


def main():
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()

    url = f"https://api.notion.com/v1/data_sources/{DATA_SOURCE_ID}/query"

    body = {
        "page_size": 100,
        "result_type": "page",
    }

    pages = []
    cursor = None

    # Fetch all pages from the Notion data source
    while True:
        if cursor:
            body["start_cursor"] = cursor

        r = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=30,
        )

        if not r.ok:
            raise RuntimeError(
                f"Notion API {r.status_code}: {r.text}"
            )

        data = r.json()

        pages.extend(data.get("results", []))

        if not data.get("has_more"):
            break

        cursor = data.get("next_cursor")

    # Only the "Publish to GitHub" checkbox decides
    # whether a page should be synced.
    approved = []

    for page in pages:
        props = page.get("properties", {})

        if not prop_value(props, "Publish to GitHub"):
            continue

        title = rich_text_title(page)

        if not title:
            continue

        approved.append((page["id"], title))

    # Nothing selected for publishing
    if not approved:
        Path("/tmp/notion_published_ids.txt").write_text(
            "",
            encoding="utf-8",
        )
        return

    # Keep the existing daily GitHub file structure
    out = Path(f"{today[:4]}/{today[5:7]}/{today}.md")

    out.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    existing = (
        out.read_text(encoding="utf-8")
        if out.exists()
        else f"# {today}\n\n## Development & Learning\n"
    )

    publish_ids = []

    for page_id, title in approved:
        line = f"- {title}"

        if line not in existing:
            existing += line + "\n"

        publish_ids.append(page_id)

    out.write_text(
        existing.rstrip() + "\n",
        encoding="utf-8",
    )

    Path("/tmp/notion_published_ids.txt").write_text(
        "\n".join(publish_ids) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
