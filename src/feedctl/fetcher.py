from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

USER_AGENT = "feedctl/0.1 (+https://github.com/frostming/feedctl)"


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FetchResult:
    data: bytes | None
    etag: str | None
    last_modified: str | None


def fetch_feed(
    url: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    timeout: float = 20.0,
) -> FetchResult:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "application/atom+xml, application/rss+xml, application/xml, "
            "text/xml;q=0.9, */*;q=0.1"
        ),
    }
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            return FetchResult(
                data=response.read(),
                etag=response.headers.get("ETag"),
                last_modified=response.headers.get("Last-Modified"),
            )
    except HTTPError as error:
        if error.code == 304:
            return FetchResult(data=None, etag=etag, last_modified=last_modified)
        raise FetchError(f"HTTP {error.code}: {error.reason}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise FetchError(str(error)) from error
