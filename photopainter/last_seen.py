"""Per-asset last-seen timestamps, sliced by source context.

Each *slot* (one source, or one Immich album) keeps its own
`{asset_id: iso_timestamp}` map inside a single JSON file. The slot key is
derived from the running config:

    "local"                          for the Local source
    "immich:<album_uuid>"            for a given Immich album

Switching source or album doesn't wipe anything — the new slot simply loads
(empty if first time) and the previous slots stay on disk, so the user can
flip back and forth between Local and Immich every week without losing the
weighted-random history on either side.
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def slot_key(source_active: str, immich_album_id: str = "") -> str:
    """Return a stable key identifying the current photo context.
    Used to namespace the last-seen history so each (source, album)
    keeps its own weighted-random state."""
    if source_active == "immich":
        return f"immich:{immich_album_id}"
    return source_active  # "local" today, future "google:<id>" later


class LastSeen:
    def __init__(self, path: Path, slot: str) -> None:
        self.path = path
        self.slot = slot
        self._slots: dict[str, dict[str, datetime]] = {}
        self._load()

    @property
    def _seen(self) -> dict[str, datetime]:
        return self._slots.setdefault(self.slot, {})

    def _load(self) -> None:
        if not self.path.exists():
            logger.info("last_seen: no existing file, starting empty")
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("last_seen: file unreadable (%s), resetting to empty", exc)
            return
        slots_raw = raw.get("slots") if isinstance(raw, dict) else None
        # Tolerate the legacy single-slot format ({entries: {...}}). We don't
        # know which context those entries belonged to, so we drop them — the
        # cost is one or two cycles of "rediscovery" before the weighting
        # kicks back in.
        if not isinstance(slots_raw, dict):
            logger.info("last_seen: legacy format or unrecognised payload, starting empty")
            return
        for k, entries in slots_raw.items():
            if not isinstance(entries, dict):
                continue
            slot: dict[str, datetime] = {}
            for aid, ts in entries.items():
                try:
                    slot[aid] = datetime.fromisoformat(ts)
                except (TypeError, ValueError):
                    continue
            self._slots[k] = slot
        logger.debug("last_seen: loaded %d slot(s); active slot %s has %d entries",
                     len(self._slots), self.slot, len(self._seen))

    def record(self, asset_id: str, now: datetime | None = None) -> None:
        self._seen[asset_id] = now or datetime.now(timezone.utc)
        self._persist()

    def clear(self) -> None:
        """Empty the current slot. Other slots on disk are kept untouched."""
        self._slots[self.slot] = {}
        self._persist()

    def has(self, asset_id: str) -> bool:
        return asset_id in self._seen

    def days_since(self, asset_id: str, now: datetime) -> float | None:
        ts = self._seen.get(asset_id)
        if ts is None:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0.0, (now - ts).total_seconds() / 86400.0)

    def pick(self, candidates: list[str], now: datetime | None = None) -> str:
        """Weighted random pick across `candidates`.

        Two-step policy: assets that have never been shown win first
        (uniform draw among them). Once every asset has at least one
        appearance recorded, switch to weighted random with
        weight = days_since_last_seen + 1, so an asset shown today still
        has a non-zero chance but is heavily down-weighted vs an asset
        shown two months ago.
        """
        if not candidates:
            raise ValueError("pick() needs at least one candidate")
        now = now or datetime.now(timezone.utc)
        never_seen = [aid for aid in candidates if aid not in self._seen]
        if never_seen:
            return random.choice(never_seen)
        weights = [(self.days_since(aid, now) or 0.0) + 1.0 for aid in candidates]
        return random.choices(candidates, weights=weights, k=1)[0]

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "slots": {
                key: {aid: ts.isoformat() for aid, ts in entries.items()}
                for key, entries in self._slots.items()
            },
        }
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)
