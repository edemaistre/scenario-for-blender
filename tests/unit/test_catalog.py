# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import urllib.parse

from conftest import FIXTURES
from fakes import FakeTransport
from scenario.core.api.catalog import Catalog, ModelRecord, models_for_lane
from scenario.core.api.client import ScenarioClient


def load(name):
    return json.loads((FIXTURES / "models" / f"{name}.json").read_text())


def test_model_record_from_api_reads_schema_and_lanes():
    rec = ModelRecord.from_api(load("model_patina-material")["model"])
    assert rec.id == "model_patina-material"
    assert "txt2img" in rec.capabilities
    assert len(rec.parameters) == 15
    assert rec.ui_config["selects"]["maps"]["basecolor"] == "Base Color"
    assert rec.lanes == {"image", "material"}
    assert rec.deprecated_successor is None


def test_deprecated_tag_names_successor():
    rec = ModelRecord.from_api({"id": "model_old", "name": "Old", "capabilities": ["img23d"], "tags": ["deprecated:model_new"]})
    assert rec.deprecated_successor == "model_new"
    assert rec.lanes == {"3d"}


def test_fetch_list_paginates_and_caches(tmp_path):
    page1 = json.loads((FIXTURES / "models_list_page1.json").read_text())
    t = FakeTransport().queue(200, page1).queue(200, {"models": [{"id": "model_last", "name": "Last", "capabilities": ["txt2video"]}]})
    catalog = Catalog(ScenarioClient("k", "s", transport=t), tmp_path)
    records = catalog.fetch_list(privacy="public", page_size=5)
    assert len(records) == len(page1["models"]) + 1
    assert "pageSize=5" in t.calls[0]["url"] and "privacy=public" in t.calls[0]["url"]
    query = urllib.parse.parse_qs(urllib.parse.urlparse(t.calls[1]["url"]).query)
    assert query["paginationToken"] == [page1["nextPaginationToken"]]
    cached = catalog.load_list_cached("public")
    assert [r.id for r in cached] == [r.id for r in records]
    assert catalog.load_list_cached("private") is None


def test_get_uses_disk_cache_then_refreshes(tmp_path):
    payload = load("model_patina-material")
    t = FakeTransport().queue(200, payload).queue(200, payload)
    catalog = Catalog(ScenarioClient("k", "s", transport=t), tmp_path)
    rec = catalog.get("model_patina-material")
    assert rec.name == "PATINA Material"
    assert (tmp_path / "models" / "model_patina-material.json").exists()
    catalog.get("model_patina-material")
    assert len(t.calls) == 1
    catalog.get("model_patina-material", refresh=True)
    assert len(t.calls) == 2


def test_models_for_lane_orders_curated_first_and_drops_deprecated():
    records = [
        ModelRecord.from_api({"id": "model_zeta", "name": "Zeta", "capabilities": ["txt2img"]}),
        ModelRecord.from_api({"id": "model_google-gemini-3-1-flash", "name": "Gemini", "capabilities": ["txt2img", "img2img"]}),
        ModelRecord.from_api({"id": "model_old", "name": "Old", "capabilities": ["txt2img"], "tags": ["deprecated:model_zeta"]}),
        ModelRecord.from_api({"id": "model_video", "name": "Vid", "capabilities": ["txt2video"]}),
        ModelRecord.from_api({"id": "model_patina", "name": "Patina maps", "capabilities": ["img2img"]}),
    ]
    image = [r.id for r in models_for_lane("image", records)]
    assert image[0] == "model_google-gemini-3-1-flash"
    assert "model_old" not in image and "model_video" not in image
    assert image[-1] == "model_zeta"
    assert [r.id for r in models_for_lane("material", records)] == ["model_patina"]
    assert [r.id for r in models_for_lane("video", records)] == ["model_video"]
