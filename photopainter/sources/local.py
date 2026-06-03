"""LocalSource — photos uploaded directly to the Pi from the web UI.

The source is a flat directory (default /var/lib/photopainter/local/) of JPEG
files. Filenames double as asset ids — no metadata cache, no database, the
filesystem is the source of truth.

No caching wrapper is used in build_source() for this backend: every "download"
already reads from a local file, so a CachingSource would just be a noisy copy.
"""
from __future__ import annotations

import logging
from pathlib import Path

from photopainter.sources.base import Asset

logger = logging.getLogger(__name__)

# Extensions we serve to the rendering pipeline. The /api/local/upload endpoint
# accepts a wider set (PNG, WEBP, …) but always rewrites them to JPEG, so on
# disk we only ever see .jpg here.
SERVED_EXTENSIONS = {".jpg", ".jpeg"}


class LocalSource:
    name = "local"

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def list_assets(self) -> list[Asset]:
        if not self.directory.exists():
            logger.info("local: directory %s does not exist yet", self.directory)
            return []
        assets: list[Asset] = []
        for p in sorted(self.directory.iterdir()):
            if not p.is_file() or p.suffix.lower() not in SERVED_EXTENSIONS:
                continue
            assets.append(Asset(id=p.name, type="IMAGE", filename=p.name))
        logger.info("local: %d IMAGE assets in %s", len(assets), self.directory)
        return assets

    def download(self, asset_id: str) -> bytes:
        # asset_id is the filename — reject anything that would escape the dir.
        safe = Path(asset_id).name
        if safe != asset_id or not safe:
            raise ValueError(f"invalid asset id: {asset_id!r}")
        path = self.directory / safe
        if not path.is_file():
            raise FileNotFoundError(f"local asset missing: {safe}")
        return path.read_bytes()
