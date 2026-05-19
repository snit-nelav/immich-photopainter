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


class SourcesConfig(BaseModel):
    active: str = "immich"
    immich: ImmichConfig


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

    @field_validator("rotation")
    @classmethod
    def validate_rotation(cls, v: int) -> int:
        if v not in ALLOWED_ROTATIONS:
            raise ValueError(f"rotation must be one of {ALLOWED_ROTATIONS}")
        return v


class SchedulingConfig(BaseModel):
    active_hours_start: int = 6
    active_hours_end: int = 24
    refresh_interval_minutes: int = 15

    @field_validator("refresh_interval_minutes")
    @classmethod
    def validate_interval(cls, v: int) -> int:
        if v not in ALLOWED_INTERVALS:
            raise ValueError(f"refresh_interval_minutes must be one of {ALLOWED_INTERVALS}")
        return v


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
    return Config.model_validate(raw)


def dump_config(cfg: Config, path: Path = Path("/etc/photopainter/config.yaml")) -> None:
    """Atomic YAML write (tmp file + rename)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = cfg.model_dump(mode="json")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(path)
