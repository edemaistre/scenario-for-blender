# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import base64

import pytest

from fakes import FakeTransport
from scenario.core.api.client import ScenarioClient
from scenario.core.api.errors import NetworkError, ScenarioError


def make(transport, **kw):
    sleeps = []
    client = ScenarioClient("api_key", "secret", transport=transport, sleep=sleeps.append, **kw)
    return client, sleeps


def test_get_sends_basic_auth_and_query():
    t = FakeTransport().queue(200, {"models": []})
    client, _ = make(t)
    out = client.get("/models", query={"pageSize": 1, "privacy": "public"})
    assert out == {"models": []}
    call = t.calls[0]
    expected = "Basic " + base64.b64encode(b"api_key:secret").decode()
    assert call["headers"]["Authorization"] == expected
    assert call["method"] == "GET"
    assert call["url"] == "https://api.cloud.scenario.com/v1/models?pageSize=1&privacy=public"
    assert call["body"] is None


def test_post_sends_json_body_and_content_type():
    t = FakeTransport().queue(200, {"job": {"jobId": "job_1"}})
    client, _ = make(t)
    client.post("/generate/custom/model_x", json_body={"prompt": "hi", "numOutputs": 1})
    call = t.calls[0]
    assert call["headers"]["Content-Type"] == "application/json"
    assert t.last_json() == {"prompt": "hi", "numOutputs": 1}


def test_dry_run_status_269_is_success():
    t = FakeTransport().queue(269, {"creativeUnitsCost": 7.25})
    client, _ = make(t)
    assert client.post("/generate/custom/m", query={"dryRun": "true"}, json_body={})["creativeUnitsCost"] == 7.25
    assert t.calls[0]["url"].endswith("?dryRun=true")


def test_error_maps_reason_and_trace_id():
    t = FakeTransport().queue(400, {"reason": "Input prompt is required", "trace_id": "tr_1"})
    client, _ = make(t)
    with pytest.raises(ScenarioError) as exc:
        client.post("/generate/custom/m", json_body={})
    assert exc.value.status == 400
    assert exc.value.reason == "Input prompt is required"
    assert exc.value.trace_id == "tr_1"
    assert exc.value.path == "/generate/custom/m"


def test_403_message_field_is_used_as_reason():
    t = FakeTransport().queue(403, {"message": "API Keys cannot access protected resources"})
    client, _ = make(t)
    with pytest.raises(ScenarioError) as exc:
        client.get("/me")
    assert "protected resources" in exc.value.reason


def test_retries_on_503_then_succeeds():
    t = FakeTransport().queue(503, {"message": "busy"}).queue(200, {"ok": True})
    client, sleeps = make(t)
    assert client.get("/models") == {"ok": True}
    assert len(t.calls) == 2
    assert sleeps == [1.0]


def test_429_uses_remaining_seconds_capped():
    t = FakeTransport().queue(429, {"reason": "cooldown", "remainingSeconds": 900}).queue(200, {"ok": True})
    client, sleeps = make(t)
    client.get("/models")
    assert sleeps == [30.0]


def test_network_error_after_retries():
    t = FakeTransport()
    t.raise_network = 10
    client, sleeps = make(t, max_retries=2)
    with pytest.raises(NetworkError):
        client.get("/models")
    assert len(t.calls) == 3
    assert sleeps == [1.0, 2.0]


def test_non_json_body_becomes_reason_text():
    t = FakeTransport().queue(502, b"<html>Bad gateway</html>")
    client, _ = make(t, max_retries=0)
    with pytest.raises(ScenarioError) as exc:
        client.get("/models")
    assert "Bad gateway" in exc.value.reason
