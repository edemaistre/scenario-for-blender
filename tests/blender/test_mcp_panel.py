# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from helpers import submodule


class McpPanelTests(unittest.TestCase):
    def test_client_configs_carry_url_and_token(self):
        runtime = submodule("blender.runtime")
        service = submodule("blender.mcp_service")
        runtime.state.mcp_token = "tok123"
        configs = service.client_configs()
        for key in ("claude_code", "cursor", "claude_desktop", "codex", "curl"):
            self.assertIn("tok123", configs[key], key)
            self.assertIn("/mcp", configs[key], key)
        self.assertIn("stdio_shim.py", configs["claude_desktop"])
        self.assertTrue(service.masked_token().endswith("...") or len(service.masked_token()) < len("tok123") + 4)
