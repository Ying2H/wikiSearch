from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path


def cache_key(fullname: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", fullname).strip("_") or "page"
    digest = hashlib.sha256(fullname.encode("utf-8")).hexdigest()[:12]
    return f"{safe[:80]}-{digest}"


def site_cache_key(site_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", site_id).strip("_") or "site"


def page_cache_dir(cache_dir: str | Path, site_id: str, fullname: str) -> Path:
    return Path(cache_dir) / site_cache_key(site_id) / cache_key(fullname)


def write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.replace(path)
