import pytest

from app.services import urlsafety
from app.services.urlsafety import UnsafeUrlError, assert_safe_url, is_safe_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "http://example.com/article",
        "https://sub.domain.example.co.uk/a/b?c=d#e",
    ],
)
def test_is_safe_url_allows_public(url):
    assert is_safe_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/x",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "http://localhost:8000/",
        "http://printer.local/",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://0.0.0.0/",
        "",
        "https://",
    ],
)
def test_is_safe_url_rejects(url):
    assert is_safe_url(url) is False


def _fake_resolution(monkeypatch, addresses: list[str]):
    async def _fake(host: str, port: int) -> list:
        return [(2, 1, 6, "", (a, port)) for a in addresses]

    monkeypatch.setattr(urlsafety, "_getaddrinfo", _fake)


async def test_assert_safe_url_allows_public_resolution(monkeypatch):
    _fake_resolution(monkeypatch, ["93.184.216.34"])
    await assert_safe_url("https://example.com/a")


async def test_assert_safe_url_rejects_hostname_resolving_to_private(monkeypatch):
    """The string check waves this through — only DNS resolution catches it."""
    assert is_safe_url("http://internal.corp.example/") is True
    _fake_resolution(monkeypatch, ["10.0.0.5"])
    with pytest.raises(UnsafeUrlError):
        await assert_safe_url("http://internal.corp.example/")


async def test_assert_safe_url_rejects_decimal_ip_literal(monkeypatch):
    """http://2130706433/ is 127.0.0.1; ip_address() raises on it, so the string
    check treats it as a hostname. getaddrinfo resolves it for real."""
    _fake_resolution(monkeypatch, ["127.0.0.1"])
    with pytest.raises(UnsafeUrlError):
        await assert_safe_url("http://2130706433/")


async def test_assert_safe_url_rejects_any_blocked_address_in_the_set(monkeypatch):
    """A host that resolves to both a public and a private address is rejected."""
    _fake_resolution(monkeypatch, ["93.184.216.34", "192.168.0.9"])
    with pytest.raises(UnsafeUrlError):
        await assert_safe_url("https://rebind.example/")


async def test_assert_safe_url_rejects_non_http_scheme():
    with pytest.raises(UnsafeUrlError):
        await assert_safe_url("file:///etc/passwd")


async def test_assert_safe_url_rejects_unresolvable(monkeypatch):
    async def _boom(host: str, port: int) -> list:
        raise OSError("nxdomain")

    monkeypatch.setattr(urlsafety, "_getaddrinfo", _boom)
    with pytest.raises(UnsafeUrlError):
        await assert_safe_url("https://does-not-exist.example/")


async def test_assert_safe_url_rejects_empty_resolution(monkeypatch):
    _fake_resolution(monkeypatch, [])
    with pytest.raises(UnsafeUrlError):
        await assert_safe_url("https://example.com/")
