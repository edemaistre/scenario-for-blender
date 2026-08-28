# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Credentials, filesystem layout and output naming. No bpy."""
import datetime as dt
import os
import pathlib
import re
from dataclasses import dataclass

KIND_SUBDIR = {"image": "images", "video": "videos", "3d": "3d", "material": "materials", "audio": "audio"}

_MIME_EXT = {
    "image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp", "image/gif": "gif",
    "image/avif": "avif", "image/tiff": "tif", "video/mp4": "mp4", "video/webm": "webm",
    "model/gltf-binary": "glb", "model/gltf+json": "gltf", "model/x-fbx": "fbx", "model/obj": "obj",
    "model/spz": "spz", "model/ply": "ply", "application/x-ply": "ply", "model/splat": "splat", "model/stl": "stl", "model/usd": "usdz",
    "model/x-3d-vox": "vox", "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/ogg": "ogg",
    "application/octet-stream": "bin",
}


@dataclass(frozen=True)
class Credentials:
    key: str
    secret: str

    @property
    def valid(self):
        return bool(self.key and self.secret)


def resolve_credentials(pref_key, pref_secret, environ=None):
    environ = os.environ if environ is None else environ
    key = (environ.get("SCENARIO_API_KEY") or pref_key or "").strip()
    secret = (environ.get("SCENARIO_API_SECRET") or pref_secret or "").strip()
    return Credentials(key, secret)


def load_dotenv(path):
    """Minimal KEY=VALUE parser for dev scripts and tests. Never logs values."""
    path = pathlib.Path(path)
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        out[key.strip()] = value
    return out


@dataclass(frozen=True)
class Paths:
    state_dir: pathlib.Path
    cache_dir: pathlib.Path
    output_dir: pathlib.Path

    @property
    def models_cache_dir(self):
        return self.cache_dir / "models"

    @property
    def registry_file(self):
        return self.state_dir / "jobs.json"

    def output_for(self, kind, when=None):
        """`<output>/<kind>/<YYYYMMDD>/`: one folder per kind and per day, so a Downloads folder synced to Dropbox stays browsable."""
        when = when or dt.datetime.now()
        return self.output_dir / KIND_SUBDIR.get(kind, "other") / f"{when:%Y%m%d}"


def ext_for_mime(mime):
    if not mime:
        return "bin"
    return _MIME_EXT.get(mime.split(";")[0].strip().lower(), "bin")


def slug(text, limit=40):
    text = str(text or "")
    if text.startswith("model_"):
        text = text[len("model_"):]
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:limit].rstrip("-") or "model"


def output_filename(kind, model_id, job_id, index, ext, when=None, asset_id=None):
    """`20260828_230353_hitem-3d-split_asset_ccpDR7Ga1…_00.glb`: the Scenario asset id sits in the name so a file
    on disk can be matched to its asset in the web app (Emmanuel, 2026-08-28). Without an asset id, the short job id."""
    when = when or dt.datetime.now()
    tag = asset_id if asset_id else (job_id or "job")[-9:]
    return f"{when:%Y%m%d_%H%M%S}_{slug(model_id)}_{tag}_{index:02d}.{ext}"
