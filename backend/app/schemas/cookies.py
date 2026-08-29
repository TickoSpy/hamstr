"""Schemas for the site-login (cookie jar) endpoints."""

from pydantic import BaseModel, Field, field_validator

from app.services.cookies import is_valid_domain, normalise_domain

# A jar is a browser profile's worth of cookies for one site, not a database.
MAX_COOKIES = 300
MAX_JAR_BYTES = 256 * 1024


class CookieIn(BaseModel):
    """One cookie, in the shape `browser.cookies.getAll()` already returns."""

    name: str = Field(max_length=256)
    value: str = Field(max_length=8192)
    domain: str = Field(max_length=253)
    path: str = Field(default="/", max_length=1024)
    secure: bool = False
    httpOnly: bool = False
    hostOnly: bool = False
    session: bool = False
    expirationDate: float | None = None

    @field_validator("name", "value", "domain", "path")
    @classmethod
    def no_control_chars(cls, v: str) -> str:
        if "\t" in v or "\n" in v or "\r" in v:
            raise ValueError("Cookie fields may not contain tabs or newlines")
        return v


class CookieJarIn(BaseModel):
    cookies: list[CookieIn] = Field(max_length=MAX_COOKIES)

    @field_validator("cookies")
    @classmethod
    def within_size_budget(cls, v: list[CookieIn]) -> list[CookieIn]:
        if not v:
            raise ValueError("A jar must contain at least one cookie")
        total = sum(len(c.name) + len(c.value) + len(c.domain) + len(c.path) for c in v)
        if total > MAX_JAR_BYTES:
            raise ValueError("Cookie jar exceeds the maximum size")
        return v


class JarStatusOut(BaseModel):
    """Status only — no route ever returns cookie names or values."""

    domain: str
    cookie_count: int
    updated_at: float
    expires_at: int | None = None
    # None when we have no session-cookie markers for this site to check.
    signed_in: bool | None = None


def validated_domain(domain: str) -> str:
    if not is_valid_domain(domain):
        raise ValueError("Not a valid site domain")
    return normalise_domain(domain)
