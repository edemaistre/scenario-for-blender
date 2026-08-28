# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
from scenario.core.api.catalog import ModelRecord
from scenario.core.api.model_filter import FILTERS, RecentModels, filter_records, matches, modality_icon, thumbnail_url


def rec(model_id, name, caps=("txt2img",), tags=(), desc="", thumb=None):
    data = {"id": model_id, "name": name, "capabilities": list(caps), "tags": list(tags), "shortDescription": desc}
    if thumb:
        data["thumbnail"] = {"assetId": "asset_x", "url": thumb}
    return ModelRecord.from_api(data)


GPT = rec("model_openai-gpt-image-2", "GPT Image 2", tags=("sc:featured", "sc:third-party"), desc="Best-in-class prompt adherence")
GEMINI = rec("model_google-gemini-3-1-flash", "Gemini 3.1", ("txt2img", "img2img", "video2img"), ("sc:featured", "sc:third-party"), "Google image model")
CHIBIS = rec("model_3Dchibis", "3D Chibis", tags=("sc:scenario",), desc="Cute chibi characters", thumb="https://cdn.example/thumb.jpg")
ZIMAGE = rec("model_z-image", "Z-Image", tags=("sc:third-party",), desc="Fast open model")
ALL = [ZIMAGE, CHIBIS, GEMINI, GPT]


def test_query_tokens_match_name_description_tags_and_id():
    assert matches(GPT, "gpt")
    assert matches(GPT, "GPT adherence")
    assert matches(GPT, "openai")           # id fragment
    assert matches(GPT, "third-party")      # tag
    assert not matches(GPT, "gpt gemini")   # every token must match
    assert matches(GPT, "")


def test_all_chip_sorts_featured_first_then_name():
    out = [r.id for r in filter_records(ALL)]
    assert out == ["model_google-gemini-3-1-flash", "model_openai-gpt-image-2", "model_3Dchibis", "model_z-image"]


def test_chips_filter_by_tag():
    assert [r.id for r in filter_records(ALL, chip="featured")] == ["model_google-gemini-3-1-flash", "model_openai-gpt-image-2"]
    assert [r.id for r in filter_records(ALL, chip="scenario")] == ["model_3Dchibis"]
    assert [r.id for r in filter_records(ALL, chip="third_party")] == ["model_google-gemini-3-1-flash", "model_openai-gpt-image-2", "model_z-image"]


def test_recent_chip_keeps_recent_order_and_drops_others():
    out = [r.id for r in filter_records(ALL, chip="recent", recent_ids=["model_z-image", "model_openai-gpt-image-2", "model_gone"])]
    assert out == ["model_z-image", "model_openai-gpt-image-2"]


def test_query_combines_with_chip():
    assert [r.id for r in filter_records(ALL, query="image", chip="featured")] == ["model_google-gemini-3-1-flash", "model_openai-gpt-image-2"]
    assert filter_records(ALL, query="nothing-here") == []


def test_filters_enum_has_expected_identifiers():
    assert [f[0] for f in FILTERS] == ["all", "featured", "scenario", "third_party", "recent"]


def test_thumbnail_url_reads_raw_dict_or_none():
    assert thumbnail_url(CHIBIS) == "https://cdn.example/thumb.jpg"
    assert thumbnail_url(GPT) is None
    assert thumbnail_url(ModelRecord.from_api({"id": "m", "name": "m", "thumbnail": "junk"})) is None


def test_modality_icon_uses_output_side_of_capabilities():
    assert modality_icon(GEMINI) == 'IMAGE_DATA'                                     # video2img is still an image model
    assert modality_icon(rec("m", "m", ("txt2video", "img2video", "video2video"))) == 'FILE_MOVIE'
    assert modality_icon(rec("m", "m", ("img23d",))) == 'MESH_DATA'
    assert modality_icon(rec("m", "m", ("3d23d",))) == 'MESH_DATA'
    assert modality_icon(rec("m", "m", ("video23d",))) == 'MESH_DATA'
    assert modality_icon(rec("m", "m", ("txt2audio", "audio2audio"))) == 'SPEAKER'
    assert modality_icon(rec("m", "m", ("txt2txt", "img2txt"))) == 'FILE_TEXT'
    assert modality_icon(rec("m", "m", ("controlnet",))) == 'QUESTION'
    assert modality_icon(None) == 'QUESTION'


def test_recent_models_touch_orders_dedupes_and_limits(tmp_path):
    path = tmp_path / "recent.json"
    recent = RecentModels(path, limit=3)
    assert recent.ids("image") == []
    recent.touch("image", "a")
    recent.touch("image", "b")
    recent.touch("image", "a")
    assert recent.ids("image") == ["a", "b"]
    recent.touch("image", "c")
    recent.touch("image", "d")
    assert recent.ids("image") == ["d", "c", "a"]
    assert recent.ids("video") == []
    assert RecentModels(path).ids("image") == ["d", "c", "a"]  # persisted


def test_recent_models_tolerates_missing_and_corrupt_files(tmp_path):
    assert RecentModels(tmp_path / "missing" / "recent.json").ids("image") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    recent = RecentModels(bad)
    assert recent.ids("image") == []
    recent.touch("image", "a")
    assert RecentModels(bad).ids("image") == ["a"]
    (tmp_path / "list.json").write_text("[1, 2]")
    assert RecentModels(tmp_path / "list.json").ids("image") == []
