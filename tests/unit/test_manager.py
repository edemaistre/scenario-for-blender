# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import pathlib

from conftest import FIXTURES
from fakes import FakeTransport
from scenario.core import config
from scenario.core.api.client import ScenarioClient
from scenario.core.jobs.manager import JobManager
from scenario.core.jobs.records import JobRecord, JobRegistry


def paths(tmp_path):
    return config.Paths(state_dir=tmp_path / "state", cache_dir=tmp_path / "cache", output_dir=tmp_path / "out")


def make_manager(tmp_path, transport, downloader=None, uploader=None):
    client = ScenarioClient("k", "s", transport=transport, sleep=lambda s: None)
    registry = JobRegistry(paths(tmp_path).registry_file)
    return JobManager(lambda: client, registry, paths(tmp_path), sleep=lambda s: None,
                      downloader=downloader or (lambda url, dest, **kw: dest.write_bytes(b"data") or dest),
                      uploader=uploader)


def events_of(kind, events):
    return [payload for name, payload in events if name == kind]


def test_record_roundtrip():
    rec = JobRecord.new(lane="image", kind="image", model_id="model_x", body={"prompt": "p"})
    rec.job_id = "job_1"
    again = JobRecord.from_dict(json.loads(json.dumps(rec.to_dict())))
    assert again.local_id == rec.local_id and again.job_id == "job_1" and again.status == "submitting"
    assert not again.is_terminal


def test_submit_runs_to_completion_and_downloads(tmp_path):
    job = json.loads((FIXTURES / "patina-copper-512" / "job.json").read_text())
    manifest = json.loads((FIXTURES / "patina-copper-512" / "manifest.json").read_text())
    running = {"job": dict(job["job"], status="in-progress", progress=0.4)}
    t = FakeTransport().queue(200, job).queue(200, running).queue(200, job)
    for asset in manifest["assets"]:
        t.queue(200, {"asset": {"id": asset["assetId"], "url": f"https://cdn/{asset['assetId']}", "mimeType": "image/png", "metadata": {"type": asset["type"]}}})
    manager = make_manager(tmp_path, t)
    rec = manager.submit("material", "material", "model_patina-material", {"prompt": "copper"})
    assert rec.local_id and rec.lane == "material"  # the worker may already be running
    manager.join(timeout=5)
    events = manager.drain()
    kinds = [name for name, _ in events]
    assert kinds[0] == "job" and kinds[-1] == "job_done"
    done = events_of("job_done", events)[0]
    assert done.job_id == "job_KWxxsnSdVXDFZRMsoCvLTmKY" and done.status == "success" and done.cu_cost == 6.0
    assert len(done.files) == 6
    assert all((tmp_path / "out" / "materials") in pathlib.Path(p).parents for p in done.files)
    assert done.asset_types[manifest["assets"][0]["assetId"]] == manifest["assets"][0]["type"]
    reloaded = JobRegistry(paths(tmp_path).registry_file)
    reloaded.load()
    assert reloaded.by_local_id(rec.local_id).status == "success"
    assert not manager.has_active()


def test_submit_uploads_files_first(tmp_path):
    t = FakeTransport().queue(200, {"job": {"jobId": "job_2", "status": "queued"}}).queue(200, {"job": {"jobId": "job_2", "status": "failure", "error": "nsfw"}})
    uploads = []

    def uploader(client, path, kind=None, transport=None):
        uploads.append(str(path))
        return f"asset_{len(uploads)}"

    manager = make_manager(tmp_path, t, uploader=uploader)
    manager.submit("image", "image", "model_g", {"prompt": "p"}, files={"referenceImages": ["/tmp/a.png", "/tmp/b.png"], "image": ["/tmp/c.png"]}, array_params={"referenceImages"})
    manager.join(timeout=5)
    body = json.loads(t.calls[0]["body"])
    assert body["referenceImages"] == ["asset_1", "asset_2"] and body["image"] == "asset_3"
    events = manager.drain()
    failed = events_of("job_failed", events)[0]
    assert failed.status == "failure" and failed.error == "nsfw"


def test_estimate_event_and_error(tmp_path):
    t = FakeTransport().queue(269, {"creativeUnitsCost": 13.25}).queue(400, {"reason": "Input prompt is required"})
    manager = make_manager(tmp_path, t)
    manager.estimate("image:model_g:1", "model_g", {"prompt": "p"})
    manager.join(timeout=5)
    manager.estimate("image:model_g:2", "model_g", {})
    manager.join(timeout=5)
    results = events_of("estimate", manager.drain())
    by_key = {r.key: r for r in results}
    assert by_key["image:model_g:1"].cu_cost == 13.25 and by_key["image:model_g:1"].error is None
    assert by_key["image:model_g:2"].cu_cost is None and "prompt" in by_key["image:model_g:2"].error


def test_resume_polls_unfinished_jobs(tmp_path):
    registry = JobRegistry(paths(tmp_path).registry_file)
    rec = JobRecord.new(lane="image", kind="image", model_id="model_g", body={})
    rec.job_id, rec.status = "job_9", "in-progress"
    registry.add(rec)
    registry.save()
    t = FakeTransport().queue(200, {"job": {"jobId": "job_9", "status": "canceled"}})
    manager = make_manager(tmp_path, t)
    manager.registry.load()
    manager.resume()
    manager.join(timeout=5)
    assert events_of("job_failed", manager.drain())[0].status == "canceled"
    assert t.calls[0]["url"].endswith("/jobs/job_9")
