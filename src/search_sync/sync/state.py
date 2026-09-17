from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Iterable

from search_sync.models import ManifestEntry


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY,
    site_id TEXT NOT NULL,
    page_id INTEGER,
    fullname TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '_default',
    observed_updated_at INTEGER,
    observed_revisions INTEGER,
    fetched_updated_at INTEGER,
    fetched_revisions INTEGER,
    source_version TEXT,
    status TEXT NOT NULL DEFAULT 'discovered',
    last_seen_inventory TEXT,
    content_hash TEXT,
    source_hash TEXT,
    dynamic_class TEXT NOT NULL DEFAULT 'unknown',
    dynamic_reasons TEXT NOT NULL DEFAULT '[]',
    next_dynamic_fetch_at INTEGER,
    last_dynamic_success INTEGER,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE(site_id, fullname),
    UNIQUE(site_id, page_id)
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY,
    page_row_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    reasons TEXT NOT NULL DEFAULT '[]',
    target_updated_at INTEGER,
    target_revisions INTEGER,
    due_at INTEGER NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    lease_until INTEGER,
    status TEXT NOT NULL DEFAULT 'queued',
    error TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE(page_row_id, status)
);

CREATE TABLE IF NOT EXISTS dependencies (
    from_page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    to_target TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'include',
    resolved_page_id INTEGER REFERENCES pages(id) ON DELETE SET NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    last_checked INTEGER,
    PRIMARY KEY(from_page_id, to_target, kind)
);

CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY,
    site_id TEXT NOT NULL,
    inventory_id TEXT,
    watermark INTEGER,
    overlap_seconds INTEGER NOT NULL DEFAULT 900,
    coverage_complete INTEGER NOT NULL DEFAULT 0,
    pages_seen INTEGER NOT NULL DEFAULT 0,
    pages_enqueued INTEGER NOT NULL DEFAULT 0,
    started_at INTEGER NOT NULL,
    finished_at INTEGER,
    error TEXT
);

CREATE TABLE IF NOT EXISTS builds (
    id INTEGER PRIMARY KEY,
    corpus_generation INTEGER NOT NULL,
    manifest_hash TEXT NOT NULL,
    build_id TEXT,
    status TEXT NOT NULL,
    published_at INTEGER,
    created_at INTEGER NOT NULL
);
"""


def _now() -> int:
    return int(time.time())


class StateStore:
    """SQLite 状态层；清单观察与任务入队在同一事务中提交。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        job_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(jobs)").fetchall()}
        if "error" not in job_columns:
            self.db.execute("ALTER TABLE jobs ADD COLUMN error TEXT")
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> "StateStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _version_values(entry: ManifestEntry) -> tuple[int | None, int | None]:
        return entry.updated_at, entry.revisions

    def observe_manifest_entry(
        self,
        *,
        site_id: str,
        entry: ManifestEntry,
        canonical_url: str,
        inventory_id: str | None = None,
        due_at: int | None = None,
    ) -> tuple[int, bool]:
        now = _now()
        due = due_at if due_at is not None else now
        observed_updated, observed_revisions = self._version_values(entry)
        with self.db:
            row = self.db.execute(
                "SELECT * FROM pages WHERE site_id = ? AND fullname = ?",
                (site_id, entry.fullname),
            ).fetchone()
            if row is None:
                cursor = self.db.execute(
                    """
                    INSERT INTO pages(
                        site_id, fullname, canonical_url, title, category,
                        observed_updated_at, observed_revisions, status,
                        last_seen_inventory, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, 'discovered', ?, ?, ?)
                    """,
                    (
                        site_id,
                        entry.fullname,
                        canonical_url,
                        entry.title,
                        entry.category,
                        observed_updated,
                        observed_revisions,
                        inventory_id,
                        now,
                        now,
                    ),
                )
                page_row_id = int(cursor.lastrowid)
                changed = True
                reasons = ["first_seen"]
            else:
                page_row_id = int(row["id"])
                changed = (
                    row["observed_updated_at"],
                    row["observed_revisions"],
                ) != (observed_updated, observed_revisions)
                reasons = ["manifest_changed"] if changed else []
                self.db.execute(
                    """
                    UPDATE pages
                    SET title = ?, category = ?, canonical_url = ?,
                        observed_updated_at = ?, observed_revisions = ?,
                        last_seen_inventory = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        entry.title,
                        entry.category,
                        canonical_url,
                        observed_updated,
                        observed_revisions,
                        inventory_id,
                        now,
                        page_row_id,
                    ),
                )
            if changed:
                self._enqueue_in_transaction(
                    page_row_id,
                    reasons=reasons,
                    target=(observed_updated, observed_revisions),
                    due_at=due,
                    now=now,
                )
            self._resolve_dependency_target_in_transaction(
                site_id=site_id,
                fullname=entry.fullname,
                target_page_row_id=page_row_id,
            )
            if changed:
                self._enqueue_dependents_in_transaction(
                    site_id=site_id,
                    target_page_row_id=page_row_id,
                    now=now,
                )
        return page_row_id, changed

    def _resolve_dependency_target_in_transaction(
        self,
        *,
        site_id: str,
        fullname: str,
        target_page_row_id: int,
    ) -> None:
        self.db.execute(
            """
            UPDATE dependencies SET resolved_page_id = ?, resolved = 1, last_checked = ?
            WHERE to_target = ? AND from_page_id IN (
                SELECT id FROM pages WHERE site_id = ?
            )
            """,
            (target_page_row_id, _now(), fullname, site_id),
        )

    def _enqueue_dependents_in_transaction(
        self,
        *,
        site_id: str,
        target_page_row_id: int,
        now: int,
    ) -> None:
        rows = self.db.execute(
            """
            SELECT DISTINCT pages.id, pages.observed_updated_at, pages.observed_revisions
            FROM dependencies
            JOIN pages ON pages.id = dependencies.from_page_id
            WHERE pages.site_id = ? AND dependencies.resolved_page_id = ?
            """,
            (site_id, target_page_row_id),
        ).fetchall()
        for row in rows:
            self._enqueue_in_transaction(
                int(row["id"]),
                reasons=["dependency_changed"],
                target=(row["observed_updated_at"], row["observed_revisions"]),
                due_at=now,
                now=now,
            )

    def enqueue_dependents(self, *, site_id: str, target_page_row_id: int, reason: str = "dependency_changed") -> int:
        now = _now()
        before = self.queued_job_count(site_id)
        with self.db:
            rows = self.db.execute(
                """
                SELECT DISTINCT pages.id, pages.observed_updated_at, pages.observed_revisions
                FROM dependencies
                JOIN pages ON pages.id = dependencies.from_page_id
                WHERE pages.site_id = ? AND dependencies.resolved_page_id = ?
                """,
                (site_id, target_page_row_id),
            ).fetchall()
            for row in rows:
                self._enqueue_in_transaction(
                    int(row["id"]),
                    reasons=[reason],
                    target=(row["observed_updated_at"], row["observed_revisions"]),
                    due_at=now,
                    now=now,
                )
        return max(0, self.queued_job_count(site_id) - before)

    def replace_dependencies(self, *, site_id: str, from_page_row_id: int, targets: Iterable[str]) -> None:
        now = _now()
        unique_targets = sorted({target.strip() for target in targets if target.strip()})
        with self.db:
            self.db.execute("DELETE FROM dependencies WHERE from_page_id = ?", (from_page_row_id,))
            for target in unique_targets:
                target_row = self.db.execute(
                    "SELECT id FROM pages WHERE site_id = ? AND fullname = ?",
                    (site_id, target),
                ).fetchone()
                resolved_page_id = int(target_row["id"]) if target_row else None
                self.db.execute(
                    """
                    INSERT INTO dependencies(
                        from_page_id, to_target, kind, resolved_page_id, resolved, last_checked
                    ) VALUES(?, ?, 'include', ?, ?, ?)
                    """,
                    (from_page_row_id, target, resolved_page_id, int(target_row is not None), now),
                )

    def schedule_due_dynamic(
        self,
        *,
        ttl_by_class: dict[str, int],
        now: int | None = None,
        limit: int = 100,
    ) -> int:
        now = _now() if now is None else now
        count = 0
        with self.db:
            rows = self.db.execute(
                """
                SELECT id, dynamic_class, observed_updated_at, observed_revisions
                FROM pages
                WHERE status = 'active' AND dynamic_class <> 'static'
                  AND next_dynamic_fetch_at IS NOT NULL
                  AND next_dynamic_fetch_at <= ?
                ORDER BY next_dynamic_fetch_at, id LIMIT ?
                """,
                (now, limit),
            ).fetchall()
            for row in rows:
                dynamic_class = str(row["dynamic_class"])
                ttl = max(1, int(ttl_by_class.get(dynamic_class, ttl_by_class.get("unknown", 3600))))
                self._enqueue_in_transaction(
                    int(row["id"]),
                    reasons=["dynamic_ttl"],
                    target=(row["observed_updated_at"], row["observed_revisions"]),
                    due_at=now,
                    now=now,
                )
                self.db.execute(
                    "UPDATE pages SET next_dynamic_fetch_at = ?, updated_at = ? WHERE id = ?",
                    (now + ttl, now, int(row["id"])),
                )
                count += 1
        return count

    def page_state(self, page_row_id: int) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM pages WHERE id = ?", (page_row_id,)).fetchone()
        if row is None:
            raise KeyError(f"unknown page row: {page_row_id}")
        return row

    def active_pages(self, site_id: str) -> list[sqlite3.Row]:
        return list(
            self.db.execute(
                """
                SELECT * FROM pages
                WHERE site_id = ? AND status = 'active' AND content_hash IS NOT NULL
                ORDER BY id
                """,
                (site_id,),
            ).fetchall()
        )

    def next_corpus_generation(self) -> int:
        row = self.db.execute("SELECT COALESCE(MAX(corpus_generation), 0) + 1 AS next FROM builds").fetchone()
        return int(row["next"])

    def record_build(
        self,
        *,
        corpus_generation: int,
        manifest_hash: str,
        status: str,
        build_id: str | None = None,
        published_at: int | None = None,
    ) -> int:
        cursor = self.db.execute(
            """
            INSERT INTO builds(
                corpus_generation, manifest_hash, build_id, status, published_at, created_at
            ) VALUES(?, ?, ?, ?, ?, ?)
            """,
            (corpus_generation, manifest_hash, build_id, status, published_at, _now()),
        )
        self.db.commit()
        return int(cursor.lastrowid)

    def begin_scan(self, site_id: str, *, inventory_id: str, overlap_seconds: int = 900) -> int:
        cursor = self.db.execute(
            """
            INSERT INTO scans(site_id, inventory_id, overlap_seconds, started_at)
            VALUES(?, ?, ?, ?)
            """,
            (site_id, inventory_id, overlap_seconds, _now()),
        )
        self.db.commit()
        return int(cursor.lastrowid)

    def finish_scan(
        self,
        scan_id: int,
        *,
        pages_seen: int,
        pages_enqueued: int,
        coverage_complete: bool,
        watermark: int | None,
        error: str | None = None,
    ) -> None:
        with self.db:
            self.db.execute(
                """
                UPDATE scans SET pages_seen = ?, pages_enqueued = ?,
                    coverage_complete = ?, watermark = ?, finished_at = ?, error = ?
                WHERE id = ?
                """,
                (
                    pages_seen,
                    pages_enqueued,
                    int(coverage_complete),
                    watermark,
                    _now(),
                    error,
                    scan_id,
                ),
            )

    def _enqueue_in_transaction(
        self,
        page_row_id: int,
        *,
        reasons: Iterable[str],
        target: tuple[int | None, int | None],
        due_at: int,
        now: int,
    ) -> None:
        reason_set = set(reasons)
        existing = self.db.execute(
            "SELECT id, reasons, due_at FROM jobs WHERE page_row_id = ? AND status = 'queued'",
            (page_row_id,),
        ).fetchone()
        if existing is None:
            self.db.execute(
                """
                INSERT INTO jobs(
                    page_row_id, reasons, target_updated_at, target_revisions,
                    due_at, status, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, 'queued', ?, ?)
                """,
                (
                    page_row_id,
                    json.dumps(sorted(reason_set), ensure_ascii=False),
                    target[0],
                    target[1],
                    due_at,
                    now,
                    now,
                ),
            )
            return
        old_reasons = set(json.loads(existing["reasons"] or "[]"))
        old_reasons.update(reason_set)
        self.db.execute(
            """
            UPDATE jobs
            SET reasons = ?, target_updated_at = ?, target_revisions = ?,
                due_at = MIN(due_at, ?), updated_at = ?
            WHERE id = ?
            """,
            (
                json.dumps(sorted(old_reasons), ensure_ascii=False),
                target[0],
                target[1],
                due_at,
                now,
                int(existing["id"]),
            ),
        )

    def enqueue_job(
        self,
        page_row_id: int,
        *,
        reason: str,
        target: tuple[int | None, int | None] = (None, None),
        due_at: int | None = None,
    ) -> None:
        now = _now()
        with self.db:
            self._enqueue_in_transaction(
                page_row_id,
                reasons=[reason],
                target=target,
                due_at=due_at if due_at is not None else now,
                now=now,
            )

    def queued_jobs(self, *, limit: int = 100, now: int | None = None) -> list[sqlite3.Row]:
        now = _now() if now is None else now
        return list(
            self.db.execute(
                """
            SELECT jobs.*, pages.site_id, pages.page_id, pages.fullname,
                       pages.canonical_url, pages.title, pages.category,
                       pages.observed_updated_at, pages.observed_revisions
                FROM jobs JOIN pages ON pages.id = jobs.page_row_id
                WHERE jobs.status = 'queued' AND jobs.due_at <= ?
                ORDER BY jobs.due_at, jobs.id LIMIT ?
                """,
                (now, limit),
            ).fetchall()
        )

    def mark_fetched(
        self,
        page_row_id: int,
        *,
        target: tuple[int | None, int | None],
        content_hash: str,
        source_hash: str | None = None,
        dynamic_class: str | None = None,
        dynamic_reasons: Iterable[str] = (),
        job_id: int | None = None,
        dynamic_ttl_seconds: int | None = None,
    ) -> bool:
        now = _now()
        with self.db:
            row = self.db.execute(
                "SELECT observed_updated_at, observed_revisions FROM pages WHERE id = ?",
                (page_row_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown page row: {page_row_id}")
            is_current = (row["observed_updated_at"], row["observed_revisions"]) == target
            if not is_current:
                return False
            values = [
                target[0],
                target[1],
                content_hash,
                source_hash,
                dynamic_class,
                json.dumps(list(dynamic_reasons), ensure_ascii=False),
                now,
                page_row_id,
            ]
            if dynamic_class is None:
                self.db.execute(
                    """
                    UPDATE pages SET fetched_updated_at = ?, fetched_revisions = ?,
                        content_hash = ?, source_hash = COALESCE(?, source_hash),
                        dynamic_class = COALESCE(?, dynamic_class), dynamic_reasons = ?,
                        status = 'active', updated_at = ? WHERE id = ?
                    """,
                    values,
                )
            else:
                next_dynamic = None if dynamic_class == "static" else now + max(1, dynamic_ttl_seconds or 3600)
                last_dynamic = now if dynamic_class != "static" else None
                self.db.execute(
                    """
                    UPDATE pages SET fetched_updated_at = ?, fetched_revisions = ?,
                        content_hash = ?, source_hash = COALESCE(?, source_hash),
                        dynamic_class = ?, dynamic_reasons = ?, status = 'active',
                        next_dynamic_fetch_at = ?, last_dynamic_success = COALESCE(?, last_dynamic_success),
                        updated_at = ? WHERE id = ?
                    """,
                    [
                        target[0],
                        target[1],
                        content_hash,
                        source_hash,
                        dynamic_class,
                        json.dumps(list(dynamic_reasons), ensure_ascii=False),
                        next_dynamic,
                        last_dynamic,
                        now,
                        page_row_id,
                    ],
                )
            if job_id is None:
                self.db.execute(
                    "DELETE FROM jobs WHERE page_row_id = ? AND status IN ('queued', 'leased')",
                    (page_row_id,),
                )
            else:
                self.db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return True

    def claim_job(self, job_id: int, *, lease_seconds: int = 600, now: int | None = None) -> bool:
        now = _now() if now is None else now
        with self.db:
            cursor = self.db.execute(
                """
                UPDATE jobs SET status = 'leased', lease_until = ?,
                    attempts = attempts + 1, updated_at = ?
                WHERE id = ? AND status = 'queued' AND due_at <= ?
                """,
                (now + lease_seconds, now, job_id, now),
            )
        return cursor.rowcount == 1

    def release_job(self, job_id: int, *, error: str, backoff_seconds: int = 60) -> None:
        now = _now()
        with self.db:
            self.db.execute(
                """
                UPDATE jobs SET status = 'queued', lease_until = NULL,
                    due_at = ?, error = ?, updated_at = ?
                WHERE id = ? AND status = 'leased'
                """,
                (now + max(1, backoff_seconds), error[:1000], now, job_id),
            )

    def recover_expired_leases(self, *, now: int | None = None) -> int:
        now = _now() if now is None else now
        with self.db:
            cursor = self.db.execute(
                """
                UPDATE jobs SET status = 'queued', lease_until = NULL,
                    due_at = MIN(due_at, ?), updated_at = ?
                WHERE status = 'leased' AND lease_until IS NOT NULL AND lease_until <= ?
                """,
                (now, now, now),
            )
        return cursor.rowcount

    def set_page_id(self, page_row_id: int, page_id: int) -> None:
        with self.db:
            self.db.execute("UPDATE pages SET page_id = ?, updated_at = ? WHERE id = ?", (page_id, _now(), page_row_id))

    def page_count(self, site_id: str) -> int:
        row = self.db.execute("SELECT COUNT(*) AS count FROM pages WHERE site_id = ?", (site_id,)).fetchone()
        return int(row["count"])

    def queued_job_count(self, site_id: str) -> int:
        row = self.db.execute(
            """
            SELECT COUNT(*) AS count FROM jobs
            JOIN pages ON pages.id = jobs.page_row_id
            WHERE pages.site_id = ? AND jobs.status = 'queued'
            """,
            (site_id,),
        ).fetchone()
        return int(row["count"])
