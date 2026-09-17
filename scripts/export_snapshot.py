from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from search_sync.sync.snapshot import RecordSnapshotter, SnapshotError
from search_sync.sync.state import StateStore


def main() -> int:
    parser = argparse.ArgumentParser(description="从已有 SQLite 状态和缓存导出静态搜索输入快照")
    parser.add_argument("--db", default="data/state.sqlite3")
    parser.add_argument("--cache-dir", default="data/cache")
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--output-dir", default="data/build-input")
    args = parser.parse_args()
    try:
        with StateStore(args.db) as store:
            snapshot = RecordSnapshotter(store, cache_dir=args.cache_dir).export(
                site_id=args.site_id,
                output_dir=args.output_dir,
            )
    except SnapshotError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "site_id": snapshot.site_id,
                "generation": snapshot.generation,
                "count": snapshot.count,
                "excluded_count": snapshot.excluded_count,
                "manifest_hash": snapshot.manifest_hash,
                "output_dir": str(snapshot.output_dir),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
