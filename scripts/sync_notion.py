import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
DATA_SOURCE_ID = os.environ["NOTION_DATA_SOURCE_ID"]

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

# Conservative safety filter. Explicit approval is still required in Notion.
PRIVATE_PATTERNS = [
    r"\brelationship\b", r"\bgirlfriend\b", r"\bboyfriend\b", r"\bromantic\b",
    r"\bfamily\b", r"\bmom\b", r"\bdad\b", r"\bsister\b", r"\bbrother\b",
    r"\bfriend\b", r"\bshopping\b", r"\bshop\b", r"\bbuy\b", r"\bergand\b",
    r"\bjournal\b", r"\btherapy\b", r"\bmental health\b", r"\bhealth\b",
    r"\bmedical\b", r"\bdoctor\b", r"\bmoney\b", r"\bfinance\b", r"\bbank\b",
    r"\bpersonal\b", r"\bprivate\b", r"\btravel\b", r"\btrip\b", r"\bhome\b",
]

PUBLIC_PATTERNS = [
    r"\bpython\b", r"\bjava\b", r"\bc\+\+\b", r"\bjavascript\b", r"\breact\b",
    r"\bnode\b", r"\bflutter\b", r"\bdart\b", r"\bgithub\b", r"\bcoding\b",
    r"\bprogramming\b", r"\bdsa\b", r"\bleetcode\b", r"\bproject\b", r"\bapi\b",
    r"\bdatabase\b", r"\bdebug\b", r"\btest\b", r"\bdeploy\b", r"\bbuild\b",
    r"\bresearch\b", r"\bsoftware\b", r"\bdeveloper\b", r"\bportfolio\b",
    r"\bapple developer academy\b", r"\bmov2mp4\b", r"\bclasstrack\b",
    r"\bplaybyplay\b", r"\bcreatique\b", r"\bcontent\b", r"\blinkedin\b",
]


def rich_text_title(page):
    props = page.get("properties", {})
    title = props.get("Task", {}).get("title", [])
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


def safe_for_public(title):
    text = title.lower()
    if any(re.search(pattern, text) for pattern in PRIVATE_PATTERNS):
        return False
    return any(re.search(pattern, text) for pattern in PUBLIC_PATTERNS)


def main():
    today = datetime.now(timezone.utc).astimezone().date().isoformat()
    url = f"https://api.notion.com/v1/data_sources/{DATA_SOURCE_ID}/query"
    body = {"page_size": 100}
    pages = []
    cursor = None

    while True:
        if cursor:
            body["start_cursor"] = cursor
        r = requests.post(url, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        pages.extend(data.get("results", []))
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    approved = []
    for page in pages:
        props = page.get("properties", {})
        if prop_value(props, "Done") != "Done":
            continue
        if not prop_value(props, "Publish to GitHub"):
            continue
        if prop_value(props, "GitHub Status") == "Published":
            continue

        title = rich_text_title(page)
        if not title or not safe_for_public(title):
            continue
        approved.append((page["id"], title))

    if not approved:
        return

    out = Path(f"{today[:4]}/{today[5:7]}/{today}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    existing = out.read_text(encoding="utf-8") if out.exists() else f"# {today}\n\n## Development & Learning\n"

    for page_id, title in approved:
        line = f"- {title}"
        if line not in existing:
            existing += line + "\n"
        patch_url = f"https://api.notion.com/v1/pages/{page_id}"
        patch = {"properties": {"GitHub Status": {"select": {"name": "Published"}}}}
        requests.patch(patch_url, headers=headers, json=patch, timeout=30).raise_for_status()

    out.write_text(existing.rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
