import os
from pathlib import Path

import requests

TOKEN = os.environ["NOTION_TOKEN"]
DATA_SOURCE_ID = os.environ["NOTION_DATA_SOURCE_ID"]
IDS_FILE = Path("/tmp/notion_published_ids.txt")

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Notion-Version": "2025-09-03",
    "Content-Type": "application/json",
}

if IDS_FILE.exists():
    for page_id in IDS_FILE.read_text(encoding="utf-8").splitlines():
        if not page_id:
            continue
        url = f"https://api.notion.com/v1/pages/{page_id}"
        payload = {"properties": {"GitHub Status": {"select": {"name": "Published"}}}}
        r = requests.patch(url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
