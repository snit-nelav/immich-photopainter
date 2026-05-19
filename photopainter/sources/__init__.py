"""Photo sources — abstract interface + concrete implementations."""
from photopainter.sources.base import Asset, PhotoSource
from photopainter.sources.immich import ImmichSource

__all__ = ["PhotoSource", "Asset", "ImmichSource"]
