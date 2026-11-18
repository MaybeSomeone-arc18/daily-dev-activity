import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("NOTION_TOKEN", "test-only")
os.environ.setdefault("NOTION_DATA_SOURCE_ID", "test-only")
spec = importlib.util.spec_from_file_location("sync_notion", Path(__file__).with_name("sync_notion.py"))
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def props(done=True, selected=True, kind="checkbox", day="2026-11-18"):
    completion = done if kind == "checkbox" else {"name": done}
    return {"Done": {"type": kind, kind: completion},
            "Publish to GitHub": {"type": "checkbox", "checkbox": selected},
            "Date": {"date": {"start": day}}}


def page(title, properties, page_id="synthetic"):
    return {"id": page_id, "properties": {**properties, "Task": {"title": [{"plain_text": title}]}}}


class PublicationTests(unittest.TestCase):
    def test_checkbox_completion(self):
        self.assertTrue(sync.is_public_technical_task(props(), "Build example"))
        self.assertFalse(sync.is_public_technical_task(props(done=False), "Build example"))

    def test_status_completion(self):
        for kind in ("status", "select"):
            self.assertTrue(sync.is_public_technical_task(props("Done", kind=kind), "Build example"))
            self.assertFalse(sync.is_public_technical_task(props("In progress", kind=kind), "Build example"))

    def test_selected_short_titles_need_no_keyword(self):
        self.assertTrue(sync.is_public_technical_task(props(), "Course exercise"))

    def test_unselected_never_publishes(self):
        self.assertFalse(sync.is_public_technical_task(props(selected=False), "Build example"))

    def test_private_titles_stay_blocked(self):
        for title in ("Personal journal", "Family call", "Book flight tickets", "Python meeting follow-up"):
            self.assertFalse(sync.is_public_technical_task(props(), title))

    def test_missing_completion_fails_closed(self):
        p = props()
        del p["Done"]
        self.assertFalse(sync.is_public_technical_task(p, "Build example"))

    def test_empty_title_blocked(self):
        self.assertFalse(sync.is_public_technical_task(props(), ""))

    def test_full_sync_privacy_dates_idempotence_and_exact_lines(self):
        pages = [page("Build example extended", props(), "long"),
                 page("Build example", props(), "short"),
                 page("Private journal", props(), "private"),
                 page("Unselected code", props(selected=False), "unselected"),
                 page("Old example", props(day="2026-11-17"), "old"),
                 page("Bad date", props(day="2026-99-99"), "bad")]
        with tempfile.TemporaryDirectory() as tmp:
            previous = Path.cwd()
            manifest = Path(tmp) / "manifest.txt"
            real_path = Path
            def local_path(value):
                return manifest if value == "/tmp/notion_published_ids.txt" else real_path(value)
            try:
                os.chdir(tmp)
                with patch.object(sync, "fetch_all_pages", return_value=pages), patch.object(sync, "Path", side_effect=local_path):
                    log = io.StringIO()
                    with contextlib.redirect_stdout(log):
                        sync.main()
                    output = Path("2026/11/2026-11-18.md").read_text()
                    self.assertIn("- Build example\n", output)
                    self.assertIn("- Build example extended\n", output)
                    self.assertNotIn("journal", output)
                    self.assertNotIn("Unselected", output)
                    self.assertFalse(Path("2026/11/2026-11-17.md").exists())
                    self.assertEqual(manifest.read_text().splitlines(), ["long", "short"])
                    self.assertNotIn("Build example", log.getvalue())
                    self.assertIn("historical_held=1", log.getvalue())
                    with contextlib.redirect_stdout(io.StringIO()):
                        sync.main()
                    self.assertEqual(Path("2026/11/2026-11-18.md").read_text(), output)
                    self.assertEqual(manifest.read_text(), "")
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
