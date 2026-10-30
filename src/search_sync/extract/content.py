from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Mapping


BLOCK_TAGS = {
    "address",
    "article",
    "blockquote",
    "div",
    "dl",
    "dt",
    "dd",
    "fieldset",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}
SKIP_TAGS = {"iframe", "noscript", "script", "style", "svg"}
SKIP_IDS = {
    "action-area", "footer", "page-info-break", "page-options-container", "side-bar",
    "comments-options-hidden", "comments-options", "new-post-button", "post-options-template",
}
SKIP_CLASSES = {"license-area", "page-options-bottom", "pager"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {key: value or "" for key, value in attrs}


class _MainContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.main_depth: int | None = None
        self.skip_depths: list[int] = []
        self.parts: list[str] = []

    @property
    def skipped(self) -> bool:
        return bool(self.skip_depths)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        depth = len(self.stack) + 1
        values = _attrs(attrs)
        classes = set(values.get("class", "").split())
        if tag == "div" and values.get("id") == "page-content" and self.main_depth is None:
            self.main_depth = depth
        if self.main_depth is not None and not self.skipped:
            forum_control = tag == "a" and "WIKIDOT.modules.Forum" in values.get("onclick", "")
            timestamp = next((item[5:] for item in classes if re.fullmatch(r"time_\d+", item)), None)
            if "odate" in classes and timestamp is not None:
                self.parts.append(datetime.fromtimestamp(int(timestamp), timezone.utc).isoformat())
                self.skip_depths.append(depth)
            elif tag in SKIP_TAGS or values.get("id") in SKIP_IDS or classes & SKIP_CLASSES or forum_control:
                self.skip_depths.append(depth)
            elif tag in BLOCK_TAGS or tag == "br":
                self.parts.append("\n")
        if tag not in VOID_TAGS:
            self.stack.append(tag)
        elif self.skip_depths and self.skip_depths[-1] == depth:
            self.skip_depths.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.main_depth is not None and not self.skipped:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag not in self.stack:
            return
        # Void elements never enter the stack; close matching ancestors on malformed HTML.
        while self.stack and self.stack[-1] != tag:
            self.handle_endtag(self.stack[-1])
        depth = len(self.stack)
        if self.main_depth is not None and not self.skipped and tag in BLOCK_TAGS:
            self.parts.append("\n")
        if self.skip_depths and self.skip_depths[-1] == depth:
            self.skip_depths.pop()
        if self.main_depth == depth:
            self.main_depth = None
        if self.stack:
            self.stack.pop()


def normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    lines = [line.strip() for line in text.split("\n")]
    normalized = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def extract_main_content(rendered_html: str) -> str:
    parser = _MainContentParser()
    parser.feed(rendered_html)
    parser.close()
    return normalize_text("".join(parser.parts))


def stable_record_hash(record: Mapping[str, Any]) -> str:
    payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def search_document(record: Mapping[str, Any]) -> dict[str, str]:
    """The fields actually consumed by builder/build.mjs, excluding crawl metadata."""
    meta = record.get("meta") or {}
    filters = record.get("filters") or {}
    return {
        "id": record["url"],
        "url": record["url"],
        "title": meta.get("title", ""),
        "fullname": meta.get("fullname", ""),
        "category": meta.get("category", ""),
        "page_type": " ".join(filters.get("page_type", [])),
        "content": record["content"],
    }
