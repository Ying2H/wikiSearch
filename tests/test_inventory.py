import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from search_sync.crawler.manifest import parse_manifest_html
from search_sync.models import ManifestPage
from search_sync.sync.inventory import InventoryScanner
from search_sync.sync.state import StateStore


FIXTURES = Path(__file__).parent / "fixtures"


class FakeSite:
    def __init__(self):
        self.pages = {
            None: parse_manifest_html((FIXTURES / "manifest_page1.html").read_text(encoding="utf-8")),
            "/pagelist/p/2": parse_manifest_html((FIXTURES / "manifest_page2.html").read_text(encoding="utf-8")),
        }

    def read_manifest_page(self, cursor=None) -> ManifestPage:
        return self.pages[cursor]

    @staticmethod
    def page_url(fullname: str) -> str:
        return f"http://example/{fullname}"


class InventoryTests(unittest.TestCase):
    def test_complete_scan_advances_watermark_only_after_last_page(self):
        with TemporaryDirectory() as temp_dir:
            with StateStore(Path(temp_dir) / "state.sqlite3") as store:
                result = InventoryScanner(FakeSite(), store, site_id="example").scan(max_pages=2, inventory_id="scan-1")

                self.assertTrue(result.coverage_complete)
                self.assertEqual(result.pages_read, 2)
                self.assertEqual(result.entries_seen, 4)
                self.assertEqual(result.watermark, 1785547798)
                self.assertEqual(store.page_count("example"), 4)
                self.assertEqual(store.queued_job_count("example"), 4)

    def test_budget_exhaustion_is_incomplete(self):
        with TemporaryDirectory() as temp_dir:
            with StateStore(Path(temp_dir) / "state.sqlite3") as store:
                result = InventoryScanner(FakeSite(), store, site_id="example").scan(max_pages=1, inventory_id="scan-2")

                self.assertFalse(result.coverage_complete)
                self.assertIsNone(result.watermark)
                self.assertEqual(result.next_cursor, "/pagelist/p/2")
