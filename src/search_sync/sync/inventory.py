from __future__ import annotations

import uuid
from dataclasses import dataclass

from search_sync.crawler.wikidot import WikidotSite
from search_sync.sync.state import StateStore


@dataclass(frozen=True)
class InventoryScanResult:
    scan_id: int
    inventory_id: str
    pages_read: int
    entries_seen: int
    entries_enqueued: int
    coverage_complete: bool
    watermark: int | None
    next_cursor: str | None


class InventoryScanner:
    """一期全清单扫描器；预算耗尽时保留 incomplete，不推进水位。"""

    def __init__(self, site: WikidotSite, store: StateStore, *, site_id: str) -> None:
        self.site = site
        self.store = store
        self.site_id = site_id

    def scan(self, *, max_pages: int = 100, inventory_id: str | None = None) -> InventoryScanResult:
        inventory_id = inventory_id or f"inventory-{uuid.uuid4().hex}"
        scan_id = self.store.begin_scan(self.site_id, inventory_id=inventory_id)
        cursor: str | None = None
        pages_read = 0
        entries_seen = 0
        entries_enqueued = 0
        timestamps: list[int] = []
        next_cursor: str | None = None
        coverage_complete = False
        error: str | None = None
        try:
            for _ in range(max(1, max_pages)):
                page = self.site.read_manifest_page(cursor)
                pages_read += 1
                entries_seen += len(page.entries)
                next_cursor = page.next_cursor
                for entry in page.entries:
                    if entry.updated_at is not None:
                        timestamps.append(entry.updated_at)
                    _, changed = self.store.observe_manifest_entry(
                        site_id=self.site_id,
                        entry=entry,
                        canonical_url=self.site.page_url(entry.fullname),
                        inventory_id=inventory_id,
                    )
                    entries_enqueued += int(changed)
                if not page.next_cursor:
                    coverage_complete = True
                    next_cursor = None
                    break
                cursor = page.next_cursor
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        watermark = min(timestamps) if coverage_complete and timestamps else None
        self.store.finish_scan(
            scan_id,
            pages_seen=pages_read,
            pages_enqueued=entries_enqueued,
            coverage_complete=coverage_complete,
            watermark=watermark,
            error=error,
        )
        if error:
            raise RuntimeError(error)
        return InventoryScanResult(
            scan_id=scan_id,
            inventory_id=inventory_id,
            pages_read=pages_read,
            entries_seen=entries_seen,
            entries_enqueued=entries_enqueued,
            coverage_complete=coverage_complete,
            watermark=watermark,
            next_cursor=next_cursor,
        )
