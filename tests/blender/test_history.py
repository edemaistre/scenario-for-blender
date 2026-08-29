# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

import bpy

from helpers import addon_name, submodule


class HistoryTests(unittest.TestCase):
    def setUp(self):
        prefs = bpy.context.preferences.addons[addon_name()].preferences
        self._saved = (prefs.api_key, prefs.api_secret)
        prefs.api_key, prefs.api_secret = prefs.api_key or "k", prefs.api_secret or "s"

    def tearDown(self):
        prefs = bpy.context.preferences.addons[addon_name()].preferences
        prefs.api_key, prefs.api_secret = self._saved

    def test_history_event_populates_state(self):
        runtime = submodule("blender.runtime")
        handlers = submodule("blender.handlers")
        runtime.state.reset()
        runtime.ensure_manager()
        jobs = [{"jobId": "job_h", "jobType": "custom", "status": "success", "createdAt": "2026-08-28T07:37:09.434Z",
                 "metadata": {"input": {"modelId": "model_g", "prompt": "hello"}, "assetIds": ["asset_1"]}}]
        handlers.dispatch(("history", {"jobs": jobs, "token": "tok2", "append": False}))
        self.assertEqual([e.job_id for e in runtime.state.history], ["job_h"])
        self.assertEqual(runtime.state.history_token, "tok2")
        handlers.dispatch(("history", {"jobs": jobs, "token": None, "append": True}))
        self.assertEqual(len(runtime.state.history), 1)


class GenerationListTests(unittest.TestCase):
    def setUp(self):
        self.runtime = submodule("blender.runtime")
        self.records = submodule("core.jobs.records")
        self.runtime.state.reset()

    def _job(self, error=None, status="success"):
        job = self.records.JobRecord.new(lane="3d", kind="3d", model_id="model_x", body={}, meta={"prompt": "p"})
        job.status = status
        job.error = error
        return job

    def test_collapse_results_collapses_all_then_expands_all(self):
        a, b = self._job(), self._job()
        self.runtime.state.jobs_view.extend([a, b])
        bpy.ops.scenario.collapse_results()  # any open -> collapse all
        self.assertTrue(a.meta["collapsed"] and b.meta["collapsed"])
        bpy.ops.scenario.collapse_results()  # all closed -> expand all
        self.assertFalse(a.meta["collapsed"] or b.meta["collapsed"])

    def test_error_details_description_is_the_full_message(self):
        from bl_ext.user_default.scenario.blender.operators import SCENARIO_OT_error_details
        long_error = "The model file is too large for processing. Try reducing the resolution. [Error ID: error_ABC123]"
        job = self._job(error=long_error, status="failed")
        self.runtime.state.jobs_view.append(job)

        class P:
            local_id = job.local_id
        self.assertEqual(SCENARIO_OT_error_details.description(bpy.context, P()), long_error)
