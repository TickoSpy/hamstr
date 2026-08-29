"""HTTP fetching with hand-rolled redirects.

httpx's own ``follow_redirects`` would hop straight past our SSRF guard, so every
request here is issued with redirects disabled and each ``Location`` is
re-validated before we follow it.
"""

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from urllib.parse import urljoin

import httpx

from app.config import settings
from app.services.urlsafety import UnsafeUrlError, assert_safe_url

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,de;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

REDIRECT_CODES = (301, 302, 303, 307, 308)

# The browser-ish UA is what gets us past news-site bot walls, but some hosts do
# the opposite and block browser UAs from non-browser clients (w3.org, for one).
# On a hard refusal, try once more as an honest robot.
FALLBACK_USER_AGENT = "hamstr/1.0 (+self-hosted archive)"
UA_RETRY_CODES = (401, 403, 406, 429)


class IngestHttpError(RuntimeError):
    """Base for fetch failures worth showing the user."""


class TooManyRedirects(IngestHttpError):
    """More redirect hops than we're willing to follow."""


class ContentTooLarge(IngestHttpError):
    """Response body exceeded the caller's byte cap."""


_STATUS_HINTS = {
    401: "the site requires a login",
    403: "the site blocks automated requests",
    404: "not found",
    410: "removed by the publisher",
    429: "rate-limited by the site",
    451: "blocked for legal reasons",
}


def describe_http_error(exc: Exception) -> str:
    """A short, actionable message for the queue UI.

    httpx's own HTTPStatusError string spans three lines and ends with an MDN
    link, which reads terribly in a status row.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        hint = _STATUS_HINTS.get(code)
        reason = exc.response.reason_phrase or ""
        return f"Fetch failed: {code} {reason}".strip() + (f" ({hint})" if hint else "")
    if isinstance(exc, ContentTooLarge):
        return str(exc)
    if isinstance(exc, TooManyRedirects):
        return "Too many redirects"
    if isinstance(exc, httpx.TimeoutException):
        return "Timed out fetching the URL"
    if isinstance(exc, httpx.TransportError):
        return f"Could not connect: {exc}"
    return str(exc) or exc.__class__.__name__


def build_client(
    *,
    timeout: float | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.AsyncClient:
    merged = {"User-Agent": settings.ingest_user_agent, **DEFAULT_HEADERS}
    if headers:
        merged.update(headers)
    return httpx.AsyncClient(
        follow_redirects=False,  # hand-rolled below so every hop is re-validated
        headers=merged,
        timeout=httpx.Timeout(
            connect=10.0,
            read=timeout if timeout is not None else settings.fetch_timeout_seconds,
            write=10.0,
            pool=5.0,
        ),
    )


async def _resolve_redirects(
    client: httpx.AsyncClient,
    url: str,
    *,
    method: str,
    max_redirects: int,
    timeout: float | None,
    extra_headers: dict[str, str] | None = None,
    ua_retried: bool = False,
    ua_retry: bool = True,
) -> tuple[httpx.Response, str]:
    """Issue `method` at `url`, following redirects manually. Returns the final
    (unclosed, streaming) response and the URL it came from."""
    current = url
    for _ in range(max_redirects + 1):
        await assert_safe_url(current)
        request = client.build_request(
            method, current, headers=extra_headers, timeout=timeout
        )
        response = await client.send(request, stream=True)

        if response.status_code in UA_RETRY_CODES and ua_retry and not ua_retried:
            await response.aclose()
            logger.debug(
                "%s refused %s — retrying with the plain user agent",
                current,
                response.status_code,
            )
            headers = dict(extra_headers or {})
            headers["User-Agent"] = FALLBACK_USER_AGENT
            return await _resolve_redirects(
                client,
                current,
                method=method,
                max_redirects=max_redirects,
                timeout=timeout,
                extra_headers=headers,
                ua_retried=True,
            )

        if response.status_code not in REDIRECT_CODES:
            return response, current

        location = response.headers.get("location")
        await response.aclose()
        if not location:
            raise IngestHttpError(f"Redirect without Location from {current}")
        current = urljoin(current, location)

    raise TooManyRedirects(f"More than {max_redirects} redirects starting at {url}")


async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_redirects: int = 5,
    max_bytes: int,
    timeout: float | None = None,
    extra_headers: dict[str, str] | None = None,
    ua_retry: bool = True,
) -> httpx.Response:
    """GET a URL into memory, capped at `max_bytes`.

    The returned response is fully read; `response.text` / `.content` are usable
    and `response.url` is the final URL after redirects.
    """
    response, final_url = await _resolve_redirects(
        client,
        url,
        method="GET",
        max_redirects=max_redirects,
        timeout=timeout,
        extra_headers=extra_headers,
        ua_retry=ua_retry,
    )
    try:
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > max_bytes:
                raise ContentTooLarge(
                    f"Response from {final_url} exceeds {max_bytes} bytes"
                )
            chunks.append(chunk)
    finally:
        await response.aclose()

    # Hand the body back through httpx so charset detection works as usual.
    # aiter_bytes() already decompressed the stream, so Content-Encoding and
    # Content-Length now describe the wire form, not `content` — leaving them on
    # makes httpx try to gunzip the plain bytes a second time.
    headers = httpx.Headers(
        [
            (k, v)
            for k, v in response.headers.multi_items()
            if k.lower() not in ("content-encoding", "content-length")
        ]
    )
    return httpx.Response(
        status_code=response.status_code,
        headers=headers,
        content=b"".join(chunks),
        request=response.request,
    )


async def resolve_final_url(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_redirects: int = 5,
    timeout: float = 10.0,
) -> str:
    """Follow redirects and return the URL they land on, without reading the body.

    Used to turn short/share links into their canonical form before deciding
    which host to actually fetch from.
    """
    try:
        response, final_url = await _resolve_redirects(
            client,
            url,
            method="GET",
            max_redirects=max_redirects,
            timeout=timeout,
            ua_retry=False,
        )
        await response.aclose()
        return final_url
    except Exception as exc:
        logger.debug("Could not resolve %s: %s", url, exc)
        return url


async def safe_stream_to_file(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    *,
    max_bytes: int,
    max_redirects: int = 5,
    timeout: float | None = None,
    on_progress: Callable[[int, int | None], Awaitable[None]] | None = None,
) -> tuple[int, httpx.Response]:
    """Stream a URL to `dest`. Returns (bytes_written, final response headers).

    The partial file is removed if the download overruns `max_bytes` or fails.
    """
    response, final_url = await _resolve_redirects(
        client, url, method="GET", max_redirects=max_redirects, timeout=timeout
    )
    try:
        response.raise_for_status()

        expected: int | None = None
        raw_len = response.headers.get("content-length")
        if raw_len and raw_len.isdigit():
            expected = int(raw_len)
            if expected > max_bytes:
                raise ContentTooLarge(
                    f"{final_url} advertises {expected} bytes (cap {max_bytes})"
                )

        written = 0
        with dest.open("wb") as fh:
            async for chunk in response.aiter_bytes():
                written += len(chunk)
                if written > max_bytes:
                    raise ContentTooLarge(f"{final_url} exceeds {max_bytes} bytes")
                fh.write(chunk)
                if on_progress is not None:
                    await on_progress(written, expected)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    finally:
        await response.aclose()

    return written, response


async def probe_head(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float = 5.0,
    max_redirects: int = 5,
) -> tuple[int, str | None, bytes]:
    """Cheaply learn a URL's content type.

    Tries HEAD; if the server refuses it, falls back to a ranged GET and reads
    the first 2 KiB so magic bytes are available. Returns
    (status_code, content_type, head_bytes).
    """
    try:
        response, _ = await _resolve_redirects(
            client, url, method="HEAD", max_redirects=max_redirects, timeout=timeout
        )
        try:
            status = response.status_code
            ctype = response.headers.get("content-type")
        finally:
            await response.aclose()
        if status < 400 and ctype:
            return status, ctype, b""
    except UnsafeUrlError:
        raise
    except Exception as exc:
        logger.debug("HEAD failed for %s: %s", url, exc)

    # HEAD unsupported or uninformative — read a little of the body instead.
    response, _ = await _resolve_redirects(
        client,
        url,
        method="GET",
        max_redirects=max_redirects,
        timeout=timeout,
        extra_headers={"Range": "bytes=0-2047"},
    )
    head = b""
    try:
        async for chunk in response.aiter_bytes():
            head += chunk
            if len(head) >= 2048:
                break
    finally:
        await response.aclose()

    return response.status_code, response.headers.get("content-type"), head
