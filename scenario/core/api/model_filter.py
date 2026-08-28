# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Search, chips, ordering and recents for the model picker dialog. No bpy."""
import json
import pathlib

FILTERS = (
    ("all", "All", "Every model usable in this lane"),
    ("featured", "Featured", "Models Scenario highlights"),
    ("scenario", "Scenario", "Scenario's own models and LoRAs"),
    ("third_party", "Partners", "Third-party models (OpenAI, Google, ByteDance...)"),
    ("recent", "Recent", "Models you picked recently in this lane"),
)
TAG_FOR_CHIP = {"featured": "sc:featured", "scenario": "sc:scenario", "third_party": "sc:third-party"}
FEATURED_TAG = "sc:featured"

# Output modality of a capability ("txt2img" -> "img"), most specific icon wins when a model spans several.
_OUTPUT_ICONS = (("3d", 'MESH_DATA'), ("video", 'FILE_MOVIE'), ("audio", 'SPEAKER'), ("img", 'IMAGE_DATA'), ("txt", 'FILE_TEXT'))


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


def filter_records(records, query="", chip="all", recent_ids=()):
    """Records passing the chip and the search, recents in recent order or featured first then by name."""
    recent = list(recent_ids)
    wanted_tag = TAG_FOR_CHIP.get(chip)
    out = []
    for record in records:
        if wanted_tag is not None and wanted_tag not in record.tags:
            continue
        if chip == "recent" and record.id not in recent:
            continue
        if not matches(record, query):
            continue
        out.append(record)
    if chip == "recent":
        rank = {model_id: index for index, model_id in enumerate(recent)}
        out.sort(key=lambda r: rank.get(r.id, len(rank)))
    else:
        out.sort(key=lambda r: (not is_featured(r), r.name.lower()))
    return out


def thumbnail_url(record):
    thumb = (record.raw or {}).get("thumbnail")
    if isinstance(thumb, dict):
        return thumb.get("url") or None
    return None


def _output_of(capability):
    cap = str(capability or "").lower()
    if "2" not in cap:
        return ""
    return cap.split("2", 1)[1]


def modality_icon(record):
    """Blender icon name for what the model produces: 3D, video, audio, image, text; QUESTION when unknown."""
    outputs = {_output_of(c) for c in (record.capabilities if record is not None else ())}
    for prefix, icon in _OUTPUT_ICONS:
        if any(out.startswith(prefix) for out in outputs):
            return icon
    return 'QUESTION'


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
