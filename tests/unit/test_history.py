# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
from scenario.core import history
from scenario.core.jobs.records import JobRecord


def test_entries_merge_cloud_jobs_with_local_files():
    local = JobRecord.new(lane="image", kind="image", model_id="model_g", body={})
    local.job_id, local.status, local.files = "job_a", "success", ["/out/a.png"]
    jobs = [
        {"jobId": "job_a", "jobType": "custom", "status": "success", "createdAt": "2026-08-28T07:37:09.434Z", "billing": {"cuCost": 6},
         "metadata": {"input": {"modelId": "model_g", "prompt": "teapot"}, "assetIds": ["asset_1"]}},
        {"jobId": "job_b", "jobType": "upload", "status": "success", "createdAt": "2026-08-28T07:40:00.000Z", "metadata": {"input": {}}},
        {"jobId": "job_c", "jobType": "custom", "status": "failure", "createdAt": "2026-08-28T08:00:00.000Z", "metadata": {"input": {"modelId": "model_m", "prompt": "x"}, "assetIds": []}},
    ]
    entries = history.entries_from_jobs(jobs, [local], kinds={"model_m": "3d"})
    assert [e.job_id for e in entries] == ["job_c", "job_a"]
    a = entries[1]
    assert a.local_files == ["/out/a.png"] and a.prompt == "teapot" and a.cu_cost == 6.0 and a.kind == "image"
    assert entries[0].kind == "3d" and entries[0].status == "failure"


def test_prompt_asset_ids_are_hidden_until_resolved():
    jobs = [{"jobId": "job_p", "jobType": "custom", "status": "success", "createdAt": "2026-08-28T09:00:00.000Z",
             "metadata": {"input": {"modelId": "model_g", "prompt": "asset_Lq9G6auxQxXpiWiahw6K5nc6"}, "assetIds": ["a"]}}]
    assert history.prompt_asset_ids(jobs) == ["asset_Lq9G6auxQxXpiWiahw6K5nc6"]
    assert history.entries_from_jobs(jobs, [])[0].prompt == ""
    history.resolve_prompts(jobs, {"asset_Lq9G6auxQxXpiWiahw6K5nc6": "mossy stone wall"})
    assert history.entries_from_jobs(jobs, [])[0].prompt == "mossy stone wall"
    assert history.prompt_asset_ids(jobs) == []
