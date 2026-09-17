from __future__ import annotations

import html as html_lib
import re
from html.parser import HTMLParser

from search_sync.models import ManifestEntry, ManifestPage, SourcePage


_TIME_RE = re.compile(r"(?:^|\s)time_(\d+)(?:\s|$)")
_PAGER_RE = re.compile(r"page\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE)


def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
    values = dict(attrs).get("class") or ""
    return set(values.split())


class _ManifestParser(HTMLParser):
    FIELD_NAMES = {"search-fullname", "search-title", "search-updated", "search-revisions"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.row: dict[str, object] | None = None
        self.row_depth: int | None = None
        self.field: str | None = None
        self.field_depth: int | None = None
        self.field_text: list[str] = []
        self.rows: list[ManifestEntry] = []

    def _finish_field(self) -> None:
        if self.row is None or self.field is None:
            self.field = None
            self.field_depth = None
            self.field_text = []
            return
        value = "".join(self.field_text).strip()
        self.row[self.field] = value
        self.field = None
        self.field_depth = None
        self.field_text = []

    def _finish_row(self) -> None:
        self._finish_field()
        if self.row is not None and "search-fullname" in self.row:
            fullname = str(self.row.get("search-fullname") or "").strip()
            title = str(self.row.get("search-title") or "").strip()
            raw_updated = str(self.row.get("search-updated") or "").strip()
            raw_revisions = str(self.row.get("search-revisions") or "").strip()
            updated = self.row.get("updated_at")
            if not isinstance(updated, int):
                updated = None
            try:
                revisions = int(raw_revisions) if raw_revisions else None
            except ValueError:
                revisions = None
            self.rows.append(
                ManifestEntry(
                    fullname=fullname,
                    title=title,
                    updated_at=updated,
                    revisions=revisions,
                    raw_updated=raw_updated,
                )
            )
        self.row = None
        self.row_depth = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        depth = len(self.stack) + 1
        class_set = _classes(attrs)
        if tag == "div" and "search-manifest-row" in class_set:
            if self.row is not None:
                self._finish_row()
            self.row = {}
            self.row_depth = depth
        if self.row is not None:
            field = next((name for name in self.FIELD_NAMES if name in class_set), None)
            if field is not None:
                self._finish_field()
                self.field = field
                self.field_depth = depth
                self.field_text = []
            for class_name in class_set:
                match = _TIME_RE.search(class_name)
                if match:
                    self.row["updated_at"] = int(match.group(1))
        self.stack.append(tag)

    def handle_data(self, data: str) -> None:
        if self.field is not None:
            self.field_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        depth = len(self.stack)
        if self.field_depth == depth:
            self._finish_field()
        if self.row_depth == depth and tag == "div":
            self._finish_row()
        if self.stack:
            self.stack.pop()

    def close(self) -> None:
        super().close()
        if self.row is not None:
            self._finish_row()


def _parse_pager(source: str) -> tuple[int, int, str | None]:
    match = re.search(r'<div\s+class=["\']pager["\']\s*>(?P<body>.*?)</div>', source, re.IGNORECASE | re.DOTALL)
    if not match:
        return 1, 1, None
    body = match.group("body")
    page_match = _PAGER_RE.search(re.sub(r"<[^>]+>", " ", body))
    page_number = int(page_match.group(1)) if page_match else 1
    total_pages = int(page_match.group(2)) if page_match else 1
    links = re.findall(
        r'<a\b[^>]*href=["\'](?P<href>[^"\']+)["\'][^>]*>(?P<label>.*?)</a>',
        body,
        re.IGNORECASE | re.DOTALL,
    )
    next_cursor: str | None = None
    for href, label in links:
        label_text = re.sub(r"<[^>]+>", " ", html_lib.unescape(label)).strip().lower()
        if "next" in label_text or "»" in label_text or "&raquo;" in label_text:
            next_cursor = html_lib.unescape(href)
            break
    return page_number, total_pages, next_cursor


def parse_manifest_html(source: str, *, url: str = "", amc_escaped: bool = False) -> ManifestPage:
    """解析 HTML 清单或 AMC body；不依赖行顺序或竖线分隔。"""

    normalized = html_lib.unescape(source) if amc_escaped else source
    parser = _ManifestParser()
    parser.feed(normalized)
    parser.close()
    page_number, total_pages, next_cursor = _parse_pager(normalized)
    return ManifestPage(tuple(parser.rows), page_number, total_pages, next_cursor, url)


class _SourceParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.capture_depth: int | None = None
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        depth = len(self.stack) + 1
        class_set = _classes(attrs)
        if tag == "div" and "page-source" in class_set and self.capture_depth is None:
            self.capture_depth = depth
        elif self.capture_depth is not None and depth >= self.capture_depth and tag == "br":
            self.parts.append("\n")
        self.stack.append(tag)

    def handle_data(self, data: str) -> None:
        if self.capture_depth is not None:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        depth = len(self.stack)
        if self.capture_depth == depth:
            self.capture_depth = None
        if self.stack:
            self.stack.pop()


def parse_source_body(body: str, *, page_id: int) -> SourcePage:
    parser = _SourceParser()
    parser.feed(html_lib.unescape(body).replace("\xa0", " "))
    parser.close()
    source = "".join(parser.parts).strip()
    return SourcePage(page_id=page_id, source=source, raw_body=body)
