"""Explain search-document changes without comparing Orama's internal index nodes."""
from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Any


def _documents(path: Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = list(payload["database"]["docs"]["docs"].values())
    by_url = {document["url"]: document for document in documents}
    if len(by_url) != len(documents):
        raise ValueError(f"duplicate document URLs: {path}")
    return by_url


def describe_changes(previous: Path, current: Path) -> dict[str, Any]:
    before = _documents(previous) if previous.is_file() else {}
    after = _documents(current)
    changed = []
    for url in sorted(before.keys() & after.keys()):
        fields = sorted(key for key in before[url].keys() | after[url].keys() if before[url].get(key) != after[url].get(key))
        if not fields:
            continue
        item = {"url": url, "fullname": after[url].get("fullname", ""), "fields": fields}
        if "content" in fields:
            lines = list(difflib.unified_diff(before[url].get("content", "").splitlines(), after[url].get("content", "").splitlines(), n=2, lineterm=""))
            item["content_diff"] = lines[:40]
            item["diff_truncated"] = len(lines) > 40
        for field in fields:
            if field != "content":
                item[field] = {"before": before[url].get(field), "after": after[url].get(field)}
        changed.append(item)
    return {
        "before_count": len(before), "after_count": len(after),
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
        "changed": changed,
    }
