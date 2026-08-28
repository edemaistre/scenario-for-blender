# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Scenario's picker taxonomy: modality tabs, category chips, LoRAs out."""
from scenario.core.api import model_filter as mf
from scenario.core.api.catalog import ModelRecord


def rec(model_id, name, caps=("txt2img",), tags=(), desc="", thumb=None, **raw):
    data = {"id": model_id, "name": name, "capabilities": list(caps), "tags": list(tags), "shortDescription": desc, "type": "custom"}
    data.update(raw)
    if thumb:
        data["thumbnail"] = {"assetId": "asset_x", "url": thumb}
    return ModelRecord.from_api(data)


GPT = rec("model_openai-gpt-image-2", "GPT Image 2", ("txt2img", "img2img"), ("GPT-Image", "OpenAI", "editing", "sc:featured", "sc:third-party"), "Best-in-class prompt adherence")
GEMINI = rec("model_google-gemini-3-1-flash", "Gemini 3.1", ("txt2img", "img2img", "video2img"), ("editing", "sc:featured", "sc:third-party"))
ZIMAGE = rec("model_z-image", "Z-Image", ("txt2img", "img2img", "controlnet"), ("sc:third-party",), "Fast open model")
BRIA = rec("model_bria-remove-background", "Bria Remove Background", ("img2img",), ("remove-background", "tool", "sc:third-party"))
UPSCALE = rec("model_sc-upscale-v3", "Scenario Upscale V3", ("img2img",), ("image-upscale", "tool", "sc:scenario"))
VECTOR = rec("model_recraft-vectorize", "Recraft Vectorize", ("img2img",), ("sc:third-party",))
EXPAND = rec("model_photoroom-expand", "Photoroom Expand", ("img2img",), ("tool", "sc:third-party"))
LORA = rec("model_3Dchibis", "3D Chibis", ("txt2img", "img2img"), ("sc:scenario",), "Flux LoRA that renders chibi characters", thumb="https://cdn.example/t.jpg",
           type="flux.1-lora", parentModelId="model_flux", trainingImagesNumber=20)
COMPOSITION = rec("model_composition", "Neo3D Realism", ("txt2img",), ("sc:scenario",), type="flux.1-composition")
DEPRECATED = rec("model_old", "Old Thing", ("txt2img",), ("deprecated:model_new", "sc:third-party"))
LLM = rec("model_scenario-llm", "Scenario LLM", ("txt2txt", "img2txt"), ("Text", "llm", "tool", "sc:scenario"))
BLUR_VIDEO = rec("model_scenario-postprocessing-blur-video", "Blur (Video)", ("video2video",), ("Post Processing", "tool", "sc:scenario"))
SEEDANCE = rec("model_bytedance-seedance-2-0", "Seedance 2.0", ("txt2video", "img2video", "video2video"), ("editing", "sc:featured", "sc:third-party"))
KLING = rec("model_kling-v3-i2v-pro", "Kling V3 I2V Pro", ("img2video",), ("I2V", "sc:featured", "sc:third-party"))
LIPSYNC = rec("model_sync-lipsync-2", "Sync Lipsync 2", ("video2video",), ("lipsync", "sc:third-party"))
REFRAME_V = rec("model_wan-2-2-reframe", "Wan 2.2 Reframe", ("video2video",), ("editing", "sc:third-party"))
ACE = rec("model_ace-step-1-5", "ACE-Step 1.5 Text to Music - Quality", ("txt2audio",), ("Music", "Text to Music", "sc:third-party"))
TTS = rec("model_elevenlabs-tts-v3", "ElevenLabs 3", ("txt2audio",), ("TTS", "sc:third-party"))
SFX = rec("model_elevenlabs-sfx", "ElevenLabs Sound Effects 2", ("txt2audio",), ("SFX", "sc:third-party"))
STT = rec("model_speech-to-text", "Speech to Text", ("audio2txt",), ("tool", "sc:scenario"))
BANG = rec("model_rodin-hyper3d-bang", "Rodin Hyper3D Bang!", ("3d23d",), ("3D to 3D", "PBR", "Retexture", "Rodin", "Segmentation", "sc:third-party"))
RETOPO = rec("model_tripo-retopology", "Tripo Retopology", ("3d23d",), ("Retopology", "Tripo", "sc:third-party"))
MESHY7 = rec("model_meshy-7-txt23d", "Meshy 7 - Text-to-3D", ("txt23d",), ("Meshy", "Text to 3D", "sc:third-party"))
TRIPO31 = rec("model_tripo-v3-1-image-to-3d", "Tripo 3.1", ("img23d",), ("Image to 3D", "sc:featured", "sc:third-party"))
SPLAT = rec("model_hunyuan-world-image-to-splat", "HY World - Image to Splat", ("img23d",), ("world", "splat"))
UV = rec("model_meshy-uv-unwrap", "Meshy UV Unwrap", ("3d23d",), ("Meshy", "sc:third-party"))
RIG = rec("model_meshy-rigging", "Meshy Rigging", ("3d23d",), ("Rigging", "sc:third-party"))
MOTION = rec("model_meshy-text-to-motion", "Meshy Text to Motion", ("txt23d",), ("Motion", "Animation", "sc:third-party"))
TRELLIS = rec("model_trellis-2", "Trellis 2", ("img23d",), ("Remeshing", "sc:third-party"))  # a generator tagged Remeshing: no mesh input, so Generate
ALL = [GPT, GEMINI, ZIMAGE, BRIA, UPSCALE, VECTOR, EXPAND, LORA, COMPOSITION, DEPRECATED, LLM, BLUR_VIDEO, SEEDANCE, KLING, LIPSYNC, REFRAME_V, ACE, TTS, SFX, STT,
       BANG, RETOPO, MESHY7, TRIPO31, SPLAT, UV, RIG, MOTION, TRELLIS]


def ids(records):
    return [r.id for r in records]


def test_modalities_and_categories_match_the_web_app():
    assert [m[0] for m in mf.MODALITIES] == ["image", "video", "audio", "3d"]
    assert [c[1] for c in mf.CATEGORIES["image"]] == ["All", "Generate", "Edit", "Expand", "Upscale", "Vectorize", "Remove Background", "Tools"]
    assert [c[1] for c in mf.CATEGORIES["video"]] == ["All", "Generate", "Edit", "Lipsync", "Upscale", "Reframe", "Remove Background", "Tools"]
    assert [c[1] for c in mf.CATEGORIES["audio"]] == ["All", "Speech", "Music", "SFX", "Tools"]
    assert [c[1] for c in mf.CATEGORIES["3d"]] == ["All", "Generate", "Splat", "Remesh", "Retexture", "UV Unwrap", "Rigging", "Animate", "Parts"]
    assert not hasattr(mf, "FILTERS")


def test_modality_from_the_output_side_of_capabilities():
    assert mf.modality_of(GEMINI) == "image"        # video2img still produces images
    assert mf.modality_of(SEEDANCE) == "video"
    assert mf.modality_of(ACE) == "audio"
    assert mf.modality_of(STT) == "audio"           # speech to text is an audio tool
    assert mf.modality_of(BANG) == "3d"
    assert mf.modality_of(LLM) == "text"
    assert mf.modality_of(None) == ""


def test_image_categories():
    assert mf.categories_of(GPT) == {"edit"}
    assert mf.categories_of(ZIMAGE) == {"generate"}
    assert mf.categories_of(BRIA) == {"remove_background", "tools"}
    assert mf.categories_of(UPSCALE) == {"upscale", "tools"}
    assert mf.categories_of(VECTOR) == {"vectorize"}
    assert mf.categories_of(EXPAND) == {"expand", "tools"}


def test_video_and_audio_categories():
    assert mf.categories_of(SEEDANCE) == {"edit"}
    assert mf.categories_of(KLING) == {"generate"}
    assert mf.categories_of(LIPSYNC) == {"lipsync"}
    assert mf.categories_of(REFRAME_V) == {"edit", "reframe"}
    assert mf.categories_of(BLUR_VIDEO) == {"tools"}
    assert mf.categories_of(ACE) == {"music"}
    assert mf.categories_of(TTS) == {"speech"}
    assert mf.categories_of(SFX) == {"sfx"}
    assert mf.categories_of(STT) == {"speech", "tools"}


def test_3d_categories_need_a_mesh_input_for_edit_tasks():
    assert mf.categories_of(BANG) == {"retexture", "parts"}
    assert mf.categories_of(RETOPO) == {"remesh"}
    assert mf.categories_of(UV) == {"uv_unwrap"}
    assert mf.categories_of(RIG) == {"rigging"}
    assert mf.categories_of(MOTION) == {"animate"}
    assert mf.categories_of(SPLAT) == {"splat"}
    assert mf.categories_of(MESHY7) == {"generate"}
    assert mf.categories_of(TRIPO31) == {"generate"}
    assert mf.categories_of(TRELLIS) == {"generate"}
    assert mf.categories_of(LLM) == set()


def test_loras_deprecated_and_text_models_are_never_visible():
    assert not mf.visible(LORA)
    assert not mf.visible(COMPOSITION)
    assert not mf.visible(DEPRECATED)
    assert not mf.visible(LLM)
    assert mf.visible(GPT) and mf.visible(BLUR_VIDEO) and mf.visible(STT) and mf.visible(BANG)


def test_filter_by_modality_category_and_query():
    image_all = ids(mf.filter_records(ALL, "image"))
    assert image_all[:2] == ["model_google-gemini-3-1-flash", "model_openai-gpt-image-2"]  # featured first, then name
    assert "model_3Dchibis" not in image_all and "model_old" not in image_all and "model_scenario-llm" not in image_all
    assert ids(mf.filter_records(ALL, "image", "remove_background")) == ["model_bria-remove-background"]
    assert ids(mf.filter_records(ALL, "image", "edit")) == ["model_google-gemini-3-1-flash", "model_openai-gpt-image-2"]
    assert ids(mf.filter_records(ALL, "image", "generate")) == ["model_z-image"]
    assert ids(mf.filter_records(ALL, "video", "tools")) == ["model_scenario-postprocessing-blur-video"]
    assert ids(mf.filter_records(ALL, "audio", "music")) == ["model_ace-step-1-5"]
    assert set(ids(mf.filter_records(ALL, "3d", "parts"))) == {"model_rodin-hyper3d-bang"}
    assert set(ids(mf.filter_records(ALL, "3d", "retexture"))) == {"model_rodin-hyper3d-bang"}
    assert ids(mf.filter_records(ALL, "3d", query="bang")) == ["model_rodin-hyper3d-bang"]
    assert mf.filter_records(ALL, "image", query="nothing-here") == []


def test_recently_used_come_first_only_under_all_without_query():
    recent = ["model_z-image", "model_gone"]
    assert ids(mf.filter_records(ALL, "image", "all", "", recent))[0] == "model_z-image"
    assert ids(mf.filter_records(ALL, "image", "generate", "", recent)) == ["model_z-image"]
    with_query = ids(mf.filter_records(ALL, "image", "all", "image", recent))
    assert with_query[0] == "model_openai-gpt-image-2" and "model_z-image" in with_query  # featured first again, recents not promoted


def test_query_tokens_match_name_description_tags_and_id():
    assert mf.matches(GPT, "gpt")
    assert mf.matches(GPT, "GPT adherence")
    assert mf.matches(GPT, "openai")
    assert mf.matches(GPT, "third-party")
    assert not mf.matches(GPT, "gpt gemini")
    assert mf.matches(GPT, "")


def test_lane_modality_and_base_lane_cover_every_lane():
    assert mf.LANE_MODALITY["render_image"] == "image" and mf.LANE_MODALITY["render_video"] == "video"
    assert mf.LANE_MODALITY["edit3d"] == "3d" and mf.LANE_MODALITY["material"] == "image" and mf.LANE_MODALITY["audio"] == "audio"
    assert mf.BASE_LANE == {"image": "image", "video": "video", "3d": "3d", "audio": "audio"}


def test_thumbnail_url_and_builtin_icons():
    assert mf.thumbnail_url(LORA) == "https://cdn.example/t.jpg"
    assert mf.thumbnail_url(GPT) is None
    assert mf.thumbnail_url(ModelRecord.from_api({"id": "m", "name": "m", "thumbnail": "junk"})) is None
    assert mf.modality_icon(GEMINI) == 'IMAGE_DATA'
    assert mf.modality_icon(SEEDANCE) == 'FILE_MOVIE'
    assert mf.modality_icon(BANG) == 'MESH_DATA'
    assert mf.modality_icon(ACE) == 'SPEAKER'
    assert mf.modality_icon(LLM) == 'FILE_TEXT'
    assert mf.modality_icon(rec("m", "m", ("weird",))) == 'QUESTION'


def test_recent_models_touch_orders_dedupes_and_limits(tmp_path):
    path = tmp_path / "recent.json"
    recent = mf.RecentModels(path, limit=3)
    assert recent.ids("image") == []
    recent.touch("image", "a")
    recent.touch("image", "b")
    recent.touch("image", "a")
    assert recent.ids("image") == ["a", "b"]
    for m in ("c", "d"):
        recent.touch("image", m)
    assert recent.ids("image") == ["d", "c", "a"]
    assert mf.RecentModels(path).ids("image") == ["d", "c", "a"]
    path.write_text("not json")
    assert mf.RecentModels(path).ids("image") == []
