import json
import tempfile
import unittest
from pathlib import Path

from search_sync.publish_diff import describe_changes


class PublishDiffTests(unittest.TestCase):
    def test_report_identifies_add_remove_and_changed_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            before, after = Path(temp) / 'before.json', Path(temp) / 'after.json'
            def write(path, docs):
                path.write_text(json.dumps({'database': {'docs': {'docs': {str(i): doc for i, doc in enumerate(docs)}}}}), encoding='utf-8')
            write(before, [{'url': 'https://example/a', 'fullname': 'a', 'content': '中文提示'}, {'url': 'https://example/removed'}])
            write(after, [{'url': 'https://example/a', 'fullname': 'a', 'content': 'English message'}, {'url': 'https://example/new'}])
            report = describe_changes(before, after)
            self.assertEqual(report['added'], ['https://example/new'])
            self.assertEqual(report['removed'], ['https://example/removed'])
            self.assertEqual(report['changed'][0]['fields'], ['content'])
            self.assertIn('-中文提示', report['changed'][0]['content_diff'])
            self.assertIn('+English message', report['changed'][0]['content_diff'])
            self.assertEqual(describe_changes(after, after)['changed'], [])
            self.assertEqual(describe_changes(Path(temp) / 'missing', after)['before_count'], 0)
