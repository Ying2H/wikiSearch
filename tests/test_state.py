import tempfile
import unittest
import json
from pathlib import Path

from search_sync.models import ManifestEntry
from search_sync.sync.state import StateStore


def entry(updated: int, revisions: int = 1, fullname: str = "article:one") -> ManifestEntry:
    return ManifestEntry(fullname, fullname.rsplit(":", 1)[-1], updated, revisions)


class StateTests(unittest.TestCase):
    def test_observation_and_enqueue_are_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with StateStore(Path(temp_dir) / "state.sqlite3") as store:
                page_id, changed = store.observe_manifest_entry(
                    site_id="wymbot",
                    entry=entry(100),
                    canonical_url="http://wymbot.wikidot.com/article:one",
                    inventory_id="scan-1",
                )
                self.assertTrue(changed)
                self.assertEqual(store.page_count("wymbot"), 1)
                self.assertEqual(store.queued_job_count("wymbot"), 1)

                same_id, changed = store.observe_manifest_entry(
                    site_id="wymbot",
                    entry=entry(100),
                    canonical_url="http://wymbot.wikidot.com/article:one",
                    inventory_id="scan-2",
                )
                self.assertEqual(same_id, page_id)
                self.assertFalse(changed)
                self.assertEqual(store.queued_job_count("wymbot"), 1)

                _, changed = store.observe_manifest_entry(
                    site_id="wymbot",
                    entry=entry(101, 2),
                    canonical_url="http://wymbot.wikidot.com/article:one",
                    inventory_id="scan-3",
                )
                self.assertTrue(changed)
                jobs = store.queued_jobs(limit=10, now=10**12)
                self.assertEqual(len(jobs), 1)
                self.assertEqual(jobs[0]["target_updated_at"], 101)
                self.assertIn("manifest_changed", jobs[0]["reasons"])

    def test_stale_fetch_does_not_advance_fetched_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with StateStore(Path(temp_dir) / "state.sqlite3") as store:
                page_id, _ = store.observe_manifest_entry(
                    site_id="wymbot",
                    entry=entry(200),
                    canonical_url="http://wymbot.wikidot.com/article:one",
                )
                self.assertFalse(store.mark_fetched(page_id, target=(199, 1), content_hash="old"))
                self.assertEqual(store.queued_job_count("wymbot"), 1)
                self.assertTrue(store.mark_fetched(page_id, target=(200, 1), content_hash="new"))
                self.assertEqual(store.queued_job_count("wymbot"), 0)

    def test_dependency_change_enqueues_dependents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with StateStore(Path(temp_dir) / "state.sqlite3") as store:
                dependent_id, _ = store.observe_manifest_entry(
                    site_id="wymbot",
                    entry=entry(100, fullname="article:one"),
                    canonical_url="http://wymbot.wikidot.com/article:one",
                )
                target_id, _ = store.observe_manifest_entry(
                    site_id="wymbot",
                    entry=entry(100, fullname="component:nav"),
                    canonical_url="http://wymbot.wikidot.com/component:nav",
                )
                store.mark_fetched(dependent_id, target=(100, 1), content_hash="dependent", dynamic_class="static")
                store.mark_fetched(target_id, target=(100, 1), content_hash="target", dynamic_class="static")
                store.replace_dependencies(site_id="wymbot", from_page_row_id=dependent_id, targets=["component:nav"])

                store.observe_manifest_entry(
                    site_id="wymbot",
                    entry=entry(101, 2, fullname="component:nav"),
                    canonical_url="http://wymbot.wikidot.com/component:nav",
                )

                jobs = store.queued_jobs(limit=10, now=10**12)
                self.assertEqual(len(jobs), 2)
                self.assertIn("dependency_changed", {reason for job in jobs for reason in json.loads(job["reasons"])})
