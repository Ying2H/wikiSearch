from __future__ import annotations

import argparse
import json

from search_sync.crawler.http import HttpClient
from search_sync.crawler.wikidot import WikidotSite


def _probe(args: argparse.Namespace) -> int:
    client = HttpClient(timeout=args.timeout, min_interval=args.min_interval)
    site = WikidotSite(args.base_url, client=client, manifest_path=args.manifest_path)
    cursor: str | None = None
    pages = []
    for _ in range(args.max_pages):
        page = site.read_manifest_page(cursor)
        pages.append(
            {
                "url": page.url,
                "page_number": page.page_number,
                "total_pages": page.total_pages,
                "entry_count": len(page.entries),
                "next_cursor": page.next_cursor,
                "first": page.entries[0].__dict__ if page.entries else None,
                "last": page.entries[-1].__dict__ if page.entries else None,
            }
        )
        if not page.next_cursor:
            break
        cursor = page.next_cursor
    print(json.dumps({"pages": pages, "requests": client.metrics.as_dict()}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wikidot Pagefind Sync 初始命令行")
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("probe", help="只读探测 ListPages HTML 清单")
    probe.add_argument("--base-url", default="http://wymbot.wikidot.com")
    probe.add_argument("--manifest-path", default="/pagelist")
    probe.add_argument("--max-pages", type=int, default=2)
    probe.add_argument("--timeout", type=float, default=30.0)
    probe.add_argument("--min-interval", type=float, default=2.0)
    probe.set_defaults(handler=_probe)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
