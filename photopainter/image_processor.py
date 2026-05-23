"""Image pipeline: EXIF transpose -> orientation match -> fill/square/original mode
-> Floyd-Steinberg dithering against the 6-color Spectra palette.

Modes (per orientation case):
  - fill     : center crop that fills the whole canvas (loses borders, no bands)
  - square   : 1:1 center crop, pasted centered on a solid background
  - original : full photo preserved, fitted (letterbox) on a solid background

The canvas dimensions are passed in by the caller — they depend on the frame
rotation. Portrait canvas is 480x800, landscape canvas is 800x480.
"""
from __future__ import annotations

import io
import logging
from typing import Literal

from PIL import Image, ImageEnhance, ImageOps

logger = logging.getLogger(__name__)

DisplayMode = Literal["fill", "square", "original"]

# Spectra 6 palette — these are the only colors the panel can render.
PALETTE_E6: list[tuple[int, int, int]] = [
    (0, 0, 0),         # black
    (255, 255, 255),   # white
    (255, 255, 0),     # yellow
    (255, 0, 0),       # red
    (0, 0, 255),       # blue
    (0, 255, 0),       # green
]


def _make_palette_image() -> Image.Image:
    pal = Image.new("P", (1, 1))
    flat = [c for rgb in PALETTE_E6 for c in rgb]
    flat += [0] * (768 - len(flat))
    pal.putpalette(flat)
    return pal


_PALETTE_CACHE = _make_palette_image()


def _is_compatible(src_w: int, src_h: int, canvas_w: int, canvas_h: int) -> bool:
    """A photo is "compatible" with the canvas if both share an orientation,
    or if the photo is roughly square (±10%)."""
    src_ratio = src_w / src_h
    if 0.9 <= src_ratio <= 1.1:
        return True
    src_portrait = src_h > src_w
    canvas_portrait = canvas_h > canvas_w
    return src_portrait == canvas_portrait


def _bg_rgb(color: Literal["white", "black"]) -> tuple[int, int, int]:
    return (255, 255, 255) if color == "white" else (0, 0, 0)


def _fill(img: Image.Image, canvas_w: int, canvas_h: int) -> Image.Image:
    """Center crop that fills the canvas. Borders of the source are lost."""
    return ImageOps.fit(img, (canvas_w, canvas_h), method=Image.LANCZOS, centering=(0.5, 0.5))


def _square(img: Image.Image, canvas_w: int, canvas_h: int, bg: Literal["white", "black"]) -> Image.Image:
    """Crop a centered 1:1 square out of the source, paste in the middle of the
    canvas on a solid background."""
    side = min(img.width, img.height)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    sq = img.crop((left, top, left + side, top + side))
    target_side = min(canvas_w, canvas_h)
    sq = sq.resize((target_side, target_side), Image.LANCZOS)
    canvas = Image.new("RGB", (canvas_w, canvas_h), _bg_rgb(bg))
    offset = ((canvas_w - target_side) // 2, (canvas_h - target_side) // 2)
    canvas.paste(sq, offset)
    return canvas


def _original(img: Image.Image, canvas_w: int, canvas_h: int, bg: Literal["white", "black"]) -> Image.Image:
    """Letterbox: preserve the whole source, fit into the canvas, pad with solid bg."""
    fitted = ImageOps.contain(img, (canvas_w, canvas_h), method=Image.LANCZOS)
    canvas = Image.new("RGB", (canvas_w, canvas_h), _bg_rgb(bg))
    offset = ((canvas_w - fitted.width) // 2, (canvas_h - fitted.height) // 2)
    canvas.paste(fitted, offset)
    return canvas


def _apply_mode(img: Image.Image, canvas_w: int, canvas_h: int, mode: DisplayMode, bg: Literal["white", "black"]) -> Image.Image:
    if mode == "fill":
        return _fill(img, canvas_w, canvas_h)
    if mode == "square":
        return _square(img, canvas_w, canvas_h, bg)
    if mode == "original":
        return _original(img, canvas_w, canvas_h, bg)
    raise ValueError(f"unknown display mode: {mode}")


def _apply_enhancements(img: Image.Image, brightness: float, saturation: float, sharpness: float) -> Image.Image:
    """Apply user-controlled image enhancements before quantization.
    A factor of 1.0 is a no-op so the default path is unchanged."""
    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    if saturation != 1.0:
        img = ImageEnhance.Color(img).enhance(saturation)
    if sharpness != 1.0:
        img = ImageEnhance.Sharpness(img).enhance(sharpness)
    return img


def process(
    raw_bytes: bytes,
    canvas_width: int,
    canvas_height: int,
    rotation: int,
    compatible_mode: DisplayMode,
    inverted_mode: DisplayMode,
    background_color: Literal["white", "black"],
    brightness: float = 1.0,
    saturation: float = 1.0,
    sharpness: float = 1.0,
) -> Image.Image:
    """Return an RGB PIL image (canvas-shaped) dithered against the E6 palette."""
    img = Image.open(io.BytesIO(raw_bytes))
    img = ImageOps.exif_transpose(img).convert("RGB")
    src_w, src_h = img.size
    compatible = _is_compatible(src_w, src_h, canvas_width, canvas_height)
    mode: DisplayMode = compatible_mode if compatible else inverted_mode
    logger.info(
        "source %dx%d, canvas %dx%d, rotation %d, compatible=%s, mode=%s, bg=%s, b=%.2f s=%.2f sh=%.2f",
        src_w, src_h, canvas_width, canvas_height, rotation, compatible, mode, background_color,
        brightness, saturation, sharpness,
    )
    rendered = _apply_mode(img, canvas_width, canvas_height, mode, background_color)
    rendered = _apply_enhancements(rendered, brightness, saturation, sharpness)
    quantized = rendered.quantize(palette=_PALETTE_CACHE, dither=Image.FLOYDSTEINBERG)
    return quantized.convert("RGB")
