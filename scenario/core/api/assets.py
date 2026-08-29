# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assets: read, download, upload (base64 or multipart)."""
import base64
import math
import pathlib
import shutil
import time
import urllib.request

from . import jobs
from .errors import NetworkError, ScenarioError

BASE64_LIMIT = 3_500_000  # bytes; the gateway body cap is 10 MB, 4.4 MB raw PNGs verified to pass
PART_SIZE = 32 * 1024 * 1024

_EXT_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif",
    ".avif": "image/avif", ".tif": "image/tiff", ".tiff": "image/tiff", ".heic": "image/heic", ".svg": "image/svg+xml",
    ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg", ".m4a": "audio/mp4",
    ".glb": "model/gltf-binary", ".gltf": "model/gltf+json", ".fbx": "model/x-fbx", ".obj": "model/obj",
    ".stl": "model/stl", ".ply": "model/ply", ".vox": "model/x-3d-vox",
}


def mime_for_path(path):
    return _EXT_MIME.get(pathlib.Path(str(path)).suffix.lower(), "application/octet-stream")


def kind_for_path(path):
    mime = mime_for_path(path)
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    if mime.startswith("audio/"):
        return "audio"
    return "3d"


def get_asset(client, asset_id):
    data = client.get(f"/assets/{asset_id}")
    return data.get("asset") or data


def asset_type(asset):
    return ((asset or {}).get("metadata") or {}).get("type") or ""


def download_file(url, dest, transport=None, timeout=300, retries=3, sleep=time.sleep):
    """Download a signed CDN URL to `dest` (atomic rename), streaming to disk, with bounded retries.

    Large 3D bundles (a Meshy OBJ is 200+ MB) have seen the CDN close the connection mid-transfer;
    one retry with a short backoff recovers it. The query string is never altered (it carries the signature)."""
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    delay = 1.0
    last_error = None
    for attempt in range(retries + 1):
        try:
            if transport is not None:
                status, _headers, raw = transport.request("GET", url, {}, None, timeout)
                if status >= 400:
                    raise ScenarioError(status, f"download failed ({status}) for {url[:80]}")
                tmp.write_bytes(raw)
            else:
                req = urllib.request.Request(url, headers={"User-Agent": "ScenarioBlender"})
                with urllib.request.urlopen(req, timeout=timeout) as resp, tmp.open("wb") as out:
                    shutil.copyfileobj(resp, out, 1024 * 1024)
            tmp.replace(dest)
            return dest
        except ScenarioError as err:
            if err.status and err.status < 500 and err.status not in (408, 429):
                raise
            last_error = err
        except (OSError, NetworkError) as err:  # includes URLError, RemoteDisconnected, timeouts
            last_error = err
        if attempt < retries:
            sleep(delay)
            delay *= 2
    raise NetworkError(0, f"download failed after {retries + 1} attempts: {last_error}")


def upload_image_base64(client, path, name=None):
    path = pathlib.Path(path)
    mime = mime_for_path(path)
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    data = client.post("/assets", json_body={"image": f"data:{mime};base64,{encoded}", "name": name or path.name})
    asset = data.get("asset") or data
    return asset["id"]


def upload_multipart(client, path, kind, content_type=None, transport=None, sleep=time.sleep, poll_interval=1.5, max_polls=120):
    path = pathlib.Path(path)
    transport = transport or client.transport
    content_type = content_type or mime_for_path(path)
    size = path.stat().st_size
    parts = max(1, math.ceil(size / PART_SIZE))
    created = client.post("/uploads", json_body={"fileName": path.name, "fileSize": size, "contentType": content_type, "kind": kind, "parts": parts})
    upload = created.get("upload") or created
    upload_id, job_id = upload["id"], upload.get("jobId")
    with path.open("rb") as handle:
        for part in sorted(upload.get("parts") or [], key=lambda p: p.get("number", 0)):
            chunk = handle.read(PART_SIZE)
            status, _h, raw = transport.request("PUT", part["url"], {"Content-Type": content_type}, chunk, 600)
            if status >= 400:
                raise ScenarioError(status, f"part {part.get('number')} upload failed: {raw[:200]!r}")
    client.post(f"/uploads/{upload_id}/action", json_body={"action": "complete"})
    for _ in range(max_polls):
        job = jobs.get_job(client, job_id)
        entity = jobs.upload_entity_id(job)
        if entity:
            return entity
        if jobs.is_terminal(job.get("status")) and not jobs.is_success(job.get("status")):
            raise ScenarioError(0, f"upload job {job_id} {job.get('status')}")
        sleep(poll_interval)
    raise ScenarioError(0, f"upload {upload_id} did not import in time")


def upload_file(client, path, kind=None, transport=None):
    path = pathlib.Path(path)
    kind = kind or kind_for_path(path)
    if kind == "image" and path.stat().st_size <= BASE64_LIMIT:
        return upload_image_base64(client, path)
    return upload_multipart(client, path, kind, transport=transport)
