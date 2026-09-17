from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ManifestEntry:
    """ListPages 清单中的一个页面版本观察。"""

    fullname: str
    title: str
    updated_at: int | None
    revisions: int | None
    raw_updated: str = ""

    @property
    def version(self) -> tuple[int | None, int | None]:
        return self.updated_at, self.revisions

    @property
    def category(self) -> str:
        return self.fullname.split(":", 1)[0] if ":" in self.fullname else "_default"


@dataclass(frozen=True)
class ManifestPage:
    entries: tuple[ManifestEntry, ...]
    page_number: int
    total_pages: int
    next_cursor: str | None
    url: str


@dataclass(frozen=True)
class RenderedPage:
    fullname: str
    page_id: int
    url: str
    html: str
    status: int = 200


@dataclass(frozen=True)
class SourcePage:
    page_id: int
    source: str
    raw_body: str
    status: str = "ok"


@dataclass(frozen=True)
class Classification:
    dynamic_class: str
    reasons: tuple[str, ...] = ()
    includes: tuple[str, ...] = ()
    parameterized_includes: tuple[str, ...] = ()


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status: int
    headers: dict[str, str]
    text: str
    elapsed_ms: int


@dataclass
class RequestMetrics:
    total: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)

    def record(self, kind: str) -> None:
        self.total += 1
        self.by_kind[kind] = self.by_kind.get(kind, 0) + 1

    def as_dict(self) -> dict[str, Any]:
        return {"total": self.total, "by_kind": dict(sorted(self.by_kind.items()))}
