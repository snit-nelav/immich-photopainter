"""Per-asset last-seen timestamps, used to weight the random pick away from
recently-shown photos and towards photos that have never been displayed.

Stored as a plain JSON map `{asset_id: iso_timestamp_utc}`. The file grows as
new photos are shown and orphan entries (assets no longer in the album) are
left as-is — they are simply ignored at weighting time because they don't
appear in the candidate pool.
"""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class LastSeen:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._seen: dict[str, datetime] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            logger.info("last_seen: no existing file, starting empty")
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            entries = raw.get("entries", {}) if isinstance(raw, dict) else {}
            for aid, ts in entries.items():
                try:
                    self._seen[aid] = datetime.fromisoformat(ts)
                except (TypeError, ValueError):
                    continue
            logger.debug("last_seen: loaded %d entries", len(self._seen))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("last_seen: file unreadable (%s), resetting to empty", exc)
            self._seen = {}

    def record(self, asset_id: str, now: datetime | None = None) -> None:
        self._seen[asset_id] = now or datetime.now(timezone.utc)
        self._persist()

    def clear(self) -> None:
        self._seen = {}
        # Remove the file outright so the next cycle treats every photo as
        # never-seen (uniform priority pick), giving the new album a fresh start.
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("last_seen: could not delete %s (%s)", self.path, exc)

    def has(self, asset_id: str) -> bool:
        return asset_id in self._seen

    def days_since(self, asset_id: str, now: datetime) -> float | None:
        ts = self._seen.get(asset_id)
        if ts is None:
            return None
        # Tolerate naive timestamps from older versions of the file.
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
            "entries": {aid: ts.isoformat() for aid, ts in self._seen.items()},
        }
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)
