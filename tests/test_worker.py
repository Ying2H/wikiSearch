import tempfile
import unittest
from pathlib import Path

from search_sync.models import ManifestEntry, RenderedPage, SourcePage
from search_sync.sync.state import StateStore
from search_sync.sync.worker import FetchWorker


class FakeSite:
    def page_url(self, fullname: str) -> str:
        return f"http://example/{fullname}"

    def fetch_rendered(self, fullname: str) -> RenderedPage:
        html = """<html><body><div id='page-content'><h1>示例</h1><p>可索引正文</p></div></body></html>"""
        return RenderedPage(fullname, 9001, self.page_url(fullname), html)

    def fetch_source(self, page_id: int) -> SourcePage:
        return SourcePage(page_id, "[[module CSS]]\nbody { color: red; }", "<div class='page-source'>[[module CSS]]</div>")


class WorkerTests(unittest.TestCase):
    def test_worker_caches_both_inputs_and_completes_job(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with StateStore(root / "state.sqlite3") as store:
                page_row_id, _ = store.observe_manifest_entry(
                    site_id="example",
                    entry=ManifestEntry("article:one", "One", 100, 1),
                    canonical_url="http://example/article:one",
                )
                results = FetchWorker(FakeSite(), store, cache_dir=root / "cache").run_once(limit=1)

                self.assertEqual([result.status for result in results], ["fetched"])
                self.assertEqual(results[0].page_id, 9001)
                self.assertEqual(store.queued_job_count("example"), 0)
                cache_dirs = list((root / "cache" / "example").iterdir())
                self.assertEqual(len(cache_dirs), 1)
                self.assertTrue((cache_dirs[0] / "rendered.html").exists())
                self.assertTrue((cache_dirs[0] / "source.ftml").exists())
                self.assertTrue((cache_dirs[0] / "record.json").exists())

    def test_failed_fetch_releases_job_for_retry(self):
        class BrokenSite(FakeSite):
            def fetch_source(self, page_id: int) -> SourcePage:
                raise RuntimeError("source unavailable")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with StateStore(root / "state.sqlite3") as store:
                store.observe_manifest_entry(
                    site_id="example",
                    entry=ManifestEntry("article:one", "One", 100, 1),
                    canonical_url="http://example/article:one",
                )
                results = FetchWorker(BrokenSite(), store, cache_dir=root / "cache", retry_backoff_seconds=1).run_once(limit=1)

                self.assertEqual(results[0].status, "failed")
                self.assertEqual(store.queued_job_count("example"), 1)

    def test_dynamic_page_gets_ttl_and_is_requeued_when_due(self):
        class DynamicSite(FakeSite):
            def fetch_source(self, page_id: int) -> SourcePage:
                return SourcePage(page_id, '[[module ListPages category="*"]]', "<div class='page-source'></div>")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with StateStore(root / "state.sqlite3") as store:
                page_row_id, _ = store.observe_manifest_entry(
                    site_id="example",
                    entry=ManifestEntry("article:one", "One", 100, 1),
                    canonical_url="http://example/article:one",
                )
                worker = FetchWorker(
                    DynamicSite(),
                    store,
                    cache_dir=root / "cache",
                    dynamic_ttls={"dynamic-listpages": 10, "unknown": 20},
                )
                self.assertEqual(worker.run_once(limit=1)[0].status, "fetched")
                state = store.page_state(page_row_id)
                self.assertEqual(state["dynamic_class"], "dynamic-listpages")
                self.assertIsNotNone(state["next_dynamic_fetch_at"])
                scheduled = store.schedule_due_dynamic(
                    ttl_by_class={"dynamic-listpages": 10, "unknown": 20},
                    now=int(state["next_dynamic_fetch_at"]) + 1,
                )
                self.assertEqual(scheduled, 1)
                self.assertEqual(store.queued_job_count("example"), 1)
