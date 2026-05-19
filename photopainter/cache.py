"""Local on-disk cache for downloaded originals — LRU eviction on demand.

Each asset is stored as a single binary file named "<asset_id>.bin" inside the
cache directory. We use the file mtime as the access timestamp (touched on
read), so LRU eviction can be done by ordering files by mtime ascending.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class AssetCache:
    def __init__(self, path: Path, max_size_bytes: int) -> None:
        self.path = path
        self.max_size_bytes = max_size_bytes
        self.path.mkdir(parents=True, exist_ok=True)

    def _file_for(self, asset_id: str) -> Path:
        safe = "".join(c for c in asset_id if c.isalnum() or c == "-")
        return self.path / f"{safe}.bin"

    def has(self, asset_id: str) -> bool:
        return self._file_for(asset_id).exists()

    def get(self, asset_id: str) -> bytes | None:
        f = self._file_for(asset_id)
        if not f.exists():
            return None
        # Touch mtime so this asset becomes the most-recently used.
        try:
            os.utime(f, None)
        except OSError:
            pass
        return f.read_bytes()

    def put(self, asset_id: str, data: bytes) -> None:
        f = self._file_for(asset_id)
        tmp = f.with_suffix(f.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(f)
        logger.debug("cache put %s (%d bytes)", asset_id[:8], len(data))

    def list_ids(self) -> list[str]:
        return [f.stem for f in self.path.glob("*.bin")]

    def total_size(self) -> int:
        return sum(f.stat().st_size for f in self.path.glob("*.bin"))

    def file_count(self) -> int:
        return sum(1 for _ in self.path.glob("*.bin"))

    def purge_excess(self) -> tuple[int, int]:
        """Delete the oldest files (by mtime) until total size <= max_size_bytes.
        Returns (files_removed, bytes_freed)."""
        files = list(self.path.glob("*.bin"))
        total = sum(f.stat().st_size for f in files)
        if total <= self.max_size_bytes:
            return (0, 0)
        files.sort(key=lambda f: f.stat().st_mtime)
        removed = 0
        freed = 0
        for f in files:
            if total <= self.max_size_bytes:
                break
            size = f.stat().st_size
            try:
                f.unlink()
                total -= size
                removed += 1
                freed += size
            except OSError as exc:
                logger.warning("cache purge: failed on %s (%s)", f.name, exc)
        return (removed, freed)


def gb_to_bytes(gb: float) -> int:
    return int(gb * 1024 * 1024 * 1024)
