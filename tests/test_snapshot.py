import tempfile
import unittest
from pathlib import Path

from search_sync.models import ManifestEntry, RenderedPage, SourcePage
from search_sync.sync.snapshot import RecordSnapshotter, SnapshotError
from search_sync.sync.state import StateStore
from search_sync.sync.worker import FetchWorker


class FakeSite:
    def page_url(self, fullname: str) -> str:
        return f"http://example/{fullname}"

    def fetch_rendered(self, fullname: str) -> RenderedPage:
        html = "<html><body><div id='page-content'><p>一致快照正文</p></div></body></html>"
        return RenderedPage(fullname, 7001, self.page_url(fullname), html)

    def fetch_source(self, page_id: int) -> SourcePage:
        return SourcePage(page_id, "[[module CSS]]", "<div class='page-source'>[[module CSS]]</div>")


class SnapshotTests(unittest.TestCase):
    def test_snapshot_contains_only_active_hash_verified_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with StateStore(root / "state.sqlite3") as store:
                row_id, _ = store.observe_manifest_entry(
                    site_id="example",
                    entry=ManifestEntry("article:one", "One", 100, 1),
                    canonical_url="http://example/article:one",
                )
                result = FetchWorker(FakeSite(), store, cache_dir=root / "cache").run_once(limit=1)
                self.assertEqual(result[0].status, "fetched")
                snapshot = RecordSnapshotter(store, cache_dir=root / "cache").export(
                    site_id="example", output_dir=root / "snapshot"
                )

                self.assertEqual(snapshot.count, 1)
                self.assertEqual(snapshot.generation, 1)
                manifest = (root / "snapshot" / "manifest.json").read_text(encoding="utf-8")
                self.assertIn('"count": 1', manifest)
                self.assertTrue((root / "snapshot" / "records" / "00000001" / "record.json").exists())
                self.assertEqual(store.page_state(row_id)["status"], "active")
                second = RecordSnapshotter(store, cache_dir=root / "cache").export(
                    site_id="example", output_dir=root / "snapshot-2"
                )
                self.assertEqual(second.generation, 2)

    def test_snapshot_refuses_observed_fetched_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with StateStore(root / "state.sqlite3") as store:
                store.observe_manifest_entry(
                    site_id="example",
                    entry=ManifestEntry("article:one", "One", 100, 1),
                    canonical_url="http://example/article:one",
                )
                worker = FetchWorker(FakeSite(), store, cache_dir=root / "cache")
                self.assertEqual(worker.run_once(limit=1)[0].status, "fetched")
                store.observe_manifest_entry(
                    site_id="example",
                    entry=ManifestEntry("article:one", "One", 101, 2),
                    canonical_url="http://example/article:one",
                )

                with self.assertRaises(SnapshotError):
                    RecordSnapshotter(store, cache_dir=root / "cache").export(
                        site_id="example", output_dir=root / "snapshot"
                    )
