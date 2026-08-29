"""Site logins — one cookie jar per site, written by the browser extension.

The browser is the only party that can produce these: a page cannot read
another origin's cookies, and there is no OAuth path that yields the tokens
yt-dlp needs. So the extension performs the login and PUTs the jar here.

Write-only by design. No route returns a cookie name or value; the UI gets
counts and expiry so it can tell you a login went stale, nothing more.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.dependencies.admin import require_admin
from app.schemas.cookies import CookieJarIn, JarStatusOut, validated_domain
from app.services import cookies as jars

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cookies", tags=["cookies"], dependencies=[Depends(require_admin)]
)


def _domain(domain: str = Path(max_length=253)) -> str:
    try:
        return validated_domain(domain)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("")
async def list_jars() -> list[JarStatusOut]:
    return [JarStatusOut(**vars(s)) for s in jars.list_status()]


@router.put("/{domain}")
async def put_jar(payload: CookieJarIn, domain: str = Depends(_domain)) -> JarStatusOut:
    written = jars.save_jar(domain, [c.model_dump() for c in payload.cookies])
    if not written:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "No usable cookies in the payload"
        )
    for status_row in jars.list_status():
        if status_row.domain == domain:
            return JarStatusOut(**vars(status_row))
    raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Jar was not stored")


@router.delete("/{domain}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_jar(domain: str = Depends(_domain)) -> None:
    if not jars.delete_jar(domain):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No login stored for that site")
