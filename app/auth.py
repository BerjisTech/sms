"""HTTP Basic auth for this server's own endpoints."""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .config import Settings, get_settings

_security = HTTPBasic()


def require_auth(
    credentials: HTTPBasicCredentials = Depends(_security),
    settings: Settings = Depends(get_settings),
) -> str:
    """Validate basic-auth credentials with constant-time comparison."""
    user_ok = secrets.compare_digest(
        credentials.username, settings.server_username
    )
    pass_ok = secrets.compare_digest(
        credentials.password, settings.server_password
    )
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
