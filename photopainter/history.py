"""JSON history of recently displayed asset ids, used to avoid repeats."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from collections import deque
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class History:
    def __init__(self, path: Path, max_size: int = 20) -> None:
        self.path = path
        self.max_size = max_size
        self._ids: deque[str] = deque(maxlen=max_size)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            logger.info("history: no existing file, starting empty")
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            entries = data.get("entries", [])
            self._ids = deque(entries[-self.max_size:], maxlen=self.max_size)
            logger.debug("history: loaded %d entries", len(self._ids))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("history: file unreadable (%s), resetting to empty", exc)
            self._ids = deque(maxlen=self.max_size)

    def contains(self, asset_id: str) -> bool:
        return asset_id in self._ids

    def add(self, asset_id: str) -> None:
        self._ids.append(asset_id)
        self._persist()

    def all(self) -> list[str]:
        return list(self._ids)

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entries": list(self._ids),
        }
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)
