# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Model catalog: fetch, cache on disk, filter by lane, curated ordering."""
import json
import pathlib
from dataclasses import dataclass, field

PAGE_TOKEN_PARAM = "paginationToken"

GENERATION_LANES = ("image", "video", "3d", "material")
LANE_CAPS = {
    "image": {"txt2img", "img2img"},
    "video": {"txt2video", "img2video", "video2video"},
    "3d": {"txt23d", "img23d"},
}
PATINA_MODELS = ("model_patina-material", "model_patina", "model_patina-material-extract")
DEFAULT_MODELS = {
    "image": ["model_openai-gpt-image-2", "model_google-gemini-3-1-flash", "model_bytedance-seedream-5-0-pro", "model_bytedance-seedream-5-0", "model_z-image"],
    "video": ["model_bytedance-seedance-2-0", "model_bytedance-seedance-2-5", "model_google-veo-3-1", "model_kling-3-0"],
    "3d": ["model_meshy-7-txt23d", "model_rodin-hyper3d-v2-5-text-to-3d", "model_tripo-v3-1-image-to-3d", "model_meshy-7-img23d", "model_hunyuan-3d-pro-3-1-i23d", "model_rodin-hyper3d-v2-5"],
    "material": list(PATINA_MODELS),
}


@dataclass
class ModelRecord:
    id: str
    name: str
    short_description: str = ""
    capabilities: tuple = ()
    tags: tuple = ()
    type: str = ""
    status: str = ""
    privacy: str = ""
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_api(cls, data):
        return cls(
            id=data.get("id", ""),
            name=data.get("name") or data.get("id", ""),
            short_description=data.get("shortDescription") or "",
            capabilities=tuple(c if isinstance(c, str) else c.get("type", "") for c in data.get("capabilities") or ()),
            tags=tuple(data.get("tags") or ()),
            type=data.get("type") or "",
            status=data.get("status") or "",
            privacy=data.get("privacy") or "",
            raw=dict(data),
        )

    @property
    def parameters(self):
        """The parameter schema. REST records carry it under `inputs` (`parameters` is often an empty dict)."""
        params = self.raw.get("parameters")
        if isinstance(params, list) and params:
            return list(params)
        return list(self.raw.get("inputs") or [])

    @property
    def ui_config(self):
        return dict(self.raw.get("uiConfig") or {})

    @property
    def deprecated_successor(self):
        for tag in self.tags:
            if tag.startswith("deprecated:"):
                return tag.split(":", 1)[1] or None
        return None

    @property
    def lanes(self):
        caps = set(self.capabilities)
        lanes = {lane for lane, wanted in LANE_CAPS.items() if caps & wanted}
        if self.id in PATINA_MODELS:
            lanes.add("material")
        return lanes


def models_for_lane(lane, records):
    """Filter records usable in `lane`, deprecated models removed, curated models first."""
    curated = DEFAULT_MODELS.get(lane, [])
    rank = {model_id: index for index, model_id in enumerate(curated)}
    usable = [r for r in records if lane in r.lanes and r.deprecated_successor is None and r.status in ("", "trained")]
    if lane == "material":
        usable = [r for r in usable if r.id in PATINA_MODELS]
    return sorted(usable, key=lambda r: (rank.get(r.id, len(rank)), r.name.lower()))


class Catalog:
    def __init__(self, client, cache_dir):
        self.client = client
        self.cache_dir = pathlib.Path(cache_dir)

    # -- lists ------------------------------------------------------------
    def fetch_list(self, privacy="public", page_size=100, max_pages=20):
        records, token = [], None
        for _ in range(max_pages):
            query = {"privacy": privacy, "pageSize": page_size}
            if token:
                query[PAGE_TOKEN_PARAM] = token
            data = self.client.get("/models", query=query)
            records.extend(ModelRecord.from_api(m) for m in data.get("models") or [])
            token = data.get("nextPaginationToken")
            if not token:
                break
        self._write(self._list_file(privacy), [r.raw for r in records])
        return records

    def load_list_cached(self, privacy="public"):
        path = self._list_file(privacy)
        if not path.exists():
            return None
        return [ModelRecord.from_api(m) for m in json.loads(path.read_text(encoding="utf-8"))]

    # -- single records -----------------------------------------------------
    def load_cached(self, model_id):
        path = self.cache_dir / "models" / f"{model_id}.json"
        if not path.exists():
            return None
        try:
            return ModelRecord.from_api(json.loads(path.read_text(encoding="utf-8")))
        except (ValueError, OSError):
            return None

    def get(self, model_id, refresh=False):
        path = self.cache_dir / "models" / f"{model_id}.json"
        if path.exists() and not refresh:
            return ModelRecord.from_api(json.loads(path.read_text(encoding="utf-8")))
        data = self.client.get(f"/models/{model_id}")
        model = data.get("model") or data
        self._write(path, model)
        return ModelRecord.from_api(model)

    def models_for_lane(self, lane, records):
        return models_for_lane(lane, records)

    # -- helpers ------------------------------------------------------------
    def _list_file(self, privacy):
        return self.cache_dir / f"list_{privacy}.json"

    @staticmethod
    def _write(path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)
