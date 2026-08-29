"""SSRF guards for URLs the backend fetches itself.

``is_safe_url`` is the cheap, synchronous check used by the submit-time pydantic
validator. ``assert_safe_url`` additionally resolves the hostname and rejects any
address that lands in a blocked range — that is what closes the two holes the
string-only check leaves open:

* hostnames that resolve to private space (``internal.corp → 10.0.0.5``)
* non-dotted IP literals (``http://2130706433/`` == 127.0.0.1), which
  ``ipaddress.ip_address`` rejects as a parse error and the string check then
  waves through as "just a hostname"

Redirect hops are re-validated by the caller (see ``ingest.http.safe_get``);
the guard itself is stateless.
"""

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    """Raised when a URL (or a redirect target) points somewhere we refuse to fetch."""


_SCHEME_RE = re.compile(r"^https?://", re.IGNORECASE)
_LOCAL_HOST_RE = re.compile(r"^(localhost|.*\.local)$", re.IGNORECASE)


def _blocked(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def is_safe_url(url: str) -> bool:
    """Allow any public HTTP/HTTPS URL; block private IPs and localhost (SSRF prevention)."""
    if not _SCHEME_RE.match(url):
        return False
    try:
        host = urlparse(url).hostname or ""
        if not host:
            return False
        if _LOCAL_HOST_RE.match(host):
            return False
        try:
            if _blocked(ipaddress.ip_address(host)):
                return False
        except ValueError:
            pass  # hostname, not an IP literal — resolution is checked separately
        return True
    except Exception:
        return False


async def _getaddrinfo(host: str, port: int) -> list:
    """Thin wrapper around getaddrinfo so tests can patch resolution."""
    loop = asyncio.get_running_loop()
    return await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)


async def assert_safe_url(url: str) -> None:
    """Raise ``UnsafeUrlError`` unless the URL is public HTTP(S) *and* every address
    it resolves to is outside the blocked ranges."""
    if not is_safe_url(url):
        raise UnsafeUrlError(f"Refusing to fetch non-public URL: {url}")

    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)

    try:
        infos = await _getaddrinfo(host, port)
    except Exception as exc:
        raise UnsafeUrlError(f"Cannot resolve host {host!r}: {exc}") from exc

    if not infos:
        raise UnsafeUrlError(f"Host {host!r} resolved to no addresses")

    for info in infos:
        sockaddr = info[4]
        try:
            addr = ipaddress.ip_address(sockaddr[0])
        except ValueError:
            raise UnsafeUrlError(f"Host {host!r} resolved to an unparsable address")
        if _blocked(addr):
            raise UnsafeUrlError(f"Host {host!r} resolves to blocked address {addr}")
