# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from scenario.core.api import spark
from scenario.core.api.client import ScenarioClient

from fakes import FakeTransport


def _client(transport):
    return ScenarioClient("key", "secret", transport=transport, sleep=lambda s: None)


def test_spark_posts_generate_prompt_and_returns_prompt_strings():
    transport = FakeTransport().queue(200, {"prompts": ["A grey clay robot", {"prompt": "A second one"}, ""], "mode": "structured"})
    prompts = spark.spark(_client(transport), prompt="a robot", model_id="model_x", images=["asset_1"], num_results=2)
    assert prompts == ["A grey clay robot", "A second one"]
    call = transport.calls[0]
    assert call["method"] == "POST" and call["url"].endswith("/generate/prompt")
    assert transport.last_json() == {"numResults": 2, "prompt": "a robot", "modelId": "model_x", "images": ["asset_1"]}


def test_spark_without_model_or_prompt_sends_minimal_body_and_clamps_results():
    transport = FakeTransport().queue(200, {"prompts": ["x"]})
    spark.spark(_client(transport), num_results=9)
    assert transport.last_json() == {"numResults": 5}


def test_spark_raises_when_no_prompt_comes_back():
    transport = FakeTransport().queue(200, {"prompts": []})
    with pytest.raises(ValueError):
        spark.spark(_client(transport), prompt="a robot")


def test_estimate_uses_the_dry_run_query_parameter():
    transport = FakeTransport().queue(269, {"creativeUnitsCost": 3.75, "costDetails": {"prompt": 3.75}})
    assert spark.estimate(_client(transport), prompt="a robot", model_id="model_x") == 3.75
    assert "dryRun=true" in transport.calls[0]["url"]


def test_data_url_inlines_png(tmp_path):
    png = tmp_path / "cap.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    assert spark.data_url(png).startswith("data:image/png;base64,")
