# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import pytest

from scenario.core.api import llm
from scenario.core.api.client import ScenarioClient
from scenario.core.api.errors import ScenarioError

from fakes import FakeTransport


def _client(transport):
    return ScenarioClient("key", "secret", transport=transport, sleep=lambda s: None)


def _job(status, asset_ids=(), **meta):
    metadata = {"assetIds": list(asset_ids)}
    metadata.update(meta)
    return {"job": {"jobId": "job_llm", "status": status, "metadata": metadata}}


def test_run_text_submits_polls_and_reads_the_text_asset():
    t = (FakeTransport()
         .queue(200, _job("queued"))
         .queue(200, _job("in-progress"))
         .queue(200, _job("success", ["asset_txt"]))
         .queue(200, {"asset": {"id": "asset_txt", "metadata": {"type": "text", "preview": "  A rusty robot in a lush jungle  "}}}))
    text = llm.run_text(_client(t), "Describe this", text_inputs=["hello"], images=["asset_img"], sleep=lambda s: None)
    assert text == "A rusty robot in a lush jungle"
    submit = t.calls[0]
    assert submit["method"] == "POST" and submit["url"].endswith("/generate/custom/model_scenario-llm")
    import json
    assert json.loads(submit["body"]) == {"instruction": "Describe this", "numOutputs": 1, "model": "gemini-3.5-flash-lite", "textInputs": ["hello"], "images": ["asset_img"]}
    assert t.calls[1]["url"].endswith("/jobs/job_llm") and t.calls[2]["url"].endswith("/jobs/job_llm")
    assert t.calls[3]["url"].endswith("/assets/asset_txt")


def test_run_text_prefers_inline_metadata_text_when_present():
    t = FakeTransport().queue(200, _job("success", ["asset_txt"], text="Inline answer"))
    assert llm.run_text(_client(t), "Q") == "Inline answer"
    assert len(t.calls) == 1  # no asset fetch needed


def test_run_text_fails_on_a_failed_job_with_its_reason():
    t = FakeTransport().queue(200, _job("failure", error="model unavailable", hint="try later"))
    with pytest.raises(ScenarioError) as err:
        llm.run_text(_client(t), "Q")
    assert "model unavailable" in str(err.value)


def test_run_text_times_out_after_max_polls():
    t = FakeTransport().queue(200, _job("queued")).queue(200, _job("queued")).queue(200, _job("queued"))
    with pytest.raises(ScenarioError) as err:
        llm.run_text(_client(t), "Q", max_polls=2, sleep=lambda s: None)
    assert "did not finish" in str(err.value)


def test_run_text_raises_when_the_asset_has_no_text():
    t = FakeTransport().queue(200, _job("success", ["asset_txt"])).queue(200, {"asset": {"id": "asset_txt", "metadata": {}}})
    with pytest.raises(ValueError):
        llm.run_text(_client(t), "Q")


def test_translate_wraps_the_text_as_an_input_with_the_translation_instruction():
    t = FakeTransport().queue(200, _job("success", ["asset_txt"])).queue(200, {"asset": {"metadata": {"preview": "a copper teapot"}}})
    assert llm.translate(_client(t), "une théière en cuivre") == "a copper teapot"
    import json
    body = json.loads(t.calls[0]["body"])
    assert body["textInputs"] == ["une théière en cuivre"]
    assert "English" in body["instruction"] and "only the translation" in body["instruction"]


def test_estimate_text_uses_the_dry_run_query_parameter():
    t = FakeTransport().queue(269, {"creativeUnitsCost": 0.5, "costDetails": {"custom-generation": 0.5}})
    assert llm.estimate_text(_client(t), "Q") == 0.5
    assert "dryRun=true" in t.calls[0]["url"]
