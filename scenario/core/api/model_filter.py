# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scenario's model taxonomy for the picker dialog: modality tabs, category chips, search, recents. No bpy.

Mirrors "Choose a Model" in the web app (2026-08-28): tabs Image / Video / Audio / 3D and, per tab, the category
chips listed in CATEGORIES. LoRAs (Scenario's trained style presets) and deprecated models never appear."""
import json
import pathlib

try:
    from .catalog import is_lora
except ImportError:  # an older installed catalog without the helper (tests loading this file against a 0.6.0 build)
    def is_lora(record):
        raw = record.raw or {}
        if record.type and record.type != "custom":
            return True
        return bool(raw.get("parentModelId") or raw.get("trainingImagesNumber") or raw.get("concepts"))

MODALITIES = (
    ("image", "Image", "image"),
    ("video", "Video", "video"),
    ("audio", "Audio", "audio"),
    ("3d", "3D", "3d"),
)
CATEGORIES = {
    "image": [("all", "All"), ("generate", "Generate"), ("edit", "Edit"), ("expand", "Expand"), ("upscale", "Upscale"), ("vectorize", "Vectorize"),
              ("remove_background", "Remove Background"), ("tools", "Tools")],
    "video": [("all", "All"), ("generate", "Generate"), ("edit", "Edit"), ("lipsync", "Lipsync"), ("upscale", "Upscale"), ("reframe", "Reframe"),
              ("remove_background", "Remove Background"), ("tools", "Tools")],
    "audio": [("all", "All"), ("speech", "Speech"), ("music", "Music"), ("sfx", "SFX"), ("tools", "Tools")],
    "3d": [("all", "All"), ("generate", "Generate"), ("splat", "Splat"), ("remesh", "Remesh"), ("retexture", "Retexture"), ("uv_unwrap", "UV Unwrap"),
           ("rigging", "Rigging"), ("animate", "Animate"), ("parts", "Parts")],
}
# Which tab a lane opens on, and which lane a tab lands in when the user crosses modalities.
LANE_MODALITY = {"image": "image", "render_image": "image", "material": "image", "video": "video", "render_video": "video", "3d": "3d", "edit3d": "3d", "audio": "audio"}
BASE_LANE = {"image": "image", "video": "video", "3d": "3d", "audio": "audio"}
FEATURED_TAG = "sc:featured"
BUILTIN_ICONS = {"image": 'IMAGE_DATA', "video": 'FILE_MOVIE', "audio": 'SPEAKER', "3d": 'MESH_DATA', "text": 'FILE_TEXT'}

_TOOL_TAGS = {"tool", "tools", "post processing"}
_EDIT_TAGS = {"editing", "image editing", "video editing"}


def _lower_tags(record):
    return {t.lower() for t in (record.tags or ())}


def is_deprecated(record):
    return any(t.lower().startswith("deprecated") for t in (record.tags or ()))


def _io(record):
    ins, outs = set(), set()
    for cap in record.capabilities or ():
        cap = str(cap).lower()
        if "2" in cap:
            a, b = cap.split("2", 1)
            ins.add(a)
            outs.add(b)
    return ins, outs


def modality_of(record):
    """What the model produces: image, video, audio, 3d, text; "" when unknown. Speech-to-text counts as audio (a tool)."""
    if record is None:
        return ""
    ins, outs = _io(record)
    if any(o.startswith("3d") for o in outs):
        return "3d"
    if any(o.startswith("video") for o in outs):
        return "video"
    if any(o.startswith("audio") for o in outs):
        return "audio"
    if any(o.startswith("img") for o in outs):
        return "image"
    if any(o.startswith("txt") for o in outs):
        return "audio" if "audio" in ins else "text"
    caps = {str(c).lower() for c in (record.capabilities or ())}
    if caps & {"controlnet", "inpaint", "outpaint", "img2img_texture", "txt2img_texture"}:
        return "image"
    return ""


def _image_categories(name, tags, out):
    if tags & _EDIT_TAGS or "edit" in name or "kontext" in name:
        out.add("edit")
    if tags & {"image-upscale", "enhance"} or "upscal" in name or "enhance" in name:
        out.add("upscale")
    if "remove-background" in tags or "background remov" in name or "remove background" in name or "bg remov" in name:
        out.add("remove_background")
    if "vector" in name:
        out.add("vectorize")
    if any(k in name for k in ("expand", "outpaint", "uncrop", "reframe")) or "outpaint" in tags:
        out.add("expand")
    if tags & _TOOL_TAGS:
        out.add("tools")


def _video_categories(name, tags, out):
    if tags & _EDIT_TAGS or "edit" in name:
        out.add("edit")
    if "lipsync" in tags or "lipsync" in name or "lip sync" in name or "lip-sync" in name:
        out.add("lipsync")
    if tags & {"video-upscale", "enhance"} or "upscal" in name:
        out.add("upscale")
    if "reframe" in name:
        out.add("reframe")
    if "remove-background" in tags or "background remov" in name or "remove background" in name:
        out.add("remove_background")
    if tags & _TOOL_TAGS:
        out.add("tools")


def _audio_categories(name, tags, ins, out):
    if tags & {"tts", "text-to-speech", "text to speech", "speech"} or any(k in name for k in ("speech", "voice", "tts", "transcri")):
        out.add("speech")
    if tags & {"music", "text to music"} or "music" in name or "song" in name or "lyria" in name:
        out.add("music")
    if "sfx" in tags or "sfx" in name or "sound effect" in name or "foley" in name:
        out.add("sfx")
    if tags & _TOOL_TAGS or "audio" in ins or any(k in name for k in ("cut", "split", "extract", "to text", "transcri", "dubbing", "isolat", "convert", "stem")):
        out.add("tools")
    if not out:
        out.add("speech" if "txt" in ins else "tools")


def _threed_categories(name, tags, caps, out):
    mesh_in = "3d23d" in caps or "video23d" in caps
    if tags & {"splat", "world"} or "splat" in name or "world" in name:
        out.add("splat")
    if mesh_in and (tags & {"remeshing", "retopology"} or any(k in name for k in ("remesh", "retopo", "topology"))):
        out.add("remesh")
    if mesh_in and ("retexture" in tags or any(k in name for k in ("retexture", "texturing", "texture edit", "multicolor", "styliz"))):
        out.add("retexture")
    if mesh_in and ("uv" in name.split() or "unwrap" in name):
        out.add("uv_unwrap")
    if mesh_in and ("rigging" in tags or "rig" in name):
        out.add("rigging")
    if (mesh_in or "txt23d" in caps) and (tags & {"animation", "motion"} or any(k in name for k in ("animation", "motion", "animate"))):
        out.add("animate")
    if mesh_in and ("segmentation" in tags or any(k in name for k in ("segment", "split", "part"))):
        out.add("parts")


def categories_of(record):
    """Category ids (without "all") for the model's modality; "generate" when nothing more specific applies."""
    modality = modality_of(record)
    if not modality or modality == "text":
        return set()
    name = (record.name or "").lower()
    tags = _lower_tags(record)
    caps = {str(c).lower() for c in (record.capabilities or ())}
    ins, _outs = _io(record)
    out = set()
    if modality == "image":
        _image_categories(name, tags, out)
    elif modality == "video":
        _video_categories(name, tags, out)
    elif modality == "audio":
        _audio_categories(name, tags, ins, out)
    elif modality == "3d":
        _threed_categories(name, tags, caps, out)
    if not out:
        out.add("generate")
    return out


def visible(record):
    """Shown in the picker: not a LoRA, not deprecated, of a modality that has a tab."""
    return record is not None and not is_lora(record) and not is_deprecated(record) and modality_of(record) in BASE_LANE


def _haystack(record):
    return " ".join((record.id, record.name, record.short_description or "", " ".join(record.tags))).lower()


def matches(record, query):
    """Every whitespace-separated token of `query` must appear in the name, description, tags or id."""
    tokens = [t for t in (query or "").lower().split() if t]
    if not tokens:
        return True
    hay = _haystack(record)
    return all(token in hay for token in tokens)


def is_featured(record):
    return FEATURED_TAG in record.tags


def filter_records(records, modality, category="all", query="", recent_ids=()):
    """Visible records of `modality` in `category` matching `query`: recently used first (in recent order, only under
    All with no query, like the web app's "Recently used" group), then featured, then by name."""
    recent = list(recent_ids) if (category in ("all", "", None) and not (query or "").strip()) else []
    rank = {model_id: index for index, model_id in enumerate(recent)}
    out = []
    for record in records:
        if not visible(record) or modality_of(record) != modality:
            continue
        if category not in ("all", "", None) and category not in categories_of(record):
            continue
        if not matches(record, query):
            continue
        out.append(record)
    out.sort(key=lambda r: (rank.get(r.id, len(rank)), not is_featured(r), r.name.lower()))
    return out


def category_items(modality):
    return list(CATEGORIES.get(modality) or [("all", "All")])


def thumbnail_url(record):
    thumb = (record.raw or {}).get("thumbnail")
    if isinstance(thumb, dict):
        return thumb.get("url") or None
    return None


def modality_icon(record):
    """Blender built-in icon name for what the model produces; QUESTION when unknown."""
    return BUILTIN_ICONS.get(modality_of(record), 'QUESTION')


class RecentModels:
    """Per-lane list of recently picked model ids, newest first, kept in a small JSON file."""

    def __init__(self, path, limit=8):
        self.path = pathlib.Path(path)
        self.limit = int(limit)
        self._data = self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(lane): [str(m) for m in ids] for lane, ids in data.items() if isinstance(ids, list)}

    def ids(self, lane):
        return list(self._data.get(lane, []))

    def touch(self, lane, model_id):
        if not model_id:
            return self.ids(lane)
        ids = [m for m in self._data.get(lane, []) if m != model_id]
        ids.insert(0, model_id)
        self._data[lane] = ids[:self.limit]
        self._save()
        return list(self._data[lane])

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._data), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass
