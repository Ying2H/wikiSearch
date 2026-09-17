from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass
from urllib.parse import quote, urljoin

from search_sync.crawler.http import HttpClient
from search_sync.crawler.manifest import parse_manifest_html, parse_source_body
from search_sync.models import ManifestPage, RenderedPage, SourcePage


class WikidotResponseError(RuntimeError):
    """Wikidot 返回了不可作为页面/模块使用的响应。"""


@dataclass(frozen=True)
class AmcConfig:
    per_page: int = 100
    category: str = "*"
    order: str = "updated_at desc"


class WikidotSite:
    def __init__(
        self,
        base_url: str,
        *,
        client: HttpClient | None = None,
        manifest_path: str = "/pagelist",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client or HttpClient()
        self.manifest_path = manifest_path

    def page_url(self, fullname: str) -> str:
        # urljoin() treats a Wikidot fullname such as ``egg:xzdc-9`` as a
        # URI scheme when the colon is preserved, so concatenate explicitly.
        return f"{self.base_url}/{quote(fullname, safe=':/-._~')}"

    def read_manifest_page(self, cursor: str | None = None) -> ManifestPage:
        path = cursor or self.manifest_path
        url = urljoin(self.base_url + "/", path.lstrip("/"))
        response = self.client.get(url, kind="manifest")
        if response.status != 200:
            raise WikidotResponseError(f"manifest returned HTTP {response.status}: {url}")
        page = parse_manifest_html(response.text, url=response.url)
        if not page.entries:
            raise WikidotResponseError(f"manifest has no parseable entries: {url}")
        return page

    def read_amc_manifest_page(
        self,
        *,
        offset: int = 0,
        config: AmcConfig | None = None,
    ) -> ManifestPage:
        config = config or AmcConfig()
        token = secrets.token_hex(16)
        module_body = (
            '<div class="search-manifest-row">'
            '<span class="search-fullname">%%fullname%%</span>'
            '<span class="search-title">%%title%%</span>'
            '<span class="search-updated">%%updated_at%%</span>'
            '<span class="search-revisions">%%revisions%%</span>'
            "</div>"
        )
        data = {
            "callbackIndex": 0,
            "wikidot_token7": token,
            "moduleName": "list/ListPagesModule",
            "category": config.category,
            "order": config.order,
            "perPage": config.per_page,
            "separate": "no",
            "offset": offset,
            "module_body": module_body,
        }
        response = self.client.post_form(
            urljoin(self.base_url + "/", "ajax-module-connector.php"),
            data,
            kind="manifest_amc",
            headers={"Cookie": f"wikidot_token7={token}"},
        )
        if response.status != 200:
            raise WikidotResponseError(f"AMC returned HTTP {response.status}")
        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise WikidotResponseError("AMC response is not JSON") from exc
        if payload.get("status") != "ok" or not isinstance(payload.get("body"), str):
            raise WikidotResponseError(f"AMC module status is not ok: {payload.get('status')!r}")
        page = parse_manifest_html(
            payload["body"],
            url=response.url,
            amc_escaped=True,
        )
        if not page.entries:
            raise WikidotResponseError("AMC manifest has no parseable entries")
        return page

    def fetch_rendered(self, fullname: str) -> RenderedPage:
        url = self.page_url(fullname)
        response = self.client.get(url, kind="rendered")
        if response.status != 200:
            raise WikidotResponseError(f"page returned HTTP {response.status}: {url}")
        match = re.search(r"WIKIREQUEST\.info\.pageId\s*=\s*(\d+);", response.text)
        if match is None:
            raise WikidotResponseError(f"page has no page id (possible soft 404): {url}")
        return RenderedPage(
            fullname=fullname,
            page_id=int(match.group(1)),
            url=response.url,
            html=response.text,
            status=response.status,
        )

    def fetch_source(self, page_id: int) -> SourcePage:
        token = secrets.token_hex(16)
        response = self.client.post_form(
            urljoin(self.base_url + "/", "ajax-module-connector.php"),
            {
                "callbackIndex": 0,
                "wikidot_token7": token,
                "moduleName": "viewsource/ViewSourceModule",
                "page_id": page_id,
            },
            kind="source",
            headers={"Cookie": f"wikidot_token7={token}"},
        )
        if response.status != 200:
            raise WikidotResponseError(f"source returned HTTP {response.status}: {page_id}")
        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise WikidotResponseError("source response is not JSON") from exc
        if payload.get("status") != "ok" or not isinstance(payload.get("body"), str):
            raise WikidotResponseError(f"source module status is not ok: {payload.get('status')!r}")
        return parse_source_body(payload["body"], page_id=page_id)
