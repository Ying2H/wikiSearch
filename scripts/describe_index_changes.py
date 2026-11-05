from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from search_sync.publish_diff import describe_changes


def main() -> None:
    parser = argparse.ArgumentParser(description="显示新旧 Orama 索引的页面和字段差异")
    parser.add_argument("--previous", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(describe_changes(args.previous, args.current), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
