"""Admin gate for the routes that handle stored site sessions.

The rest of the API is deliberately open — it holds nothing a LAN peer couldn't
already download. A cookie jar is different: it is a live login. So these few
routes need a token, and they fail *closed* — an unset ``ADMIN_TOKEN`` disables
them rather than leaving them unguarded.
"""

import secrets

from fastapi import Header, HTTPException, status

from app.config import settings


async def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.admin_token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Site logins are disabled: set ADMIN_TOKEN on the backend to enable them.",
        )
    if not x_admin_token or not secrets.compare_digest(
        x_admin_token, settings.admin_token
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid admin token")
