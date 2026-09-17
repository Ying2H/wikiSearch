from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import Message
from typing import Mapping

from search_sync.models import HttpResponse, RequestMetrics


class RequestError(RuntimeError):
    """请求无法完成，或响应无法读取。"""


@dataclass
class RateLimiter:
    min_interval: float = 2.0
    clock: callable = time.monotonic
    sleeper: callable = time.sleep
    _last_request: float | None = None

    def wait(self) -> None:
        if self._last_request is not None and self.min_interval > 0:
            remaining = self.min_interval - (self.clock() - self._last_request)
            if remaining > 0:
                self.sleeper(remaining)
        self._last_request = self.clock()


class HttpClient:
    """所有外部请求的可计数、可限速入口。"""

    def __init__(
        self,
        *,
        timeout: float = 30.0,
        min_interval: float = 2.0,
        user_agent: str = "wikidot-pagefind-sync/0.1 (+read-only)",
        limiter: RateLimiter | None = None,
    ) -> None:
        self.timeout = timeout
        self.user_agent = user_agent
        self.limiter = limiter or RateLimiter(min_interval)
        self.metrics = RequestMetrics()

    @staticmethod
    def _headers(message: Message | Mapping[str, str]) -> dict[str, str]:
        if isinstance(message, Message):
            return {key: value for key, value in message.items()}
        return dict(message)

    def _request(
        self,
        request: urllib.request.Request,
        *,
        kind: str,
    ) -> HttpResponse:
        self.limiter.wait()
        self.metrics.record(kind)
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                status = int(response.status)
                headers = self._headers(response.headers)
                url = response.geturl()
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = int(exc.code)
            headers = self._headers(exc.headers)
            url = exc.geturl()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RequestError(f"request failed: {request.full_url}: {exc}") from exc

        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("utf-8", errors="replace")
        return HttpResponse(
            url=url,
            status=status,
            headers=headers,
            text=text,
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )

    def get(
        self,
        url: str,
        *,
        kind: str = "generic",
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        request_headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"}
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(url, headers=request_headers, method="GET")
        return self._request(request, kind=kind)

    def post_form(
        self,
        url: str,
        data: Mapping[str, str | int],
        *,
        kind: str = "generic",
        headers: Mapping[str, str] | None = None,
    ) -> HttpResponse:
        encoded = urllib.parse.urlencode({key: str(value) for key, value in data.items()}).encode("utf-8")
        request_headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json,text/plain,*/*",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        }
        if headers:
            request_headers.update(headers)
        request = urllib.request.Request(url, data=encoded, headers=request_headers, method="POST")
        return self._request(request, kind=kind)
