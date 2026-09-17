from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_sync.extract.content import stable_record_hash
from search_sync.sync.cache import page_cache_dir
from search_sync.sync.state import StateStore


class SnapshotError(RuntimeError):
    """活动页面无法形成一致的本地索引输入快照。"""


@dataclass(frozen=True)
class RecordSnapshot:
    site_id: str
    generation: int
    count: int
    excluded_count: int
    manifest_hash: str
    output_dir: Path


def _publish_directory(staged: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    backup = output.parent / f"{output.name}.previous-{uuid.uuid4().hex}"
    moved_previous = False
    try:
        if output.exists():
            output.rename(backup)
            moved_previous = True
        staged.rename(output)
        if moved_previous:
            shutil.rmtree(backup)
    except Exception:
        if moved_previous and not output.exists() and backup.exists():
            backup.rename(output)
        raise


class RecordSnapshotter:
    """从 active 页面和已校验缓存生成全量、可发布的 Pagefind 输入目录。"""

    def __init__(self, store: StateStore, *, cache_dir: str | Path) -> None:
        self.store = store
        self.cache_dir = Path(cache_dir)

    def export(self, *, site_id: str, output_dir: str | Path) -> RecordSnapshot:
        pending = self.store.pending_active_pages(site_id)
        if pending:
            names = ", ".join(str(row["fullname"]) for row in pending[:10])
            suffix = "..." if len(pending) > 10 else ""
            raise SnapshotError(f"active pages have pending jobs: {names}{suffix}")
        rows = self.store.active_pages(site_id)
        if not rows:
            raise SnapshotError(f"no active records for site: {site_id}")
        generation = self.store.next_corpus_generation()
        output = Path(output_dir)
        staged = output.parent / f"{output.name}.staged-{uuid.uuid4().hex}"
        manifest_entries: list[dict[str, Any]] = []
        excluded_entries: list[dict[str, Any]] = []
        try:
            staged.mkdir(parents=True, exist_ok=False)
            records_dir = staged / "records"
            records_dir.mkdir()
            for row in rows:
                observed = (row["observed_updated_at"], row["observed_revisions"])
                fetched = (row["fetched_updated_at"], row["fetched_revisions"])
                if observed != fetched:
                    raise SnapshotError(f"page is stale: {row['fullname']}")
                record_path = page_cache_dir(self.cache_dir, site_id, str(row["fullname"])) / "record.json"
                try:
                    record = json.loads(record_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise SnapshotError(f"invalid cache for {row['fullname']}: {exc}") from exc
                if stable_record_hash(record) != row["content_hash"]:
                    raise SnapshotError(f"cache hash mismatch: {row['fullname']}")
                if not str(record.get("content") or "").strip():
                    excluded_entries.append(
                        {
                            "page_row_id": int(row["id"]),
                            "fullname": row["fullname"],
                            "reason": "empty-content",
                        }
                    )
                    continue
                destination = records_dir / f"{len(manifest_entries) + 1:08d}" / "record.json"
                destination.parent.mkdir(parents=True)
                shutil.copyfile(record_path, destination)
                manifest_entries.append(
                    {
                        "page_row_id": int(row["id"]),
                        "fullname": row["fullname"],
                        "url": record.get("url", row["canonical_url"]),
                        "content_hash": row["content_hash"],
                    }
                )
            manifest_payload = {
                "site_id": site_id,
                "corpus_generation": generation,
                "active_count": len(rows),
                "count": len(manifest_entries),
                "excluded": excluded_entries,
                "records": manifest_entries,
            }
            hash_payload = dict(manifest_payload)
            hash_payload.pop("corpus_generation", None)
            manifest_hash = hashlib.sha256(
                json.dumps(hash_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            manifest_payload["manifest_hash"] = manifest_hash
            (staged / "manifest.json").write_text(
                json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            _publish_directory(staged, output)
            self.store.record_build(
                corpus_generation=generation,
                manifest_hash=manifest_hash,
                build_id=f"snapshot-{uuid.uuid4().hex}",
                status="snapshot",
            )
        except Exception:
            if staged.exists():
                shutil.rmtree(staged)
            raise
        return RecordSnapshot(site_id, generation, len(manifest_entries), len(excluded_entries), manifest_hash, output)
