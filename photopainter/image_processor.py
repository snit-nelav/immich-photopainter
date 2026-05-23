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

from PIL import Image, ImageDraw, ImageEnhance, ImageOps

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


# Feather Icons (https://feathericons.com, MIT license).
# Stroke color forced to pure red so it maps cleanly onto the Spectra 6 palette.
_SVG_WIFI_OFF = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24" fill="none" stroke="#FF0000" stroke-width="2.5" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<line x1="1" y1="1" x2="23" y2="23"/>'
    '<path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55"/>'
    '<path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39"/>'
    '<path d="M10.71 5.05A16 16 0 0 1 22.58 9"/>'
    '<path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88"/>'
    '<path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>'
    '<line x1="12" y1="20" x2="12.01" y2="20"/>'
    '</svg>'
)
_SVG_ALERT = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24" fill="none" stroke="#FF0000" stroke-width="2.5" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>'
    '<line x1="12" y1="9" x2="12" y2="13"/>'
    '<line x1="12" y1="17" x2="12.01" y2="17"/>'
    '</svg>'
)


def _render_svg(svg: str, size: int) -> Image.Image:
    """Rasterize an SVG string to a PIL RGBA image of (size, size)."""
    import cairosvg
    png_bytes = cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        output_width=size,
        output_height=size,
    )
    return Image.open(io.BytesIO(png_bytes)).convert("RGBA")


# Per-kind tuning (icon size + visual centering offset from geometric center).
# Values found by trial on the 7.3" panel (5 px/mm). The Feather pictograms
# are not perfectly balanced inside their 24×24 viewBox so each one has its
# own small (off_x, off_y) correction.
_BADGE_KIND = {
    "wifi":  {"svg": "WIFI_OFF", "icon": 16, "off_x": 1, "off_y": 2},
    "alert": {"svg": "ALERT",    "icon": 16, "off_x": 1, "off_y": 0},
}


def _draw_error_badge(img: Image.Image, kind: str = "wifi") -> None:
    """Draw an error badge in the bottom-left corner of the canvas.

    33 px white disc (≈ 6.6 mm at 5 px/mm) with a thin black border and a red
    Feather icon inside. The icon is selected by ``kind``:
      - "wifi"  -> wifi-off
      - "alert" -> alert-triangle

    Drawn after Floyd-Steinberg dithering so the disc stays solid white.
    """
    BADGE = 33
    MARGIN = 16
    x0 = MARGIN
    y0 = img.height - MARGIN - BADGE

    # White disc with thin black border.
    ImageDraw.Draw(img).ellipse(
        (x0, y0, x0 + BADGE, y0 + BADGE),
        fill=(255, 255, 255), outline=(0, 0, 0), width=2,
    )

    cfg = _BADGE_KIND.get(kind, _BADGE_KIND["wifi"])
    svg = _SVG_ALERT if cfg["svg"] == "ALERT" else _SVG_WIFI_OFF
    icon = _render_svg(svg, cfg["icon"])
    pad_x = (BADGE - cfg["icon"]) // 2 + cfg["off_x"]
    pad_y = (BADGE - cfg["icon"]) // 2 + cfg["off_y"]
    # Threshold the alpha to a binary mask so the icon edges stay crisp on the
    # Spectra 6 palette (no transparent gray that would dither to noise).
    alpha = icon.split()[3].point(lambda v: 255 if v > 128 else 0)
    img.paste(icon.convert("RGB"), (x0 + pad_x, y0 + pad_y), mask=alpha)


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
    show_error_badge: bool = False,
    error_badge_kind: str = "wifi",
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
    final = quantized.convert("RGB")
    if show_error_badge:
        _draw_error_badge(final, kind=error_badge_kind)
    return final
