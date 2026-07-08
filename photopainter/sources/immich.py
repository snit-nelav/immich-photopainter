"""Immich source — API-key authentication only."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from photopainter.events_log import log_event
from photopainter.sources.base import Asset

logger = logging.getLogger(__name__)


class ImmichError(RuntimeError):
    pass


class ImmichSource:
    name = "immich"

    def __init__(
        self,
        base_url: str,
        api_key: str,
        album_id: str,
        timeout_seconds: int = 30,
    ) -> None:
        if not base_url:
            raise ImmichError("base_url is required")
        if not api_key:
            raise ImmichError("api_key is required")
        if not album_id:
            raise ImmichError("album_id is required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.album_id = album_id
        self.timeout = timeout_seconds
        self._session = requests.Session()
        self._session.headers["x-api-key"] = api_key

    def list_assets(self) -> list[Asset]:
        out: list[Asset] = []
        # Immich v3 dropped the embedded `assets` array from GET /api/albums/{id}
        # (it only returns metadata now), so we enumerate the album's assets via
        # the paginated metadata-search endpoint instead.
        page = 1
        while page:
            payload = self._retry(lambda p=page: self._fetch_album_page(p))
            assets = payload.get("assets", {})
            for a in assets.get("items", []):
                if a.get("type") != "IMAGE":
                    continue
                # Prefer the EXIF "shot at" date; fall back to the file creation date.
                date_taken = (a.get("exifInfo") or {}).get("dateTimeOriginal") or a.get("fileCreatedAt")
                out.append(Asset(
                    id=a["id"],
                    type="IMAGE",
                    filename=a.get("originalFileName", ""),
                    date_taken=date_taken,
                ))
            # `nextPage` is the next page number as a string, or null when done.
            next_page = assets.get("nextPage")
            page = int(next_page) if next_page else 0
        logger.info("Immich: %d IMAGE assets in album", len(out))
        return out

    def download(self, asset_id: str) -> bytes:
        return self._retry(lambda: self._fetch_original(asset_id))

    def _retry(self, fn, attempts: int = 3) -> Any:
        last_exc: Exception | None = None
        for i in range(attempts):
            try:
                return fn()
            except (requests.RequestException, ImmichError) as exc:
                last_exc = exc
                wait = 4 ** i  # 1s, 4s, 16s
                logger.warning("attempt %d/%d failed (%s), retrying in %ds", i + 1, attempts, exc, wait)
                log_event("WARNING", "immich_retry", attempt=i + 1, total=attempts, error=str(exc)[:200])
                time.sleep(wait)
        log_event("ERROR", "immich_giveup", error=str(last_exc)[:200], attempts=attempts)
        raise ImmichError(f"giving up after {attempts} attempts: {last_exc}")

    def _fetch_album_page(self, page: int) -> dict[str, Any]:
        url = f"{self.base_url}/api/search/metadata"
        body = {"albumIds": [self.album_id], "withExif": True, "page": page}
        r = self._session.post(url, json=body, timeout=self.timeout)
        if r.status_code != 200:
            raise ImmichError(f"POST {url} (page {page}) -> {r.status_code}: {r.text[:200]}")
        return r.json()

    def _fetch_original(self, asset_id: str) -> bytes:
        url = f"{self.base_url}/api/assets/{asset_id}/original"
        r = self._session.get(url, timeout=self.timeout)
        if r.status_code != 200:
            raise ImmichError(f"download {asset_id} -> {r.status_code}: {r.text[:200]}")
        return r.content
