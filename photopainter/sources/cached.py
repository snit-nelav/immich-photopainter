"""CachingSource — wraps a PhotoSource with a local on-disk cache.

Behaviour:
  - list_assets(): call the upstream; on exception, fall back to listing assets
    currently in the local cache (so the frame keeps cycling even when Immich
    is unreachable).
  - download(id): cache HIT returns the local bytes directly (no network);
    cache MISS calls the upstream and stores the result on the way back.
"""
from __future__ import annotations

import logging

from photopainter.cache import AssetCache
from photopainter.sources.base import Asset, PhotoSource

logger = logging.getLogger(__name__)


class CachingSource:
    def __init__(self, upstream: PhotoSource, cache: AssetCache) -> None:
        self._upstream = upstream
        self._cache = cache
        self.name = upstream.name + "+cache"
        self.fallback_used: bool = False

    def list_assets(self) -> list[Asset]:
        try:
            assets = self._upstream.list_assets()
            self.fallback_used = False
            return assets
        except Exception as exc:
            logger.warning("upstream source unreachable (%s), falling back to local cache", exc)
            self.fallback_used = True
            return [Asset(id=aid, type="IMAGE", filename="") for aid in self._cache.list_ids()]

    def download(self, asset_id: str) -> bytes:
        cached = self._cache.get(asset_id)
        if cached is not None:
            logger.info("cache HIT %s (%d bytes)", asset_id[:8], len(cached))
            return cached
        if self.fallback_used:
            raise RuntimeError(f"asset {asset_id} not in cache and upstream unreachable")
        logger.info("cache MISS %s, downloading from upstream", asset_id[:8])
        data = self._upstream.download(asset_id)
        self._cache.put(asset_id, data)
        return data
