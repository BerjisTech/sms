"""Background worker that drains the queue while respecting rate limits."""

from __future__ import annotations

import asyncio
import logging

from . import db, rate_limiter
from .config import Settings
from .gateway import GatewayError, send_sms

log = logging.getLogger("sms.worker")

# How long to nap when the queue is empty or the daily cap is hit.
_IDLE_SLEEP = 5.0
_DAILY_SLEEP = 60.0


async def worker_loop(settings: Settings, stop: asyncio.Event) -> None:
    log.info("Queue worker started.")
    while not stop.is_set():
        msg = db.next_queued()
        if msg is None:
            await _sleep_or_stop(stop, _IDLE_SLEEP)
            continue

        decision = rate_limiter.check(settings)
        if not decision.allowed:
            if decision.daily_exhausted:
                log.info("Daily quota reached; pausing. %s", decision.reason)
                await _sleep_or_stop(stop, _DAILY_SLEEP)
            else:
                await _sleep_or_stop(stop, max(0.1, decision.wait_seconds))
            continue

        await _deliver(settings, msg)

    log.info("Queue worker stopped.")


async def _deliver(settings: Settings, msg) -> None:
    message_id = msg["id"]
    recipient = msg["recipient"]
    try:
        gateway_id = await send_sms(settings, recipient, msg["body"])
        db.mark_sent(message_id, gateway_id or None)
        db.add_log(message_id, recipient, "sent", None)
        log.info(
            "SENT id=%s to=%s gateway_id=%s", message_id, recipient, gateway_id
        )
    except GatewayError as exc:
        err = str(exc)
        status = db.mark_attempt_failed(
            message_id, err, settings.max_attempts
        )
        db.add_log(message_id, recipient, status, err)
        log.warning(
            "SEND FAILED id=%s to=%s status=%s error=%s",
            message_id,
            recipient,
            status,
            err,
        )
        # Brief back-off so a hard-down gateway doesn't spin the loop.
        await asyncio.sleep(2.0)


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass
