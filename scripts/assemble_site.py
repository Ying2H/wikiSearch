from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from search_sync.publish import PublishError, assemble_site


def main() -> int:
    parser = argparse.ArgumentParser(description="组合静态搜索页和 Orama 资源")
    parser.add_argument("--web-dir", default="web")
    parser.add_argument("--orama-dir", required=True)
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--build-config-hash", default=None)
    parser.add_argument("--output-dir", default="data/publish/site")
    args = parser.parse_args()
    try:
        site = assemble_site(
            web_dir=args.web_dir,
            orama_dir=args.orama_dir,
            output_dir=args.output_dir,
            manifest_path=args.manifest,
            build_config_hash=args.build_config_hash,
        )
    except PublishError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "output_dir": str(site.output_dir),
                "record_count": site.record_count,
                "corpus_generation": site.corpus_generation,
                "manifest_hash": site.manifest_hash,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
