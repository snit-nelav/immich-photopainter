"""Display abstraction layer for the Waveshare epd7in3e panel.

The panel itself is fixed 800x480 landscape, with the ribbon connector on one
side. The "logical canvas" the upstream pipeline draws on can be either:

  - 480x800 portrait (when the user mounts the frame in portrait, rotation 0 or 180)
  - 800x480 landscape (when the user mounts in landscape, rotation 90 or 270)

This module is responsible for mapping the logical canvas onto the panel-native
buffer for each of the four rotations.

`MockDisplay` saves the image to a separate file (NOT the live preview) so that
dry-run cycles never leak into /api/preview.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)


class Display(ABC):
    @abstractmethod
    def push(self, img: Image.Image, rotation: int) -> None: ...
    @abstractmethod
    def clear(self) -> None: ...


def _map_canvas_to_panel(img: Image.Image, rotation: int, panel_w: int, panel_h: int) -> Image.Image:
    """Rotate the canvas-shaped image into the panel-native 800x480 buffer."""
    # Portrait canvas: 480x800. Panel is 800x480 landscape, so rotate.
    if img.size == (panel_h, panel_w):
        if rotation == 0:
            return img.rotate(-90, expand=True)   # portrait → landscape, "top" stays on top
        if rotation == 180:
            return img.rotate(90, expand=True)    # portrait reversed
        raise ValueError(f"portrait canvas requires rotation in (0, 180), got {rotation}")
    # Landscape canvas: 800x480, already panel-shaped.
    if img.size == (panel_w, panel_h):
        if rotation == 90:
            return img
        if rotation == 270:
            return img.rotate(180, expand=False)
        raise ValueError(f"landscape canvas requires rotation in (90, 270), got {rotation}")
    raise ValueError(f"image size {img.size} does not match panel {panel_w}x{panel_h} or its rotation")


class WaveshareDisplay(Display):
    def __init__(self) -> None:
        from waveshare_epd import epd7in3e
        self._epd_mod = epd7in3e
        self._epd = epd7in3e.EPD()
        self._initialized = False

    def _ensure_init(self) -> None:
        if not self._initialized:
            ret = self._epd.init()
            if ret != 0:
                raise RuntimeError(f"epd.init() returned {ret}")
            self._initialized = True

    def push(self, img: Image.Image, rotation: int) -> None:
        self._ensure_init()
        panel_w, panel_h = self._epd.width, self._epd.height  # 800, 480
        final = _map_canvas_to_panel(img, rotation, panel_w, panel_h)
        logger.debug("push buffer to panel (%dx%d, rotation %d)", final.width, final.height, rotation)
        self._epd.display(self._epd.getbuffer(final))
        self._epd.sleep()

    def clear(self) -> None:
        self._ensure_init()
        logger.warning("epd.Clear() — uses screen charge cycles, use sparingly")
        self._epd.Clear()
        self._epd.sleep()


class MockDisplay(Display):
    """Headless replacement that writes a PNG instead of touching the panel."""

    DEFAULT_DRYRUN_PATH = Path("/tmp/photopainter-preview-dryrun.png")

    def __init__(self, dryrun_path: Path = DEFAULT_DRYRUN_PATH) -> None:
        self.dryrun_path = dryrun_path

    def push(self, img: Image.Image, rotation: int) -> None:
        logger.info("MockDisplay: skipping hardware, writing dry-run preview to %s", self.dryrun_path)
        # We save the image as-is in canvas orientation — the dry-run preview is
        # meant to show what gets rendered, not how it would land on the panel.
        self.dryrun_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(self.dryrun_path, format="PNG")

    def clear(self) -> None:
        logger.info("MockDisplay: clear (no-op)")
