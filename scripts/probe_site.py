from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from search_sync.crawler.http import HttpClient
from search_sync.crawler.wikidot import WikidotSite


def main() -> int:
    parser = argparse.ArgumentParser(description="只读探测一个 Wikidot 站点")
    parser.add_argument("--base-url", default="https://wymbot.wikidot.com")
    parser.add_argument("--manifest-path", default="/pagelist")
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--min-interval", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--check-amc", action="store_true")
    args = parser.parse_args()

    client = HttpClient(timeout=args.timeout, min_interval=args.min_interval)
    site = WikidotSite(args.base_url, client=client, manifest_path=args.manifest_path)
    manifest_pages = []
    cursor = None
    entries = []
    for _ in range(max(1, args.max_pages)):
        page = site.read_manifest_page(cursor)
        entries.extend(page.entries)
        manifest_pages.append(
            {
                "url": page.url,
                "page_number": page.page_number,
                "total_pages": page.total_pages,
                "entry_count": len(page.entries),
                "next_cursor": page.next_cursor,
            }
        )
        if not page.next_cursor:
            break
        cursor = page.next_cursor

    sample = next((entry for entry in entries if entry.fullname != "pagelist"), entries[0])
    rendered = site.fetch_rendered(sample.fullname)
    source = site.fetch_source(rendered.page_id)
    result = {
        "base_url": args.base_url,
        "manifest_pages": manifest_pages,
        "manifest_entry_count": len(entries),
        "sample": {
            "fullname": sample.fullname,
            "title": sample.title,
            "page_id": rendered.page_id,
            "source_status": source.status,
            "source_chars": len(source.source),
            "source_preview": source.source[:240],
        },
        "amc": None,
        "requests": client.metrics.as_dict(),
    }
    if args.check_amc:
        amc = site.read_amc_manifest_page()
        result["amc"] = {
            "entry_count": len(amc.entries),
            "page_number": amc.page_number,
            "total_pages": amc.total_pages,
        }
        result["requests"] = client.metrics.as_dict()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
