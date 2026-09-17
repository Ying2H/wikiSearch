import json
import unittest
from pathlib import Path

from search_sync.crawler.manifest import parse_manifest_html, parse_source_body


FIXTURES = Path(__file__).parent / "fixtures"


class ManifestTests(unittest.TestCase):
    def test_manifest_parser_keeps_unicode_entities_and_machine_time(self):
        page = parse_manifest_html((FIXTURES / "manifest_page1.html").read_text(encoding="utf-8"), url="http://example/pagelist")

        self.assertEqual(page.page_number, 1)
        self.assertEqual(page.total_pages, 2)
        self.assertEqual(page.next_cursor, "/pagelist/p/2")
        self.assertEqual(len(page.entries), 2)
        self.assertEqual(page.entries[1].fullname, "hqsb:sp10")
        self.assertEqual(page.entries[1].title, "SP—10 & extra")
        self.assertEqual(page.entries[1].updated_at, 1787211864)
        self.assertEqual(page.entries[1].revisions, 13)

    def test_manifest_parser_retains_rows_with_empty_title(self):
        page = parse_manifest_html((FIXTURES / "manifest_page2.html").read_text(encoding="utf-8"))

        self.assertEqual([entry.fullname for entry in page.entries], ["nav:top", "start"])
        self.assertEqual([entry.title for entry in page.entries], ["", ""])
        self.assertIsNone(page.next_cursor)

    def test_amc_body_is_unescaped_once_before_dom_parsing(self):
        page = parse_manifest_html((FIXTURES / "amc_body.html").read_text(encoding="utf-8"), amc_escaped=True)

        self.assertEqual(len(page.entries), 1)
        self.assertEqual(page.entries[0].fullname, "pagelist")
        self.assertEqual(page.entries[0].updated_at, 1789614157)
        self.assertEqual(page.total_pages, 36)

    def test_source_body_preserves_markup_lines(self):
        payload = json.loads((FIXTURES / "viewsource.json").read_text(encoding="utf-8"))
        source = parse_source_body(payload["body"], page_id=123)

        self.assertEqual(source.page_id, 123)
        self.assertIn("[[module ListPages category=\"*\"]]", source.source)
        self.assertIn("[[include component:nav]]", source.source)
