"""Site-login (cookie jar) storage and its admin gate."""

import http.cookiejar
import os
import stat

import pytest

from app.config import settings
from app.services import cookies as jars
from app.services.downloader import _ydl_base_opts


def cookie(name="SID", value="abc", domain="youtube.com", **kw):
    base = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": "/",
        "secure": True,
        "httpOnly": False,
        "hostOnly": False,
        "session": False,
        "expirationDate": 2000000000,
    }
    base.update(kw)
    return base


# ------------------------------------------------------------- serialisation


def test_netscape_round_trips_through_mozillacookiejar(storage_root, tmp_path):
    text = jars.to_netscape(
        [
            cookie("SID", "one"),
            cookie("__Secure-3PSID", "two", httpOnly=True),
            cookie("HOSTONLY", "three", hostOnly=True, path="/watch"),
            cookie("SESSIONY", "four", session=True, expirationDate=None),
        ]
    )
    path = tmp_path / "jar.txt"
    path.write_text(text)

    jar = http.cookiejar.MozillaCookieJar(str(path))
    # Session cookies (expiry 0) are "discard" records; ask for them explicitly.
    jar.load(ignore_discard=True, ignore_expires=True)
    loaded = {c.name: c for c in jar}

    assert set(loaded) == {"SID", "__Secure-3PSID", "HOSTONLY", "SESSIONY"}
    assert loaded["SID"].value == "one"
    assert loaded["SID"].domain == ".youtube.com"
    assert loaded["SID"].secure is True
    assert loaded["HOSTONLY"].domain == "youtube.com"
    assert loaded["HOSTONLY"].path == "/watch"
    assert loaded["SESSIONY"].expires in (None, 0)


def test_httponly_cookies_keep_their_marker(storage_root):
    text = jars.to_netscape([cookie("__Secure-3PSID", "x", httpOnly=True)])
    assert "#HttpOnly_.youtube.com\t" in text


def test_save_counts_httponly_cookies(storage_root):
    """`#HttpOnly_` lines look like comments. Miscounting them once rejected an
    entirely valid YouTube jar as empty — every session cookie there is httpOnly."""
    written = jars.save_jar(
        "youtube.com",
        [
            cookie("__Secure-3PSID", "a", httpOnly=True),
            cookie("LOGIN_INFO", "b", httpOnly=True),
        ],
    )
    assert written == 2
    assert jars.list_status()[0].cookie_count == 2


def test_cookies_with_tabs_or_empty_names_are_dropped(storage_root):
    text = jars.to_netscape(
        [cookie("bad\tname"), cookie("ok", "has\tvalue"), cookie(""), cookie("good")]
    )
    body = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    assert len(body) == 1
    assert body[0].endswith("\tgood\tabc")


# -------------------------------------------------------------------- on disk


def test_save_jar_writes_0600_and_builds_merged(storage_root):
    jars.save_jar("youtube.com", [cookie()])
    path = storage_root / "cookies" / "youtube.com.txt"
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    merged = storage_root / "cookies" / jars.MERGED_NAME
    assert stat.S_IMODE(os.stat(merged).st_mode) == 0o600


def test_merged_holds_every_site_with_one_header(storage_root):
    jars.save_jar("youtube.com", [cookie(domain="youtube.com")])
    jars.save_jar("nebula.tv", [cookie("NEB", "z", domain="nebula.tv")])

    text = (storage_root / "cookies" / jars.MERGED_NAME).read_text()
    assert text.count("# Netscape HTTP Cookie File") == 1
    assert ".youtube.com\t" in text
    assert ".nebula.tv\t" in text


def test_delete_jar_rebuilds_and_removes_merged_when_last(storage_root):
    jars.save_jar("youtube.com", [cookie()])
    jars.save_jar("nebula.tv", [cookie("NEB", "z", domain="nebula.tv")])

    assert jars.delete_jar("nebula.tv") is True
    text = (storage_root / "cookies" / jars.MERGED_NAME).read_text()
    assert ".nebula.tv\t" not in text
    assert ".youtube.com\t" in text

    assert jars.delete_jar("youtube.com") is True
    assert not (storage_root / "cookies" / jars.MERGED_NAME).exists()
    assert jars.delete_jar("youtube.com") is False


def test_status_reports_counts_and_sign_in_without_values(storage_root):
    jars.save_jar(
        "youtube.com",
        [
            cookie(
                "__Secure-3PSID", "secret", httpOnly=True, expirationDate=1900000000
            ),
            cookie("LOGIN_INFO", "secret2"),
            cookie("PREF", "secret3", expirationDate=2100000000),
        ],
    )
    jars.save_jar("nebula.tv", [cookie("NEB", "z", domain="nebula.tv")])

    by_domain = {s.domain: s for s in jars.list_status()}
    yt = by_domain["youtube.com"]
    assert yt.cookie_count == 3
    assert yt.signed_in is True
    assert yt.expires_at == 1900000000
    # Unknown site: we have no markers to check, so we do not guess.
    assert by_domain["nebula.tv"].signed_in is None

    jars.save_jar("youtube.com", [cookie("PREF", "only")])
    assert {s.domain: s.signed_in for s in jars.list_status()}["youtube.com"] is False


# ------------------------------------------------------------------ selection


def test_active_cookie_file_prefers_explicit_override(storage_root, monkeypatch):
    assert jars.active_cookie_file() is None
    assert "cookiefile" not in _ydl_base_opts()

    jars.save_jar("youtube.com", [cookie()])
    merged = storage_root / "cookies" / jars.MERGED_NAME
    assert jars.active_cookie_file() == merged
    assert _ydl_base_opts()["cookiefile"] == str(merged)

    manual = storage_root / "hand-rolled.txt"
    manual.write_text(jars.NETSCAPE_HEADER)
    monkeypatch.setattr(settings, "yt_cookies_file", manual)
    assert jars.active_cookie_file() == manual

    # A configured-but-missing override falls back rather than breaking downloads.
    monkeypatch.setattr(settings, "yt_cookies_file", storage_root / "gone.txt")
    assert jars.active_cookie_file() == merged


# ------------------------------------------------------------------- domains


@pytest.mark.parametrize(
    "domain",
    ["youtube.com", ".youtube.com", "www.youtube.com", "a.b.c.co.uk"],
)
def test_valid_domains(domain):
    assert jars.is_valid_domain(domain)


@pytest.mark.parametrize(
    "domain",
    [
        "",
        "..",
        "../etc/passwd",
        "youtube",
        "1.2.3.4",
        "a/b.com",
        "a\\b.com",
        "-bad.com",
        "yt..com",
        "::1",
        "x" * 300 + ".com",
    ],
)
def test_invalid_domains(domain):
    assert not jars.is_valid_domain(domain)


def test_jar_path_refuses_traversal(storage_root):
    with pytest.raises(ValueError):
        jars.jar_path("../../etc/passwd")


# ---------------------------------------------------------------- admin gate


@pytest.fixture
def admin(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "s3cret")
    return {"X-Admin-Token": "s3cret"}


async def test_routes_fail_closed_when_token_unset(client, storage_root, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", None)
    for call in (
        client.get("/api/cookies"),
        client.put("/api/cookies/youtube.com", json={"cookies": [cookie()]}),
        client.delete("/api/cookies/youtube.com"),
    ):
        assert (await call).status_code == 503


async def test_routes_reject_missing_or_wrong_token(client, storage_root, admin):
    assert (await client.get("/api/cookies")).status_code == 401
    bad = {"X-Admin-Token": "nope"}
    assert (await client.get("/api/cookies", headers=bad)).status_code == 401
    assert (await client.get("/api/cookies", headers=admin)).status_code == 200


async def test_put_get_delete_round_trip(client, storage_root, admin):
    body = {
        "cookies": [
            cookie("__Secure-3PSID", "tok", httpOnly=True),
            cookie("LOGIN_INFO"),
        ]
    }
    response = await client.put("/api/cookies/youtube.com", json=body, headers=admin)
    assert response.status_code == 200
    assert response.json()["cookie_count"] == 2
    assert response.json()["signed_in"] is True

    listed = (await client.get("/api/cookies", headers=admin)).json()
    assert [j["domain"] for j in listed] == ["youtube.com"]
    # The whole point: no values ever come back out.
    assert "tok" not in str(listed)
    assert "value" not in str(listed)

    assert (
        await client.delete("/api/cookies/youtube.com", headers=admin)
    ).status_code == 204
    assert (await client.get("/api/cookies", headers=admin)).json() == []
    assert (
        await client.delete("/api/cookies/youtube.com", headers=admin)
    ).status_code == 404


async def test_put_rejects_bad_domains_and_oversized_jars(client, storage_root, admin):
    body = {"cookies": [cookie()]}
    assert (
        await client.put("/api/cookies/1.2.3.4", json=body, headers=admin)
    ).status_code == 422
    assert (
        await client.put("/api/cookies/nope", json=body, headers=admin)
    ).status_code == 422

    empty = await client.put(
        "/api/cookies/youtube.com", json={"cookies": []}, headers=admin
    )
    assert empty.status_code == 422

    too_many = {"cookies": [cookie(f"c{i}") for i in range(301)]}
    assert (
        await client.put("/api/cookies/youtube.com", json=too_many, headers=admin)
    ).status_code == 422

    huge = {"cookies": [cookie("big", "x" * 8000) for _ in range(40)]}
    assert (
        await client.put("/api/cookies/youtube.com", json=huge, headers=admin)
    ).status_code == 422


# --------------------------------------------------------- error translation

YT_AGE_ERROR = (
    "ERROR: [youtube] NyXt5dPEfeQ: Sign in to confirm your age. This video may be "
    "inappropriate for some users. Use --cookies-from-browser or --cookies for the "
    "authentication."
)


def test_auth_error_names_the_site_and_the_fix(storage_root):
    """yt-dlp's own advice is useless here — there is no browser on the server."""
    explained = jars.explain_auth_error(
        YT_AGE_ERROR, "https://www.youtube.com/watch?v=NyXt5dPEfeQ"
    )
    assert explained is not None
    assert "youtube.com" in explained
    assert "not signed in to any site" in explained
    assert "--cookies-from-browser" not in explained


def test_auth_error_distinguishes_no_login_from_a_stale_one(storage_root):
    jars.save_jar("youtube.com", [cookie("__Secure-3PSID", "x", httpOnly=True)])
    explained = jars.explain_auth_error(YT_AGE_ERROR, "https://youtube.com/watch?v=x")
    assert "did not satisfy it" in explained
    assert "youtube.com" in explained


def test_ordinary_failures_keep_their_own_message(storage_root):
    assert jars.explain_auth_error("ERROR: unable to download video data: 404") is None
    assert jars.explain_auth_error("ffmpeg exited with code 1") is None


def test_account_refusal_is_not_reported_as_a_missing_login(storage_root):
    """ "Sign in to confirm your age" and "this content is age-restricted" look
    alike but need opposite fixes — the second means the jar worked."""
    jars.save_jar("youtube.com", [cookie("__Secure-3PSID", "x", httpOnly=True)])
    explained = jars.explain_auth_error(
        "ERROR: [youtube] NyXt5dPEfeQ: Sorry, this content is age-restricted",
        "https://www.youtube.com/watch?v=NyXt5dPEfeQ",
    )
    assert explained is not None
    assert "stored login was accepted" in explained
    assert "JavaScript runtime" in explained
    assert "Settings" not in explained
