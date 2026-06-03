"""Weekly activity calendar check + refresh-interval debouncing."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

TZ = ZoneInfo("Europe/Paris")

# Tolerance to absorb drift caused by cron-tick alignment and cycle duration.
SCHEDULER_TOLERANCE_SECONDS = 60


def is_active_hour(now: datetime, active_hours: list[list[bool]]) -> bool:
    """True when ``now`` falls in a cell of the weekly schedule that is
    flagged as active. ``active_hours`` is a 7×24 boolean matrix indexed by
    [weekday][hour] with weekday 0=Monday .. 6=Sunday (Python convention)."""
    local = now.astimezone(TZ)
    day = local.weekday()
    hour = local.hour
    try:
        return bool(active_hours[day][hour])
    except (IndexError, TypeError):
        # Fail-open: better refresh than stay silent forever if the schedule
        # got corrupted somehow.
        return True


def time_since_last_run(status_path: Path) -> float | None:
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
    active_hours: list[list[bool]],
    interval_minutes: int,
    status_path: Path,
) -> tuple[bool, str]:
    """Decide whether to refresh on this tick. Returns (do_refresh, reason)."""
    if not is_active_hour(now, active_hours):
        local = now.astimezone(TZ)
        return False, f"inactive slot (weekday {local.weekday()}, hour {local.hour:02d})"

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
    **extra,
) -> None:
    status_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = status_path.with_suffix(status_path.suffix + ".tmp")
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "asset_id": asset_id,
        "status": status,
        "durations": durations,
        **extra,
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
