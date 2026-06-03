"""Configuration parsing + validation via pydantic."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


ALLOWED_INTERVALS = (5, 10, 15, 20, 30, 45, 60)
ALLOWED_ROTATIONS = (0, 90, 180, 270)
DisplayMode = Literal["fill", "square", "original"]


class ImmichConfig(BaseModel):
    base_url: str
    api_key: str = ""
    album_id: str = ""
    timeout_seconds: int = 30

    @field_validator("base_url")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")


class LocalConfig(BaseModel):
    # Where photos uploaded via the Local tab live on disk. Created by install.sh
    # and owned by the photopainter user.
    path: Path = Path("/var/lib/photopainter/local")


class SourcesConfig(BaseModel):
    active: Literal["immich", "local"] = "immich"
    immich: ImmichConfig
    local: LocalConfig = Field(default_factory=LocalConfig)


class DisplayConfig(BaseModel):
    # The native panel is fixed 800x480 landscape. The logical canvas the image
    # pipeline draws on depends on the frame rotation: portrait (480x800) for
    # rotation in {0, 180}, landscape (800x480) for rotation in {90, 270}.
    canvas_width: int = 480
    canvas_height: int = 800
    rotation: int = 0
    compatible_mode: DisplayMode = "fill"
    inverted_mode: DisplayMode = "original"
    background_color: Literal["white", "black"] = "white"
    # PIL ImageEnhance factors applied before dithering. 1.0 = identity.
    # 0.0 zeroes the channel (B&W for saturation, full blur for sharpness);
    # 2.0 doubles it. Useful to compensate for the muted Spectra 6 palette.
    brightness: float = 1.0
    saturation: float = 1.0
    sharpness: float = 1.0

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, v: int) -> int:
        if v not in ALLOWED_ROTATIONS:
            raise ValueError(f"rotation must be one of {ALLOWED_ROTATIONS}")
        return v

    @field_validator("brightness", "saturation", "sharpness")
    @classmethod
    def validate_enhance(cls, v: float) -> float:
        if not (0.0 <= v <= 2.0):
            raise ValueError("enhancement factors must be in [0.0, 2.0]")
        return float(v)


def _default_active_hours() -> list[list[bool]]:
    """Default schedule: every hour of every day is active."""
    return [[True] * 24 for _ in range(7)]


class SchedulingConfig(BaseModel):
    refresh_interval_minutes: int = 15
    # 7 rows (Monday .. Sunday, ISO weekday 0-6) × 24 columns (hour 0-23).
    # Cell value True = the refresh runs during that hour, False = silent.
    active_hours: list[list[bool]] = Field(default_factory=_default_active_hours)

    @field_validator("refresh_interval_minutes")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        if v not in ALLOWED_INTERVALS:
            raise ValueError(f"refresh_interval_minutes must be one of {ALLOWED_INTERVALS}")
        return v

    @field_validator("active_hours")
    @classmethod
    def validate_active_hours(cls, v: list[list[bool]]) -> list[list[bool]]:
        if len(v) != 7 or any(len(row) != 24 for row in v):
            raise ValueError("active_hours must be a 7×24 matrix")
        return [[bool(c) for c in row] for row in v]


class HistoryConfig(BaseModel):
    max_size: int = 20
    path: Path = Path("/var/lib/photopainter/history.json")


class CacheConfig(BaseModel):
    path: Path = Path("/var/cache/photopainter")
    max_size_gb: float = 2.0

    @field_validator("max_size_gb")
    @classmethod
    def validate_size(cls, v: float) -> float:
        if not (1.0 <= v <= 10.0):
            raise ValueError("max_size_gb must be between 1.0 and 10.0")
        return float(v)


class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    path: Path = Path("/var/log/photopainter/photopainter.log")


class WebConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 80
    enabled: bool = True


class UIConfig(BaseModel):
    language: Literal["en", "fr"] = "en"


class Config(BaseModel):
    sources: SourcesConfig
    display: DisplayConfig = Field(default_factory=DisplayConfig)
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig)
    history: HistoryConfig = Field(default_factory=HistoryConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    ui: UIConfig = Field(default_factory=UIConfig)


def load_config(path: Path = Path("/etc/photopainter/config.yaml")) -> Config:
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    _migrate_legacy_scheduling(raw)
    return Config.model_validate(raw)


def _migrate_legacy_scheduling(raw: dict) -> None:
    """Translate the legacy pause_enabled/start/end fields into an
    active_hours matrix in place. No-op if active_hours is already set."""
    sch = raw.get("scheduling") or {}
    if "active_hours" in sch:
        return
    enabled = sch.pop("pause_enabled", False)
    start = sch.pop("pause_start_hour", 0)
    end = sch.pop("pause_end_hour", 0)
    grid = [[True] * 24 for _ in range(7)]
    if enabled and start != end:
        for h in range(24):
            in_pause = (
                (start < end and start <= h < end)
                or (start > end and (h >= start or h < end))
            )
            if in_pause:
                for d in range(7):
                    grid[d][h] = False
    sch["active_hours"] = grid
    raw["scheduling"] = sch


def dump_config(cfg: Config, path: Path = Path("/etc/photopainter/config.yaml")) -> None:
    """Atomic YAML write (tmp file + rename)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = cfg.model_dump(mode="json")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(path)
