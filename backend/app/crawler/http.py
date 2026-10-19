"""Bounded HTTP fetches: never download more than a page's worth, never wait forever on a slow stream."""

import time
from dataclasses import dataclass

import httpx

MAX_BYTES = 5_000_000
MAX_SECONDS = 30.0


@dataclass
class Fetched:
    url: str
    status_code: int
    headers: httpx.Headers
    text: str | None  # None when skipped (wrong content type) or truncated past the cap
    truncated: bool = False

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "")


def fetch(client: httpx.Client, url: str, accept=lambda content_type: True,
          max_bytes: int = MAX_BYTES, max_seconds: float = MAX_SECONDS) -> Fetched:
    """GET `url`, reading the body only if `accept(content_type)` and only up to the size/time caps.

    httpx's read timeout applies per chunk, so a server trickling a large file never trips it;
    the overall deadline here does.
    """
    deadline = time.monotonic() + max_seconds
    with client.stream("GET", url) as resp:
        if not accept(resp.headers.get("content-type", "")):
            return Fetched(str(resp.url), resp.status_code, resp.headers, None)
        chunks, size, truncated = [], 0, False
        for chunk in resp.iter_bytes():
            chunks.append(chunk)
            size += len(chunk)
            if size > max_bytes or time.monotonic() > deadline:
                truncated = True
                break
        body = b"".join(chunks)
        encoding = resp.charset_encoding or "utf-8"
        text = None if truncated else body.decode(encoding, errors="replace")
        return Fetched(str(resp.url), resp.status_code, resp.headers, text, truncated)


def is_html(content_type: str) -> bool:
    return "text/html" in content_type or "application/xhtml" in content_type


def is_texty(content_type: str) -> bool:
    return not content_type or any(t in content_type for t in ("text/", "json", "xml", "yaml"))
