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
