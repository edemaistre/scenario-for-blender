# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lane filters added in 0.6.0: Render Image, Render Video, Edit 3D."""
from scenario.core.api import catalog


def rec(model_id, name, caps, tags=(), inputs=(), desc=""):
    return catalog.ModelRecord.from_api({"id": model_id, "name": name, "capabilities": list(caps), "tags": list(tags), "status": "trained",
                                         "inputs": list(inputs), "shortDescription": desc})


RECORDS = [
    rec("model_google-gemini-3-1-flash", "Gemini 3.1", ["txt2img", "img2img", "video2img"], ["sc:featured"]),
    rec("model_bria-remove-background", "Bria Remove Background", ["img2img"]),
    rec("model_patina-material", "PATINA Material", ["txt2img", "img2img"]),
    rec("model_some-lora", "Cartoon Backgrounds 2.0", ["txt2img", "img2img"], ["sc:scenario"]),
    rec("model_scenario-llm", "Scenario LLM", ["txt2txt", "img2txt"], ["tool"]),
    rec("model_bytedance-seedance-2-0", "Seedance 2.0", ["txt2video", "img2video", "video2video"]),
    rec("model_minimax-h3", "Minimax H3", ["txt2video", "img2video", "video2video"]),
    rec("model_kling-v3-i2v-pro", "Kling V3 I2V Pro", ["img2video"]),
    rec("model_meshy-7-retexture", "Meshy 7 - Retexture", ["3d23d"], inputs=[{"name": "model", "type": "file", "kind": "3d"}, {"name": "imageStyle", "type": "file", "kind": "image"}]),
    rec("model_tripo-retopology", "Tripo Retopology", ["3d23d"], inputs=[{"name": "model", "type": "file", "kind": "3d"}]),
    rec("model_tencent-uv-unwrapping", "Tencent UV Unwrapping", ["3d23d"], inputs=[{"name": "file3d", "type": "file", "kind": "3d"}]),
    rec("model_meshy-7-txt23d", "Meshy 7 - Text-to-3D", ["txt23d"]),
]


def ids(records):
    return [r.id for r in records]


def test_render_image_lane_keeps_edit_models_and_drops_utilities_and_patina():
    got = ids(catalog.models_for_lane("render_image", RECORDS))
    assert got[0] == "model_google-gemini-3-1-flash"
    assert "model_some-lora" in got
    assert "model_bria-remove-background" not in got
    assert "model_patina-material" not in got
    assert "model_scenario-llm" not in got


def test_render_video_lane_needs_a_video_input():
    got = ids(catalog.models_for_lane("render_video", RECORDS))
    assert got[:2] == ["model_bytedance-seedance-2-0", "model_minimax-h3"]
    assert "model_kling-v3-i2v-pro" not in got


def test_edit3d_lane_and_tasks():
    assert ids(catalog.models_for_lane("edit3d", RECORDS)) == ["model_meshy-7-retexture", "model_tripo-retopology", "model_tencent-uv-unwrapping"]
    assert ids(catalog.edit3d_models("RETEXTURE", RECORDS)) == ["model_meshy-7-retexture"]
    assert ids(catalog.edit3d_models("RETOPO", RECORDS)) == ["model_tripo-retopology"]
    assert ids(catalog.edit3d_models("UV", RECORDS)) == ["model_tencent-uv-unwrapping"]
    assert ids(catalog.edit3d_models("RIG", RECORDS)) == []
    assert len(catalog.edit3d_models("ALL", RECORDS)) == 3
    assert catalog.edit3d_task("RETOPO")[1] == "Retopology"
    assert catalog.edit3d_task("nope")[0] == "ALL"


def test_mesh_param_and_tagged_models():
    assert catalog.mesh_param(RECORDS[8]) == "model"
    assert catalog.mesh_param(RECORDS[10]) == "file3d"
    assert catalog.mesh_param(RECORDS[0]) is None
    assert catalog.tagged_video_model("model_bytedance-seedance-2-0-mini")
    assert not catalog.tagged_video_model("model_minimax-h3")


def test_every_curated_edit3d_model_belongs_to_a_task():
    tasked = {m for task in catalog.EDIT3D_TASKS for m in task[3]}
    assert set(catalog.DEFAULT_MODELS["edit3d"]) <= tasked
