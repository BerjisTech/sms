"""Rate-limit checks built on top of the SQLite state.

Two independent limits:
  * a per-day cap (default 100 messages/day), and
  * a minimum interval between sends (default 1 every 5 seconds).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from . import db
from .config import Settings


@dataclass
class RateDecision:
    allowed: bool
    wait_seconds: float = 0.0   # how long until the interval limit clears
    daily_exhausted: bool = False
    reason: str = ""


def check(settings: Settings) -> RateDecision:
    """Decide whether a message may be sent right now."""
    sent_today = db.sent_today_count()
    if sent_today >= settings.rate_limit_per_day:
        return RateDecision(
            allowed=False,
            daily_exhausted=True,
            reason=(
                f"daily limit reached ({sent_today}/"
                f"{settings.rate_limit_per_day})"
            ),
        )

    last = db.last_sent_at()
    if last is not None:
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        remaining = settings.rate_limit_min_interval_seconds - elapsed
        if remaining > 0:
            return RateDecision(
                allowed=False,
                wait_seconds=remaining,
                reason=f"min interval not elapsed ({remaining:.1f}s left)",
            )

    return RateDecision(allowed=True)


def remaining_daily_quota(settings: Settings) -> int:
    return max(0, settings.rate_limit_per_day - db.sent_today_count())
