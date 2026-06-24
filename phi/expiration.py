"""Expiration status and color tinting for inventory items."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Optional

from phi.models import Item

DAYS_PER_YEAR = 365


class ExpirationStatus(Enum):
    """Tint level based on the oldest expiration among an item's units."""

    OK = "ok"  # not expired, or no expiration dates
    RECENT = "recent"  # expired less than 1 year ago
    AGING = "aging"  # expired 1–3 years ago
    OLD = "old"  # expired 3–5 years ago
    DISPOSE = "dispose"  # expired 5+ years ago


@dataclass(frozen=True)
class ExpirationInfo:
    status: ExpirationStatus
    oldest_expiration: Optional[date]
    message: str
    bg_color: str  # hex background tint for list cards
    fg_color: str  # hex text/accent color


# Palette tuned for dark UI backgrounds
_COLORS = {
    ExpirationStatus.OK: ("#1a2a3d", "#6eb5ff"),
    ExpirationStatus.RECENT: ("#1a3d1a", "#6fcf6f"),
    ExpirationStatus.AGING: ("#3d3a1a", "#f2c94c"),
    ExpirationStatus.OLD: ("#3d1a1a", "#eb5757"),
    ExpirationStatus.DISPOSE: ("#0d0d0d", "#ffffff"),
}


def _parse_date(value: str) -> Optional[date]:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _oldest_expiration(item: Item) -> Optional[date]:
    dates: list[date] = []
    for unit in item.units:
        if unit.expiration:
            parsed = _parse_date(unit.expiration)
            if parsed:
                dates.append(parsed)
    return min(dates) if dates else None


def get_expiration_info(item: Item, today: Optional[date] = None) -> ExpirationInfo:
    """
    Evaluate expiration status from the oldest (earliest) dated unit.

    Scale:
      - Blue   — not expired, or no expiration dates
      - Green  — expired less than 1 year ago
      - Yellow — expired 1–3 years ago
      - Red    — expired 3–5 years ago
      - Black  — expired 5+ years ago (consider disposal)
    """
    ref = today or date.today()
    oldest = _oldest_expiration(item)

    if oldest is None:
        bg, fg = _COLORS[ExpirationStatus.OK]
        return ExpirationInfo(
            status=ExpirationStatus.OK,
            oldest_expiration=None,
            message="No expiration date",
            bg_color=bg,
            fg_color=fg,
        )

    days_until = (oldest - ref).days

    if days_until >= 0:
        status = ExpirationStatus.OK
        if days_until == 0:
            message = f"Expires today — {oldest.isoformat()}"
        else:
            message = f"Not expired — expires {oldest.isoformat()} ({days_until}d)"
    else:
        days_past = abs(days_until)
        if days_past < DAYS_PER_YEAR:
            status = ExpirationStatus.RECENT
            message = f"Expired {oldest.isoformat()} (< 1 year ago)"
        elif days_past < DAYS_PER_YEAR * 3:
            status = ExpirationStatus.AGING
            message = f"Expired {oldest.isoformat()} (1–3 years ago)"
        elif days_past < DAYS_PER_YEAR * 5:
            status = ExpirationStatus.OLD
            message = f"Expired {oldest.isoformat()} (3–5 years ago)"
        else:
            status = ExpirationStatus.DISPOSE
            message = f"Expired {oldest.isoformat()} — consider disposal"

    bg, fg = _COLORS[status]
    return ExpirationInfo(
        status=status,
        oldest_expiration=oldest,
        message=message,
        bg_color=bg,
        fg_color=fg,
    )
