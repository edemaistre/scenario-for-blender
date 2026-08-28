# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import base64
import json

from conftest import FIXTURES
from fakes import FakeTransport
from scenario.core.api import assets, generate, jobs
from scenario.core.api.client import ScenarioClient


def client(t):
    return ScenarioClient("k", "s", transport=t, sleep=lambda s: None)


def test_submit_and_estimate():
    job = json.loads((FIXTURES / "patina-copper-512" / "job.json").read_text())
    dry = json.loads((FIXTURES / "patina-copper-512" / "dryrun_response.json").read_text())
    t = FakeTransport().queue(200, job).queue(269, dry)
    c = client(t)
    submitted = generate.submit(c, "model_patina-material", {"prompt": "x"})
    assert submitted["jobId"] == "job_KWxxsnSdVXDFZRMsoCvLTmKY"
    assert t.calls[0]["url"].endswith("/generate/custom/model_patina-material")
    est = generate.estimate(c, "model_patina-material", {"prompt": "x"})
    assert est.cu_cost == 7.25 and est.details["quality-gate"] == 1.25
    assert t.calls[1]["url"].endswith("/generate/custom/model_patina-material?dryRun=true")
    assert "dryRun" not in t.last_json()


def test_job_helpers():
    job = json.loads((FIXTURES / "patina-copper-512" / "job.json").read_text())["job"]
    assert jobs.is_terminal("success") and jobs.is_terminal("failure") and jobs.is_terminal("canceled")
    assert not jobs.is_terminal("in-progress") and not jobs.is_terminal("queued")
    assert jobs.is_success("success") and not jobs.is_success("failure")
    assert len(jobs.asset_ids(job)) == 6
    assert jobs.upload_entity_id({"metadata": {"output": {"entityId": "asset_x"}}}) == "asset_x"
    assert jobs.upload_entity_id(job) is None


def test_get_and_list_jobs():
    t = FakeTransport().queue(200, {"job": {"jobId": "job_1", "status": "queued"}}).queue(200, {"jobs": [{"jobId": "job_2"}], "nextPaginationToken": "tok"})
    c = client(t)
    assert jobs.get_job(c, "job_1")["status"] == "queued"
    rows, token = jobs.list_jobs(c, page_size=20)
    assert rows[0]["jobId"] == "job_2" and token == "tok"
    assert "pageSize=20" in t.calls[1]["url"]


def test_get_asset_and_download(tmp_path):
    asset = json.loads((FIXTURES / "patina-copper-512" / "manifest.json").read_text())["assets"][0]
    t = FakeTransport().queue(200, {"asset": {"id": asset["assetId"], "url": "https://cdn.example/a.png", "mimeType": "image/png", "metadata": {"type": asset["type"]}}})
    c = client(t)
    rec = assets.get_asset(c, asset["assetId"])
    assert rec["mimeType"] == "image/png"
    dl = FakeTransport().queue(200, b"\x89PNG fake")
    dest = assets.download_file("https://cdn.example/a.png", tmp_path / "sub" / "a.png", transport=dl)
    assert dest.read_bytes() == b"\x89PNG fake"
    assert "Authorization" not in dl.calls[0]["headers"]


def test_upload_image_base64(tmp_path):
    png = FIXTURES / "patina-copper-512" / "metallic.png"
    t = FakeTransport().queue(200, {"asset": {"id": "asset_new", "status": "imported"}})
    asset_id = assets.upload_image_base64(client(t), png, name="metallic.png")
    assert asset_id == "asset_new"
    body = t.last_json()
    assert body["name"] == "metallic.png"
    prefix = "data:image/png;base64,"
    assert body["image"].startswith(prefix)
    assert base64.b64decode(body["image"][len(prefix):]) == png.read_bytes()


def test_upload_multipart_flow(tmp_path):
    src = tmp_path / "clip.mp4"
    src.write_bytes(b"0" * 1000)
    t = FakeTransport()
    t.queue(200, {"upload": {"id": "upl_1", "jobId": "job_u", "parts": [{"number": 1, "url": "https://s3.example/part1"}]}})
    t.queue(200, b"")  # PUT part
    t.queue(200, {"upload": {"id": "upl_1", "status": "validating"}})
    t.queue(200, {"job": {"jobId": "job_u", "status": "in-progress", "metadata": {"output": {}}}})
    t.queue(200, {"job": {"jobId": "job_u", "status": "success", "metadata": {"output": {"entityId": "asset_vid"}}}})
    asset_id = assets.upload_multipart(client(t), src, kind="video", transport=t, sleep=lambda s: None)
    assert asset_id == "asset_vid"
    create = t.calls[0]
    assert create["url"].endswith("/uploads")
    assert json.loads(create["body"]) == {"fileName": "clip.mp4", "fileSize": 1000, "contentType": "video/mp4", "kind": "video", "parts": 1}
    put = t.calls[1]
    assert put["method"] == "PUT" and put["url"] == "https://s3.example/part1" and put["body"] == b"0" * 1000
    assert "Authorization" not in put["headers"] and put["headers"]["Content-Type"] == "video/mp4"
    assert t.calls[2]["url"].endswith("/uploads/upl_1/action") and json.loads(t.calls[2]["body"]) == {"action": "complete"}
    assert t.calls[3]["url"].endswith("/jobs/job_u")


def test_kind_and_mime_for_path():
    assert assets.kind_for_path("a.PNG") == "image" and assets.mime_for_path("a.PNG") == "image/png"
    assert assets.kind_for_path("b.mp4") == "video" and assets.kind_for_path("c.glb") == "3d"
    assert assets.kind_for_path("d.wav") == "audio" and assets.mime_for_path("e.glb") == "model/gltf-binary"
