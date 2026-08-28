# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json

from conftest import FIXTURES
from scenario.core.jobs.records import JobRecord
from scenario.core.scene import material_plan as mp


def typed_fixture_files():
    manifest = json.loads((FIXTURES / "patina-copper-512" / "manifest.json").read_text())
    return [(a["type"], str(FIXTURES / "patina-copper-512" / a["file"])) for a in manifest["assets"]]


def test_plan_maps_every_patina_type():
    plan = mp.plan_material("Copper", typed_fixture_files())
    assert plan.name == "Copper"
    assert set(plan.textures) == {mp.ALBEDO, mp.NORMAL, mp.SMOOTHNESS, mp.METALLIC, mp.HEIGHT, mp.BASE}
    assert plan.textures[mp.ALBEDO].endswith("albedo.png")
    assert plan.invert_smoothness and plan.has_displacement
    assert plan.color_space(mp.ALBEDO) == "sRGB" and plan.color_space(mp.BASE) == "sRGB"
    for role in (mp.NORMAL, mp.SMOOTHNESS, mp.METALLIC, mp.HEIGHT):
        assert plan.color_space(role) == "Non-Color"


def test_plan_without_maps_uses_base_as_color():
    plan = mp.plan_material("Flat", [("inference-txt2img-texture", "/x/base.png")])
    assert plan.base_color_path == "/x/base.png"
    assert not plan.has_displacement and not plan.invert_smoothness


def test_plan_accepts_roughness_typed_asset_without_inversion():
    plan = mp.plan_material("R", [("texture-albedo", "/a.png"), ("texture-roughness", "/r.png")])
    assert plan.textures[mp.ROUGHNESS] == "/r.png" and not plan.invert_smoothness


def test_roles_from_record_pairs_files_with_asset_types():
    rec = JobRecord.new(lane="material", kind="material", model_id="model_patina-material", body={})
    rec.asset_ids = ["a1", "a2"]
    rec.asset_types = {"a1": "texture-albedo", "a2": "texture-normal"}
    rec.files = ["/out/1.png", "/out/2.png"]
    assert mp.roles_from_record(rec) == [("texture-albedo", "/out/1.png"), ("texture-normal", "/out/2.png")]
