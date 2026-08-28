# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assets: read, download, upload (base64 or multipart)."""
import base64
import math
import pathlib
import time

from . import jobs
from .errors import ScenarioError
from .transport import UrllibTransport

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


def download_file(url, dest, transport=None, timeout=300):
    """Download a signed CDN URL to `dest` (atomic rename). Never alters the query string."""
    transport = transport or UrllibTransport(timeout=timeout)
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    status, _headers, raw = transport.request("GET", url, {}, None, timeout)
    if status >= 400:
        raise ScenarioError(status, f"download failed for {url[:80]}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(raw)
    tmp.replace(dest)
    return dest


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
