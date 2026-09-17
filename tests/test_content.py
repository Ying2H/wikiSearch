import unittest
from pathlib import Path

from search_sync.extract.content import extract_main_content, stable_record_hash


class ContentTests(unittest.TestCase):
    def test_content_extractor_removes_chrome_but_keeps_text(self):
        html = (Path(__file__).parent / "fixtures" / "rendered.html").read_text(encoding="utf-8")
        content = extract_main_content(html)

        self.assertIn("第一段中文内容。", content)
        self.assertIn("第二段正文", content)
        self.assertIn("换行。", content)
        self.assertNotIn("页脚", content)
        self.assertNotIn("编辑控件", content)
        self.assertNotIn("alert", content)

    def test_record_hash_is_stable_across_mapping_order(self):
        self.assertEqual(
            stable_record_hash({"title": "A", "content": "B"}),
            stable_record_hash({"content": "B", "title": "A"}),
        )
