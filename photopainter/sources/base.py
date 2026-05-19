"""PhotoSource interface — every photo backend implements this Protocol."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class Asset:
    id: str
    type: str          # "IMAGE" (videos are filtered upstream)
    filename: str = ""


@runtime_checkable
class PhotoSource(Protocol):
    name: str

    def list_assets(self) -> list[Asset]: ...
    def download(self, asset_id: str) -> bytes: ...
