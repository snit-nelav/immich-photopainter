"""Active-hours window check + refresh-interval debouncing."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Europe/Paris")

# Tolerance to absorb drift caused by cron-tick alignment and cycle duration.
# Without this, a 5-minute interval would actually fire every ~10 minutes because
# the cron */5 tick that lands right after last_run+5min sees elapsed = 4m59s.
SCHEDULER_TOLERANCE_SECONDS = 60


def is_in_active_hours(now: datetime, start_hour: int, end_hour: int) -> bool:
    """Half-open window [start_hour, end_hour) in local Europe/Paris time."""
    local = now.astimezone(TZ)
    return start_hour <= local.hour < end_hour


def time_since_last_run(status_path: Path) -> float | None:
    """Seconds since the last successful refresh, or None if never run."""
    if not status_path.exists():
        return None
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
        ts = data.get("timestamp")
        if not ts:
            return None
        last = datetime.fromisoformat(ts)
        return (datetime.now(timezone.utc) - last).total_seconds()
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        logger.warning("last_status unreadable (%s), treating as never run", exc)
        return None


def should_refresh_now(
    now: datetime,
    start_hour: int,
    end_hour: int,
    interval_minutes: int,
    status_path: Path,
) -> tuple[bool, str]:
    """Decide whether to refresh on this tick. Returns (do_refresh, reason)."""
    if not is_in_active_hours(now, start_hour, end_hour):
        return False, f"outside active hours ({start_hour}h-{end_hour}h)"

    elapsed = time_since_last_run(status_path)
    if elapsed is None:
        return True, "first run (no last_status)"

    interval_seconds = interval_minutes * 60
    threshold = interval_seconds - SCHEDULER_TOLERANCE_SECONDS
    if elapsed >= threshold:
        return True, f"interval elapsed ({int(elapsed)}s >= {threshold}s, target {interval_seconds}s)"

    remaining = int(threshold - elapsed)
    return False, f"too early ({remaining}s until next firing window, interval {interval_minutes}min)"


def write_last_status(
    status_path: Path,
    asset_id: str,
    durations: dict[str, float],
    status: str,
) -> None:
    """Persist the result of the last cycle (atomic write)."""
    status_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = status_path.with_suffix(status_path.suffix + ".tmp")
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "asset_id": asset_id,
        "status": status,
        "durations": durations,
    }
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(status_path)


def read_last_status(status_path: Path) -> dict | None:
    if not status_path.exists():
        return None
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
