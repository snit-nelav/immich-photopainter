"""Cycle entry point: ``python -m photopainter``.

Flags:
  --dry-run             write a preview to /tmp instead of pushing the panel
  --force-asset <UUID>  pick this specific asset (skips random + history)
  --clear               send a clear screen and exit
  --ignore-schedule     bypass the active-hours and interval check
  --purge-cache         purge LRU cache to its max_size_gb and exit
"""
from __future__ import annotations

import argparse
import fcntl
import logging
import logging.handlers
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from photopainter.config import load_config, Config
from photopainter.history import History
from photopainter.scheduler import should_refresh_now, write_last_status
from photopainter import image_processor
from photopainter.display import Display, WaveshareDisplay, MockDisplay
from photopainter.sources.base import Asset
from photopainter.sources.immich import ImmichSource
from photopainter.sources.cached import CachingSource
from photopainter.cache import AssetCache, gb_to_bytes

LOCK_PATH = Path("/run/photopainter/refresh.lock")
LAST_STATUS_PATH = Path("/var/lib/photopainter/last_status.json")
PREVIEW_PATH = Path("/tmp/photopainter-preview.png")
CONFIG_PATH = Path(os.environ.get("PHOTOPAINTER_CONFIG", "/etc/photopainter/config.yaml"))

MAX_PROCESS_RETRIES = 3


def setup_logging(cfg: Config) -> None:
    level_str = os.environ.get("PHOTOPAINTER_LOG_LEVEL", cfg.logging.level)
    level = getattr(logging, level_str.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    for h in list(root.handlers):
        root.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    root.addHandler(sh)
    try:
        cfg.logging.path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.WatchedFileHandler(cfg.logging.path)
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError as exc:
        logging.warning("file logging disabled: %s", exc)


def acquire_lock() -> int:
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(LOCK_PATH, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BlockingIOError:
        os.close(fd)
        raise


def build_source(cfg: Config) -> CachingSource:
    if cfg.sources.active != "immich":
        raise NotImplementedError(f"source '{cfg.sources.active}' not implemented yet")
    icfg = cfg.sources.immich
    upstream = ImmichSource(
        base_url=icfg.base_url,
        api_key=icfg.api_key,
        album_id=icfg.album_id,
        timeout_seconds=icfg.timeout_seconds,
    )
    cache = AssetCache(cfg.cache.path, gb_to_bytes(cfg.cache.max_size_gb))
    return CachingSource(upstream, cache)


def _canvas_size(cfg: Config) -> tuple[int, int]:
    """Return the logical canvas size (w, h) given the physical frame rotation.
    Portrait for 0/180, landscape for 90/270."""
    if cfg.display.rotation in (0, 180):
        return cfg.display.canvas_width, cfg.display.canvas_height
    return cfg.display.canvas_height, cfg.display.canvas_width


def _try_process(
    source: CachingSource,
    cfg: Config,
    asset: Asset,
    canvas_w: int,
    canvas_h: int,
) -> tuple[bytes, "Image.Image"] | None:  # type: ignore[name-defined]
    """Download + process one asset. Returns (raw, rendered) on success, None on failure."""
    log = logging.getLogger("photopainter.cycle")
    try:
        raw = source.download(asset.id)
    except Exception as exc:
        log.warning("download failed for %s: %s", asset.id, exc)
        return None
    try:
        rendered = image_processor.process(
            raw, canvas_w, canvas_h,
            cfg.display.rotation,
            cfg.display.compatible_mode,
            cfg.display.inverted_mode,
            cfg.display.background_color,
        )
    except Exception as exc:
        log.warning("image processing failed for %s: %s", asset.id, exc)
        return None
    return raw, rendered


def cycle(cfg: Config, display: Display, force_asset: str | None = None) -> int:
    log = logging.getLogger("photopainter.cycle")
    history = History(cfg.history.path, cfg.history.max_size)
    timings: dict[str, float] = {}

    t = time.perf_counter()
    source = build_source(cfg)
    all_assets = source.list_assets()
    timings["fetch_list"] = time.perf_counter() - t
    if source.fallback_used:
        log.warning("DEGRADED MODE: upstream unreachable, drawing from cache (%d assets)", len(all_assets))

    images = [a for a in all_assets if a.type == "IMAGE"]
    if not images:
        log.error("no IMAGE assets available (neither upstream nor cache)")
        write_last_status(LAST_STATUS_PATH, "", timings, "no_assets")
        return 2

    canvas_w, canvas_h = _canvas_size(cfg)

    chosen: Asset | None = None
    rendered = None
    attempted_ids: set[str] = set()

    if force_asset:
        cands = [a for a in images if a.id == force_asset]
        if not cands:
            log.error("forced asset %s not found", force_asset)
            write_last_status(LAST_STATUS_PATH, force_asset, timings, "force_asset_not_found")
            return 3
        chosen = cands[0]
        t = time.perf_counter()
        result = _try_process(source, cfg, chosen, canvas_w, canvas_h)
        timings.setdefault("download", 0.0)
        timings.setdefault("process", time.perf_counter() - t)
        if result is None:
            log.error("forced asset %s could not be processed", force_asset)
            write_last_status(LAST_STATUS_PATH, force_asset, timings, "force_asset_process_failed")
            return 4
        _, rendered = result
    else:
        # Try up to MAX_PROCESS_RETRIES different assets if download/decode fails.
        for attempt in range(1, MAX_PROCESS_RETRIES + 1):
            if len(images) > cfg.history.max_size:
                pool = [a for a in images if not history.contains(a.id) and a.id not in attempted_ids]
                if not pool:
                    pool = [a for a in images if a.id not in attempted_ids]
            else:
                pool = [a for a in images if a.id not in attempted_ids]
            if not pool:
                log.warning("no more candidate assets to try (after %d attempts)", attempt - 1)
                break
            candidate = random.choice(pool)
            attempted_ids.add(candidate.id)
            log.info("attempt %d/%d: %s (%s)", attempt, MAX_PROCESS_RETRIES, candidate.id, candidate.filename or "n/a")
            t_attempt = time.perf_counter()
            result = _try_process(source, cfg, candidate, canvas_w, canvas_h)
            if result is not None:
                _, rendered = result
                chosen = candidate
                timings.setdefault("download", 0.0)
                timings["process"] = time.perf_counter() - t_attempt
                break
        # Fallback: if all retries failed, draw from local cache directly.
        if rendered is None:
            log.warning("all %d attempts failed, falling back to local cache for the next picture", MAX_PROCESS_RETRIES)
            cache = AssetCache(cfg.cache.path, gb_to_bytes(cfg.cache.max_size_gb))
            cache_pool = [aid for aid in cache.list_ids() if aid not in attempted_ids]
            if not cache_pool:
                log.error("no usable asset in cache either, giving up this cycle")
                write_last_status(LAST_STATUS_PATH, "", timings, "image_failed_after_retries")
                return 0
            cache_id = random.choice(cache_pool)
            chosen = Asset(id=cache_id, type="IMAGE", filename="from_cache_fallback")
            t = time.perf_counter()
            try:
                raw = cache.get(cache_id)
                if raw is None:
                    raise RuntimeError("cache file disappeared between list and get")
                rendered = image_processor.process(
                    raw, canvas_w, canvas_h,
                    cfg.display.rotation, cfg.display.compatible_mode,
                    cfg.display.inverted_mode, cfg.display.background_color,
                )
            except Exception as exc:
                log.error("cache fallback failed: %s", exc)
                write_last_status(LAST_STATUS_PATH, cache_id, timings, f"cache_fallback_failed: {exc}")
                return 0
            timings["process"] = time.perf_counter() - t

    assert chosen is not None and rendered is not None

    t = time.perf_counter()
    try:
        display.push(rendered, cfg.display.rotation)
    except Exception as exc:
        log.error("display push failed: %s", exc)
        write_last_status(LAST_STATUS_PATH, chosen.id, timings, f"display_failed: {exc}")
        return 5
    timings["display"] = time.perf_counter() - t
    log.info("display push completed in %.2fs", timings["display"])

    # Only update the live preview after a successful hardware push so it always
    # reflects what is actually on the panel.
    if not isinstance(display, MockDisplay):
        try:
            PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
            rendered.save(PREVIEW_PATH, format="PNG")
        except OSError as exc:
            log.warning("preview save failed: %s", exc)

    history.add(chosen.id)
    status = "success_fallback" if source.fallback_used else "success"
    write_last_status(LAST_STATUS_PATH, chosen.id, timings, status)
    log.info("cycle OK (total %.2fs, status=%s)", sum(timings.values()), status)
    return 0


def purge_cache(cfg: Config) -> int:
    log = logging.getLogger("photopainter.purge")
    cache = AssetCache(cfg.cache.path, gb_to_bytes(cfg.cache.max_size_gb))
    before_count, before_size = cache.file_count(), cache.total_size()
    removed, freed = cache.purge_excess()
    log.info(
        "purge: %d->%d files (-%d), %.2f->%.2f MB (freed %.2f MB)",
        before_count, cache.file_count(), removed,
        before_size / 1024 / 1024, cache.total_size() / 1024 / 1024, freed / 1024 / 1024,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="photopainter")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-asset")
    ap.add_argument("--clear", action="store_true")
    ap.add_argument("--ignore-schedule", action="store_true")
    ap.add_argument("--purge-cache", action="store_true")
    args = ap.parse_args(argv)

    try:
        cfg = load_config(CONFIG_PATH)
    except Exception as exc:
        print(f"invalid config: {exc}", file=sys.stderr)
        return 1
    setup_logging(cfg)
    log = logging.getLogger("photopainter.main")

    if args.purge_cache:
        return purge_cache(cfg)

    try:
        lock_fd = acquire_lock()
    except BlockingIOError:
        log.info("another refresh is in progress (lock held), exit 0")
        return 0

    try:
        if args.clear:
            display: Display = MockDisplay() if args.dry_run else WaveshareDisplay()
            display.clear()
            return 0

        if not args.ignore_schedule and not args.force_asset:
            do_refresh, reason = should_refresh_now(
                datetime.now(timezone.utc),
                cfg.scheduling.active_hours_start, cfg.scheduling.active_hours_end,
                cfg.scheduling.refresh_interval_minutes, LAST_STATUS_PATH,
            )
            if not do_refresh:
                log.info("skip: %s", reason)
                return 0
            log.info("refresh allowed: %s", reason)

        display = MockDisplay() if args.dry_run else WaveshareDisplay()
        return cycle(cfg, display, args.force_asset)
    finally:
        try:
            os.close(lock_fd)
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
