# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Model catalog: fetch, cache on disk, filter by lane, curated ordering."""
import json
import pathlib
from dataclasses import dataclass, field

PAGE_TOKEN_PARAM = "paginationToken"

GENERATION_LANES = ("image", "video", "3d", "material", "render_image", "render_video", "edit3d")
LANE_CAPS = {
    "image": {"txt2img", "img2img"},
    "video": {"txt2video", "img2video", "video2video"},
    "3d": {"txt23d", "img23d"},
    "render_image": {"img2img"},      # a viewport capture plus style images to a finished still
    "render_video": {"video2video"},  # a playblast plus images to a finished clip
    "edit3d": {"3d23d"},              # a mesh from the scene to a retextured / remeshed / rigged / animated mesh
}
PATINA_MODELS = ("model_patina-material", "model_patina", "model_patina-material-extract")
DEFAULT_MODELS = {
    "image": ["model_openai-gpt-image-2", "model_google-gemini-3-1-flash", "model_bytedance-seedream-5-0-pro", "model_bytedance-seedream-5-0", "model_z-image"],
    "video": ["model_bytedance-seedance-2-0", "model_bytedance-seedance-2-5", "model_google-veo-3-1", "model_kling-3-0"],
    "3d": ["model_meshy-7-txt23d", "model_rodin-hyper3d-v2-5-text-to-3d", "model_tripo-v3-1-image-to-3d", "model_meshy-7-img23d", "model_hunyuan-3d-pro-3-1-i23d",
           "model_rodin-hyper3d-v2-5", "model_tripo-p1-image-to-3d", "model_meshy-7-multi-image-to-3d", "model_tripo-v3-1-multiview-to-3d", "model_hunyuan-3d-pro-3-1-multiview"],
    "material": list(PATINA_MODELS),
    # the ten image edit models that take a reference image and a look prompt (catalog 2026-08-28, featured first)
    "render_image": ["model_google-gemini-3-1-flash", "model_openai-gpt-image-2", "model_bytedance-seedream-5-0-pro", "model_bfl-flux-2-max-editing", "model_bfl-flux-2-pro-editing",
                     "model_reve-remix", "model_qwen-image-edit-2511", "model_microsoft-mai-image-2-5-pro-edit", "model_xai-grok-imagine-image-2-0", "model_z-image"],
    # the ten video models that accept a reference video (and images) to re-render
    "render_video": ["model_bytedance-seedance-2-0", "model_minimax-h3", "model_bytedance-seedance-2-5", "model_bytedance-seedance-2-0-mini", "model_runway-aleph-2",
                     "model_alibaba-happy-horse-video-editing", "model_google-omni-1-1-flash-edit", "model_google-omni-flash-edit", "model_xai-grok-edit-video", "model_bfl-flux-3-extend"],
    "edit3d": ["model_meshy-7-retexture", "model_tripo-retopology", "model_meshy-rigging", "model_meshy-animation", "model_meshy-uv-unwrap", "model_tripo-segmentation-v2"],
}
RENDER_LANES = ("render_image", "render_video")
# Video models that address their inputs as @video1 / @image1 in the prompt (Seedance family). The others take plain words.
TAGGED_VIDEO_MODELS = ("seedance",)

# What a mesh from the scene can become. Each task lists the models that do it, best first; "ALL" shows every 3d23d model.
EDIT3D_TASKS = (
    ("RETEXTURE", "Retexture", "New textures and materials for the mesh, from a prompt or a style image",
     ("model_meshy-7-retexture", "model_tripo-v3-0-texturing", "model_trellis-2-retexture", "model_tencent-texture-edit", "model_meshy-retexture")),
    ("RETOPO", "Retopology", "Clean quad or triangle topology at a target polycount",
     ("model_tripo-retopology", "model_meshy-remesh", "model_tencent-smarttopology")),
    ("RIG", "Rigging", "A skeleton and skin weights for a character",
     ("model_meshy-rigging", "model_tripo-rigging-v2-5", "model_tripo-rigging-v1", "model_cartwheel-character-rigging")),
    ("ANIMATE", "Animation", "An animated version of a rigged character",
     ("model_meshy-animation", "model_cartwheel-text-to-motion")),
    ("UV", "UV unwrap", "New UV layout",
     ("model_meshy-uv-unwrap", "model_tencent-uv-unwrapping")),
    ("SEGMENT", "Segment", "Split the mesh into parts",
     ("model_tripo-segmentation-v2", "model_tripo-segmentation-v1", "model_hunyuan-3d-part", "model_hitem-3d-split")),
    ("STYLIZE", "Stylize", "Restyle the whole mesh",
     ("model_tripo-stylization", "model_rodin-hyper3d-bang", "model_hitem-3d-multicolor")),
    ("ALL", "All", "Every model that takes a mesh as input", ()),
)
# Names that mark utilities rather than renderers; kept out of the Render Image list (they still show in Image).
UTILITY_HINTS = ("remove background", "background remov", "upscal", "vectoriz", "reframe", "pixelate", "blur", "color lut", "layerize", "image sequence")


# Schema defaults that produce surprising results in Blender. Applied when the value is among the allowed ones.
# Rodin's "All" material returns two meshes (a baked Shaded GLB and a PBR GLB); one PBR mesh is what a Blender user expects.
PARAM_OVERRIDES = {
    "model_rodin-hyper3d-v2-5-text-to-3d": {"material": "PBR"},
    "model_rodin-hyper3d-v2-5-text-to-3d-fast": {"material": "PBR"},
    "model_rodin-hyper3d-v2-5": {"material": "PBR"},
    "model_rodin-hyper3d-v2-5-fast": {"material": "PBR"},
}
MULTIVIEW_HINTS = ("multi", "multiview")


def param_override(model_id, name):
    return (PARAM_OVERRIDES.get(model_id) or {}).get(name)


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


def is_utility(record):
    text = (record.name + " " + record.short_description[:60]).lower()
    return "tool" in record.tags or any(hint in text for hint in UTILITY_HINTS)


def models_for_lane(lane, records):
    """Filter records usable in `lane`, deprecated models removed, curated models first."""
    curated = DEFAULT_MODELS.get(lane, [])
    rank = {model_id: index for index, model_id in enumerate(curated)}
    usable = [r for r in records if lane in r.lanes and r.deprecated_successor is None and r.status in ("", "trained")]
    if lane == "material":
        usable = [r for r in usable if r.id in PATINA_MODELS]
    elif lane == "render_image":
        usable = [r for r in usable if r.id not in PATINA_MODELS and not is_utility(r)]
    return sorted(usable, key=lambda r: (rank.get(r.id, len(rank)), r.name.lower()))


def edit3d_task(task_id):
    return next((t for t in EDIT3D_TASKS if t[0] == task_id), EDIT3D_TASKS[-1])


def edit3d_models(task_id, records):
    """Mesh-to-mesh models for one task, best first; ALL lists every 3d23d model with the curated ones first."""
    usable = models_for_lane("edit3d", records)
    if task_id == "ALL":
        return usable
    wanted = list(edit3d_task(task_id)[3])
    by_id = {r.id: r for r in usable}
    return [by_id[m] for m in wanted if m in by_id]


def tagged_video_model(model_id):
    return any(hint in (model_id or "").lower() for hint in TAGGED_VIDEO_MODELS)


def mesh_param(record):
    """Name of the parameter that takes the input mesh (kind 3d), or None."""
    for raw in record.parameters:
        if raw.get("type") in ("file", "file_array") and (raw.get("kind") or "").lower() == "3d":
            return raw.get("name")
    return None


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
