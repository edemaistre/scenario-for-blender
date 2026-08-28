# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json

from conftest import FIXTURES
from scenario.core.api.catalog import ModelRecord
from scenario.core.schema.params import build_body, missing_required_files, parse_schema, validate


def record(name):
    return ModelRecord.from_api(json.loads((FIXTURES / "models" / f"{name}.json").read_text())["model"])


def spec_by_name(schema, name):
    return next(s for s in schema.specs if s.name == name)


def test_parse_patina_schema():
    schema = parse_schema(record("model_patina-material"))
    assert schema.prompt_name == "prompt"
    prompt = spec_by_name(schema, "prompt")
    assert prompt.required_always and prompt.is_prompt and prompt.max_length == 2048
    width = spec_by_name(schema, "width")
    assert width.ptype == "number" and width.is_integer and (width.min, width.max, width.step) == (512, 2048, 16)
    assert width.cost_impact and width.group == "Settings"
    maps = spec_by_name(schema, "maps")
    assert maps.ptype == "string_array" and maps.is_array
    assert maps.allowed_values == ("basecolor", "normal", "roughness", "metalness", "height")
    assert maps.allowed_labels["basecolor"] == "Base Color"
    upscale = spec_by_name(schema, "upscaleFactor")
    assert upscale.allowed_values == (0, 2, 4) and upscale.allowed_labels[0] == "None"
    mask = spec_by_name(schema, "mask")
    assert mask.is_file and mask.kind == "image" and not mask.is_array
    image = spec_by_name(schema, "image")
    assert image.required_if_defined == ("mask",)
    assert [p["label"] for p in schema.resolution_presets][:2] == ["1:1 (512x512)", "1:1 (1024x1024)"]


def test_parse_gemini_file_array_and_enum():
    schema = parse_schema(record("model_google-gemini-3-1-flash"))
    refs = spec_by_name(schema, "referenceImages")
    assert refs.is_file and refs.is_array and refs.kind == "image"
    res = spec_by_name(schema, "resolution")
    assert res.allowed_values == ("512", "1K", "2K", "4K") and res.default == "1K"


def test_build_body_matches_recorded_job_input():
    schema = parse_schema(record("model_patina-material"))
    job = json.loads((FIXTURES / "patina-copper-512" / "job.json").read_text())["job"]
    recorded = dict(job["metadata"]["input"])
    recorded.pop("modelId")
    recorded.pop("seed")
    values = {"prompt": "weathered copper patina with verdigris streaks", "width": 512.0, "height": 512.0,
              "maps": ["basecolor", "normal", "roughness", "metalness", "height"], "numOutputs": 1.0,
              "upscaleFactor": None, "tilingMode": "", "seed": None}
    body = build_body(schema.specs, values, files={})
    assert body == recorded


def test_build_body_files_scalar_vs_array_and_disabled_optionals():
    schema = parse_schema(record("model_google-gemini-3-1-flash"))
    body = build_body(schema.specs, {"prompt": "x", "resolution": "2K", "numOutputs": 2}, files={"referenceImages": ["asset_a", "asset_b"]},
                      enabled={"resolution": False})
    assert body["referenceImages"] == ["asset_a", "asset_b"]
    assert "resolution" not in body and body["numOutputs"] == 2
    patina = parse_schema(record("model_patina-material"))
    body = build_body(patina.specs, {"prompt": "x"}, files={"image": ["asset_1"]})
    assert body["image"] == "asset_1"


def test_validate_rules():
    schema = parse_schema(record("model_patina-material"))
    assert validate(schema.specs, {}) == ["Prompt is required"]
    errors = validate(schema.specs, {"prompt": "x" * 3000, "width": 100, "tilingMode": "diagonal", "mask": "asset_m"})
    assert "Prompt is longer than 2048 characters" in errors
    assert "Width must be between 512 and 2048" in errors
    assert "Tiling Mode must be one of both, horizontal, vertical" in errors
    assert "Image is required when Mask is set" in errors
    assert validate(schema.specs, {"prompt": "ok"}) == []


def test_missing_required_files():
    schema = parse_schema(record("model_patina"))
    assert missing_required_files(schema.specs, {}) == ["image"]
    assert missing_required_files(schema.specs, {"image": "asset_x"}) == []
