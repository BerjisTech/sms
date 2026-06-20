"""HTTP client for the capcom6 android-sms-gateway local server API."""

from __future__ import annotations

import httpx

from .config import Settings


class GatewayError(Exception):
    """Raised when the Android gateway rejects or fails a send."""


async def send_sms(settings: Settings, recipient: str, body: str) -> str:
    """Send one SMS through the phone. Returns the gateway message id.

    The local server exposes ``POST /message`` protected by HTTP basic auth:
        { "message": "...", "phoneNumbers": ["+1..."] }
    """
    url = f"{settings.gateway_base_url}/message"
    payload = {"message": body, "phoneNumbers": [recipient]}
    auth = (settings.gateway_username, settings.gateway_password)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, auth=auth)
    except httpx.HTTPError as exc:
        raise GatewayError(f"could not reach gateway at {url}: {exc}") from exc

    if resp.status_code >= 400:
        raise GatewayError(
            f"gateway returned HTTP {resp.status_code}: {resp.text[:300]}"
        )

    try:
        data = resp.json()
    except ValueError:
        return ""
    return str(data.get("id", ""))
