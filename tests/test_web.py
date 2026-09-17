import unittest
from pathlib import Path


class WebPageTests(unittest.TestCase):
    def test_search_page_is_compact_and_exposes_resize_protocol(self):
        page = (Path(__file__).parents[1] / "web" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="search-input"', page)
        self.assertNotIn("<h1>", page)
        self.assertNotIn("RanDomWiki 搜索", page)
        self.assertNotIn("结果链接会返回目标 Wikidot 页面", page)
        self.assertIn('./orama/search.js', page)
        self.assertIn('wymbot-search-height', (Path(__file__).parents[1] / "web" / "search.js").read_text(encoding="utf-8"))
        self.assertIn("ResizeObserver", (Path(__file__).parents[1] / "web" / "search.js").read_text(encoding="utf-8"))
        self.assertIn('<base target="_blank">', page)
        search_script = (Path(__file__).parents[1] / "web" / "search.js").read_text(encoding="utf-8")
        self.assertIn('link.rel = "noopener noreferrer"', search_script)
        self.assertIn('compositionstart', search_script)
        self.assertIn('compositionend', search_script)
