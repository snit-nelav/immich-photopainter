"""Flask app: REST API + static HTML UI.

The POST /api/config endpoint compares the incoming patch against the current
config and triggers an automatic refresh according to which fields changed:

  - Album / API URL / API key / interval / source.active  -> "new_photo"
    (forces a fresh random pick, even if the schedule hasn't elapsed)
  - Rotation / display modes / background_color           -> "redraw"
    (re-renders the LAST asset with the new display settings, no new pick)
  - Language / cache size / etc.                          -> no refresh
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

import requests
from flask import Flask, jsonify, request, send_file, send_from_directory, abort

from photopainter.config import load_config, dump_config, Config, ALLOWED_INTERVALS, ALLOWED_ROTATIONS
from photopainter.cache import AssetCache, gb_to_bytes
from photopainter import events_log
from photopainter.last_seen import LastSeen
from photopainter.scheduler import read_last_status

logger = logging.getLogger(__name__)

CONFIG_PATH = Path("/etc/photopainter/config.yaml")
LAST_STATUS_PATH = Path("/var/lib/photopainter/last_status.json")
HISTORY_PATH = Path("/var/lib/photopainter/history.json")
# Preview file lives on the persistent volume so it survives a reboot
# (was previously /tmp which is tmpfs and wiped on Trixie).
PREVIEW_PATH = Path("/var/lib/photopainter/preview.png")
REFRESH_SH = "/opt/photopainter/refresh.sh"
STATIC_DIR = Path(__file__).parent / "static"


def _mask_secrets(data: dict) -> dict:
    if "immich" in data.get("sources", {}):
        ak = data["sources"]["immich"].get("api_key", "")
        if ak:
            data["sources"]["immich"]["api_key"] = ak[:4] + "***" + ak[-4:] if len(ak) > 8 else "***"
    return data


def _source_context_changed(old: dict, new: dict) -> bool:
    """True if the user switched source or picked a different album within the
    same source — both reset the universe of photos, so the per-asset last_seen
    history should be wiped to give the new context a fresh, uniform first cycle."""
    old_im = old.get("sources", {}).get("immich", {})
    new_im = new.get("sources", {}).get("immich", {})
    return (
        old.get("sources", {}).get("active") != new.get("sources", {}).get("active")
        or old_im.get("album_id") != new_im.get("album_id")
    )


def _categorize_change(old: dict, new: dict) -> str:
    """Returns 'new_photo', 'redraw', or 'none'."""
    old_im = old.get("sources", {}).get("immich", {})
    new_im = new.get("sources", {}).get("immich", {})
    old_sch = old.get("scheduling", {})
    new_sch = new.get("scheduling", {})
    if (old.get("sources", {}).get("active") != new.get("sources", {}).get("active")
        or old_im.get("base_url") != new_im.get("base_url")
        or old_im.get("api_key") != new_im.get("api_key")
        or old_im.get("album_id") != new_im.get("album_id")
        or old_sch.get("refresh_interval_minutes") != new_sch.get("refresh_interval_minutes")
        or old_sch.get("active_hours") != new_sch.get("active_hours")):
        return "new_photo"

    old_d = old.get("display", {})
    new_d = new.get("display", {})
    for k in ("rotation", "compatible_mode", "inverted_mode", "background_color",
              "brightness", "saturation", "sharpness"):
        if old_d.get(k) != new_d.get(k):
            return "redraw"
    return "none"


def _spawn_refresh(extra_args: list[str]) -> tuple[int | None, str | None]:
    """Spawn refresh.sh in the background. Returns (pid, early_error).

    We give the subprocess a short grace period (0.4s) before returning, just
    enough to catch early crashes like a missing dependency or a permission
    error on the lock dir. The subprocess keeps running afterwards.
    """
    import time
    try:
        proc = subprocess.Popen(
            [REFRESH_SH] + extra_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except FileNotFoundError:
        return None, "refresh.sh not found"

    time.sleep(0.4)
    rc = proc.poll()
    if rc is not None and rc != 0:
        # The subprocess already exited with an error code.
        out_bytes = b""
        try:
            if proc.stdout is not None:
                out_bytes = proc.stdout.read(2048) or b""
        except Exception:
            pass
        tail = out_bytes.decode("utf-8", errors="replace").strip().splitlines()[-3:]
        return proc.pid, f"exit {rc}: {' | '.join(tail)[:300]}"
    return proc.pid, None


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    @app.route("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.route("/static/<path:path>")
    def static_files(path):
        return send_from_directory(STATIC_DIR, path)

    @app.get("/api/config")
    def get_config():
        cfg = load_config(CONFIG_PATH)
        data = _mask_secrets(cfg.model_dump(mode="json"))
        data["_meta"] = {
            "allowed_intervals": list(ALLOWED_INTERVALS),
            "allowed_rotations": list(ALLOWED_ROTATIONS),
            "display_modes": ["fill", "square", "original"],
        }
        return jsonify(data)

    @app.post("/api/config")
    def post_config():
        current = load_config(CONFIG_PATH)
        old_snapshot = current.model_dump(mode="json")
        patch = request.get_json(force=True, silent=False) or {}
        merged = current.model_dump(mode="json")

        for section, values in patch.items():
            if section == "_meta":
                continue
            if isinstance(values, dict) and isinstance(merged.get(section), dict):
                # Preserve unchanged secrets that the UI sent back masked.
                if section == "sources" and "immich" in values:
                    new_val = values["immich"].get("api_key", "")
                    if new_val and "***" in new_val:
                        values["immich"]["api_key"] = merged[section]["immich"]["api_key"]
                for k, v in values.items():
                    if isinstance(v, dict) and isinstance(merged[section].get(k), dict):
                        merged[section][k].update(v)
                    else:
                        merged[section][k] = v
            else:
                merged[section] = values

        try:
            new_cfg = Config.model_validate(merged)
        except Exception as exc:
            return jsonify({"error": "validation_failed", "details": str(exc)}), 400
        dump_config(new_cfg, CONFIG_PATH)
        logger.info("config updated via UI")

        if _source_context_changed(old_snapshot, merged):
            LastSeen(new_cfg.history.path.parent / "last_seen.json").clear()
            logger.info("last_seen wiped (source or album changed)")

        category = _categorize_change(old_snapshot, merged)
        # Caller may force a redraw even when nothing changed (used by the
        # "Live preview" button so the user can iterate on enhancement sliders).
        if patch.get("_force_redraw") and category == "none":
            category = "redraw"
        triggered_pid: int | None = None
        trigger_error: str | None = None
        if category == "new_photo":
            triggered_pid, trigger_error = _spawn_refresh(["--ignore-schedule"])
        elif category == "redraw":
            last = read_last_status(LAST_STATUS_PATH)
            if last and last.get("asset_id"):
                triggered_pid, trigger_error = _spawn_refresh(["--force-asset", last["asset_id"], "--ignore-schedule"])
            else:
                triggered_pid, trigger_error = _spawn_refresh(["--ignore-schedule"])

        return jsonify({"status": "ok", "refresh": category, "pid": triggered_pid, "trigger_error": trigger_error})

    @app.get("/api/sources")
    def list_sources():
        return jsonify({
            "active": load_config(CONFIG_PATH).sources.active,
            "available": [
                {"id": "immich", "name": "Immich", "implemented": True},
                {"id": "google_photos", "name": "Google Photos", "implemented": False},
                {"id": "local_directory", "name": "Local upload", "implemented": False},
            ],
        })

    @app.get("/api/sources/immich/albums")
    def list_immich_albums():
        cfg = load_config(CONFIG_PATH)
        ic = cfg.sources.immich
        if not ic.api_key or not ic.base_url:
            return jsonify({"error": "base_url and api_key required", "albums": []}), 400
        try:
            r = requests.get(
                f"{ic.base_url}/api/albums",
                headers={"x-api-key": ic.api_key},
                timeout=5,
            )
        except requests.RequestException as exc:
            return jsonify({"error": f"Immich call failed: {exc}", "albums": []}), 502
        if r.status_code != 200:
            return jsonify({"error": f"Immich HTTP {r.status_code}", "albums": []}), 502
        albums = [
            {"id": a["id"], "name": a.get("albumName", "?"), "count": a.get("assetCount", 0)}
            for a in r.json()
        ]
        albums.sort(key=lambda x: x["name"].lower())
        return jsonify({"albums": albums, "selected": ic.album_id})

    @app.get("/api/cache/info")
    def cache_info():
        cfg = load_config(CONFIG_PATH)
        cache = AssetCache(cfg.cache.path, gb_to_bytes(cfg.cache.max_size_gb))
        return jsonify({
            "max_size_gb": cfg.cache.max_size_gb,
            "used_bytes": cache.total_size(),
            "used_gb": round(cache.total_size() / 1024 / 1024 / 1024, 3),
            "file_count": cache.file_count(),
            "path": str(cfg.cache.path),
        })

    @app.post("/api/cache/clear")
    def cache_clear():
        cfg = load_config(CONFIG_PATH)
        cache = AssetCache(cfg.cache.path, gb_to_bytes(cfg.cache.max_size_gb))
        removed, freed = cache.clear_all()
        events_log.log_event("INFO", "cache_clear_manual",
                              removed=removed, freed_mb=round(freed / 1024 / 1024, 1))
        return jsonify({"status": "ok", "removed": removed, "freed_bytes": freed})

    @app.post("/api/refresh")
    def trigger_refresh():
        pid, err = _spawn_refresh(["--ignore-schedule"])
        if pid is None:
            return jsonify({"error": err or "refresh.sh not found"}), 500
        if err:
            return jsonify({"status": "failed", "pid": pid, "error": err}), 500
        return jsonify({"status": "started", "pid": pid}), 202

    @app.post("/api/clear")
    def trigger_clear():
        pid, err = _spawn_refresh(["--clear"])
        if pid is None:
            return jsonify({"error": err or "refresh.sh not found"}), 500
        if err:
            return jsonify({"status": "failed", "pid": pid, "error": err}), 500
        return jsonify({"status": "started", "pid": pid}), 202

    @app.get("/api/status")
    def get_status():
        if not LAST_STATUS_PATH.exists():
            return jsonify({"status": "never_run"})
        try:
            return jsonify(json.loads(LAST_STATUS_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return jsonify({"status": "corrupted"})

    @app.get("/api/preview")
    def get_preview():
        if not PREVIEW_PATH.exists():
            abort(404)
        return send_file(PREVIEW_PATH, mimetype="image/png")

    @app.get("/api/history")
    def get_history():
        if not HISTORY_PATH.exists():
            return jsonify({"entries": []})
        try:
            return jsonify(json.loads(HISTORY_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return jsonify({"entries": [], "warning": "corrupted"})

    @app.get("/api/logs")
    def get_logs():
        try:
            limit = max(1, min(int(request.args.get("limit", 100)), 500))
        except ValueError:
            limit = 100
        before_ts = request.args.get("before") or None
        entries, has_more = events_log.read_tail(limit=limit, before_ts=before_ts)
        return jsonify({"entries": entries, "has_more": has_more, "limit": limit})

    @app.post("/api/logs/clear")
    def post_clear_logs():
        events_log.clear()
        events_log.log_event("INFO", "logs_cleared")
        return jsonify({"status": "ok"})

    @app.post("/api/reboot")
    def post_reboot():
        """Reboot the Pi. Returns immediately; the actual reboot happens a few
        seconds later so the HTTP response can be sent first."""
        events_log.log_event("INFO", "reboot_requested")
        try:
            subprocess.Popen(
                ["sudo", "-n", "shutdown", "-r", "+0", "Manual reboot from photopainter UI"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:
            events_log.log_event("ERROR", "reboot_failed", error=str(exc))
            return jsonify({"error": str(exc)}), 500
        return jsonify({"status": "rebooting"}), 202

    @app.post("/api/shutdown")
    def post_shutdown():
        """Halt the Pi. The frame keeps its last image (e-paper)."""
        events_log.log_event("INFO", "shutdown_requested")
        try:
            subprocess.Popen(
                ["sudo", "-n", "shutdown", "-h", "+0", "Manual shutdown from photopainter UI"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except Exception as exc:
            events_log.log_event("ERROR", "shutdown_failed", error=str(exc))
            return jsonify({"error": str(exc)}), 500
        return jsonify({"status": "shutting_down"}), 202

    return app


app = create_app()
