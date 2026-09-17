import json
import tempfile
import unittest
from pathlib import Path

from search_sync.publish import assemble_site


class PublishTests(unittest.TestCase):
    def test_assemble_site_copies_entrypoint_assets_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            web = root / "web"
            pagefind = root / "pagefind"
            web.mkdir()
            pagefind.mkdir()
            (web / "index.html").write_text("<html></html>", encoding="utf-8")
            for filename in ("pagefind.js", "pagefind-ui.js", "pagefind-ui.css"):
                (pagefind / filename).write_text(filename, encoding="utf-8")
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps({"site_id": "example", "corpus_generation": 3, "count": 4, "excluded": [], "manifest_hash": "abc"}),
                encoding="utf-8",
            )

            result = assemble_site(
                web_dir=web,
                pagefind_dir=pagefind,
                output_dir=root / "site",
                manifest_path=manifest,
            )

            self.assertEqual(result.record_count, 4)
            self.assertTrue((root / "site" / "index.html").exists())
            self.assertTrue((root / "site" / "pagefind" / "pagefind-ui.js").exists())
            metadata = json.loads((root / "site" / "build.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["corpus_generation"], 3)
            self.assertEqual(metadata["manifest_hash"], "abc")
            self.assertEqual(len(metadata["entrypoint_hash"]), 64)

    def test_second_assembly_replaces_old_files_as_a_unit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            web = root / "web"
            pagefind = root / "pagefind"
            web.mkdir()
            pagefind.mkdir()
            (web / "index.html").write_text("v1", encoding="utf-8")
            for filename in ("pagefind.js", "pagefind-ui.js", "pagefind-ui.css"):
                (pagefind / filename).write_text("v1", encoding="utf-8")
            output = root / "site"
            assemble_site(web_dir=web, pagefind_dir=pagefind, output_dir=output)
            (web / "index.html").write_text("v2", encoding="utf-8")
            (pagefind / "old.pf").write_text("new", encoding="utf-8")
            assemble_site(web_dir=web, pagefind_dir=pagefind, output_dir=output)

            self.assertEqual((output / "index.html").read_text(encoding="utf-8"), "v2")
            self.assertTrue((output / "pagefind" / "old.pf").exists())
