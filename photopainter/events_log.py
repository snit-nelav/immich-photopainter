"""Structured event log for the web UI.

This is a slim, JSON-lines log file that records only the moments a user
typically cares about: cycle outcomes, Immich errors, cache fallbacks,
crashes. It is intentionally separate from photopainter.log (which can be
verbose and includes DEBUG) so the UI can render a clean event stream.

Format: one JSON object per line, e.g.
  {"ts": "2026-05-23T07:37:10+00:00", "level": "INFO", "msg": "cycle_ok",
   "asset_id": "b7a7a9c7", "duration_s": 25.83, "from_cache": false}

Rotation is delegated to logrotate (daily, 14-day retention).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path("/var/log/photopainter/events.log")

_logger = logging.getLogger(__name__)


def log_event(level: str, message: str, path: Path = DEFAULT_PATH, **fields: Any) -> None:
    """Append a single JSON entry to the events log. Never raises."""
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "level": level,
        "msg": message,
    }
    entry.update(fields)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        _logger.debug("events log append failed: %s", exc)


def read_tail(limit: int, before_ts: str | None = None, path: Path = DEFAULT_PATH) -> tuple[list[dict[str, Any]], bool]:
    """Return up to ``limit`` events older than ``before_ts`` (ISO 8601), newest first.

    Also returns a bool indicating whether more entries are available beyond
    the page returned (used by the UI to enable the "Load more" button).
    """
    if not path.exists():
        return [], False

    all_entries: list[dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if before_ts and entry.get("ts", "") >= before_ts:
                    continue
                all_entries.append(entry)
    except OSError:
        return [], False

    all_entries.sort(key=lambda e: e.get("ts", ""), reverse=True)
    return all_entries[:limit], len(all_entries) > limit


def has_alert_since_last_ok(path: Path = DEFAULT_PATH) -> bool:
    """Returns True if any ERROR or non-wifi WARNING was logged since the
    last ``cycle_ok`` event. Used by the cycle to decide whether to draw an
    alert badge on the next photo. Wi-Fi-related events are excluded — they
    are signalled by their own badge driven by ``source.fallback_used``.
    """
    if not path.exists():
        return False
    entries: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return False

    last_ok = -1
    for i, e in enumerate(entries):
        if e.get("msg") == "cycle_ok":
            last_ok = i
    after = entries[last_ok + 1:]

    # These messages are upstream/network related and are reported via the
    # Wi-Fi badge, not the generic alert one.
    WIFI_EVENTS = {
        "degraded_mode",
        "immich_retry",
        "immich_giveup",
        "upstream_unreachable_cache_fallback",
    }
    for e in after:
        if e.get("msg") in WIFI_EVENTS:
            continue
        if e.get("level") in ("ERROR", "WARNING"):
            return True
    return False


def clear(path: Path = DEFAULT_PATH) -> None:
    """Empty the events log file (best effort)."""
    try:
        if path.exists():
            path.write_text("", encoding="utf-8")
    except OSError as exc:
        _logger.debug("events log clear failed: %s", exc)
