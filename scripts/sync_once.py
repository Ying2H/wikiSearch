from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from search_sync.crawler.http import HttpClient
from search_sync.crawler.wikidot import WikidotSite
from search_sync.sync.inventory import InventoryScanner
from search_sync.sync.snapshot import RecordSnapshotter, SnapshotError
from search_sync.sync.state import StateStore
from search_sync.sync.worker import FetchWorker


def main() -> int:
    parser = argparse.ArgumentParser(description="执行一轮 Wikidot 清单扫描、抓取和可选快照")
    parser.add_argument("--base-url", default="http://wymbot.wikidot.com")
    parser.add_argument("--manifest-path", default="/pagelist")
    parser.add_argument("--site-id", default=None)
    parser.add_argument("--db", default="data/state.sqlite3")
    parser.add_argument("--cache-dir", default="data/cache")
    parser.add_argument("--snapshot-dir", default=None)
    parser.add_argument("--scan-pages", type=int, default=1)
    parser.add_argument("--worker-limit", type=int, default=10)
    parser.add_argument("--progress", action="store_true", help="逐页输出 worker 进度到 stderr")
    parser.add_argument("--skip-scan", action="store_true", help="只处理已有 SQLite 队列，不访问清单")
    parser.add_argument("--min-interval", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    site_id = args.site_id or urlparse(args.base_url).netloc
    client = HttpClient(timeout=args.timeout, min_interval=args.min_interval)
    site = WikidotSite(args.base_url, client=client, manifest_path=args.manifest_path)
    output: dict[str, object] = {"site_id": site_id}
    with StateStore(args.db) as store:
        if args.skip_scan:
            output["scan"] = {"skipped": True}
        else:
            scan = InventoryScanner(site, store, site_id=site_id).scan(max_pages=args.scan_pages)
            output["scan"] = {
                "pages_read": scan.pages_read,
                "entries_seen": scan.entries_seen,
                "entries_enqueued": scan.entries_enqueued,
                "coverage_complete": scan.coverage_complete,
                "watermark": scan.watermark,
                "next_cursor": scan.next_cursor,
            }
        results = []
        if args.worker_limit > 0:
            def report_progress(result, index, total):
                print(
                    json.dumps(
                        {
                            "worker": f"{index}/{total}",
                            "fullname": result.fullname,
                            "status": result.status,
                            "page_id": result.page_id,
                            "error": result.error,
                        },
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                    flush=True,
                )

            results = FetchWorker(site, store, cache_dir=args.cache_dir).run_once(
                limit=args.worker_limit,
                on_result=report_progress if args.progress else None,
            )
        output["jobs"] = [
            {"fullname": result.fullname, "status": result.status, "page_id": result.page_id, "error": result.error}
            for result in results
        ]
        if args.snapshot_dir:
            try:
                snapshot = RecordSnapshotter(store, cache_dir=args.cache_dir).export(
                    site_id=site_id, output_dir=args.snapshot_dir
                )
                output["snapshot"] = {
                    "count": snapshot.count,
                    "excluded_count": snapshot.excluded_count,
                    "generation": snapshot.generation,
                    "manifest_hash": snapshot.manifest_hash,
                    "output_dir": str(snapshot.output_dir),
                }
            except SnapshotError as exc:
                output["snapshot_error"] = str(exc)
                print(json.dumps(output, ensure_ascii=False, indent=2))
                return 2
    output["requests"] = client.metrics.as_dict()
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
