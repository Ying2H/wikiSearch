from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from search_sync.crawler.wikidot import WikidotSite
from search_sync.extract.content import extract_main_content, stable_record_hash
from search_sync.sync.cache import page_cache_dir, write_text_atomic
from search_sync.sync.classifier import classify_source
from search_sync.sync.state import StateStore


@dataclass(frozen=True)
class JobResult:
    job_id: int
    page_row_id: int
    fullname: str
    status: str
    page_id: int | None = None
    content_hash: str | None = None
    error: str | None = None


class FetchWorker:
    """处理已入队页面；租约和原子缓存使进程中断后可恢复。"""

    def __init__(
        self,
        site: WikidotSite,
        store: StateStore,
        *,
        cache_dir: str | Path,
        retry_backoff_seconds: int = 60,
        dynamic_ttls: dict[str, int] | None = None,
    ) -> None:
        self.site = site
        self.store = store
        self.cache_dir = Path(cache_dir)
        self.retry_backoff_seconds = retry_backoff_seconds
        self.dynamic_ttls = dynamic_ttls or {
            "dynamic-listpages": 900,
            "dynamic-transitive": 900,
            "dynamic-other": 1800,
            "unknown": 3600,
        }

    def _cache_page(self, job: Any, rendered_html: str, source: str, record: dict[str, Any]) -> None:
        page_dir = page_cache_dir(self.cache_dir, str(job["site_id"]), str(job["fullname"]))
        write_text_atomic(page_dir / "rendered.html", rendered_html)
        write_text_atomic(page_dir / "source.ftml", source)
        write_text_atomic(page_dir / "record.json", json.dumps(record, ensure_ascii=False, indent=2) + "\n")

    def process_job(self, job: Any) -> JobResult:
        job_id = int(job["id"])
        page_row_id = int(job["page_row_id"])
        fullname = str(job["fullname"])
        target = (job["target_updated_at"], job["target_revisions"])
        try:
            previous_content_hash = self.store.page_state(page_row_id)["content_hash"]
            rendered = self.site.fetch_rendered(fullname)
            self.store.set_page_id(page_row_id, rendered.page_id)
            source_page = self.site.fetch_source(rendered.page_id)
            classification = classify_source(source_page.source)
            self.store.replace_dependencies(
                site_id=str(job["site_id"]),
                from_page_row_id=page_row_id,
                targets=classification.includes,
            )
            content = extract_main_content(rendered.html)
            record = {
                "url": rendered.url,
                "content": content,
                "language": "zh",
                "meta": {
                    "title": str(job["title"] or ""),
                    "category": str(job["category"] or "_default"),
                    "fullname": fullname,
                },
                "filters": {"page_type": [str(job["category"] or "_default")]},
                "sort": {"updated": str(target[0] or 0)},
            }
            content_hash = stable_record_hash(record)
            source_hash = hashlib.sha256(source_page.source.encode("utf-8")).hexdigest()
            self._cache_page(job, rendered.html, source_page.source, record)
            current = self.store.mark_fetched(
                page_row_id,
                target=target,
                content_hash=content_hash,
                source_hash=source_hash,
                dynamic_class=classification.dynamic_class,
                dynamic_reasons=classification.reasons,
                job_id=job_id,
                dynamic_ttl_seconds=self.dynamic_ttls.get(classification.dynamic_class),
            )
            if current and previous_content_hash != content_hash:
                self.store.enqueue_dependents(site_id=str(job["site_id"]), target_page_row_id=page_row_id)
            return JobResult(
                job_id=job_id,
                page_row_id=page_row_id,
                fullname=fullname,
                status="fetched" if current else "stale",
                page_id=rendered.page_id,
                content_hash=content_hash,
            )
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            self.store.release_job(job_id, error=message, backoff_seconds=self.retry_backoff_seconds)
            return JobResult(job_id, page_row_id, fullname, "failed", error=message)

    def run_once(self, *, limit: int = 10) -> list[JobResult]:
        self.store.recover_expired_leases()
        self.store.schedule_due_dynamic(ttl_by_class=self.dynamic_ttls, limit=limit)
        results: list[JobResult] = []
        for job in self.store.queued_jobs(limit=limit):
            job_id = int(job["id"])
            if not self.store.claim_job(job_id):
                continue
            results.append(self.process_job(job))
        return results
