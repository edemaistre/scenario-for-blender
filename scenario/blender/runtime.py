# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Process-wide singletons shared by panels, operators and the pump (main thread only)."""
import logging
import os
import pathlib

import bpy

from .. import prefs as prefs_module
from ..core import config
from ..core.api.catalog import Catalog
from ..core.api.client import ScenarioClient
from ..core.api.errors import ScenarioError
from ..core.jobs.manager import JobManager
from ..core.jobs.records import JobRegistry

log = logging.getLogger("scenario")
PACKAGE = __package__.rsplit(".", 1)[0]  # the extension package, e.g. bl_ext.user_default.scenario


class RuntimeState:
    def __init__(self):
        self.manager = None
        self.catalog = None
        self.records = {}          # model_id -> ModelRecord (detailed)
        self.lane_models = {}      # lane -> list[ModelRecord]
        self.catalog_loaded = False
        self.catalog_loading = False
        self.account_label = ""
        self.last_message = ""
        self.enum_cache = {}       # key -> list of (id, name, desc) tuples kept alive for EnumProperty
        self.previews = None       # bpy.utils.previews collection, created lazily
        self.jobs_view = []        # JobRecord list shown in the panel (active + recent)
        self.history = []
        self.history_token = None
        self.mcp = None
        self.mcp_token = ""
        self.mcp_error = ""
        self.cli_handle = None
        self.composer = None
        self.composer_modal_running = False

    SESSION_ATTRS = ("mcp", "mcp_token", "mcp_error", "cli_handle", "composer", "composer_modal_running", "previews")

    def reset(self):
        """Forget catalog, jobs and history; keep process-level services (MCP server, composer, previews)."""
        kept = {name: getattr(self, name) for name in self.SESSION_ATTRS}
        self.__init__()
        for name, value in kept.items():
            setattr(self, name, value)


state = RuntimeState()


def prefs():
    return prefs_module.get_prefs()


def online():
    return bool(getattr(bpy.app, "online_access", True))


def paths():
    state_dir = pathlib.Path(bpy.utils.extension_path_user(PACKAGE, path="state", create=True))
    cache_dir = pathlib.Path(bpy.utils.extension_path_user(PACKAGE, path="cache", create=True))
    p = prefs()
    raw_out = p.output_dir if p and p.output_dir else "~/Downloads/Scenario"
    output_dir = pathlib.Path(os.path.expanduser(bpy.path.abspath(raw_out)))
    return config.Paths(state_dir=state_dir, cache_dir=cache_dir, output_dir=output_dir)


def credentials():
    p = prefs()
    return config.resolve_credentials(p.api_key if p else "", p.api_secret if p else "")


def make_client():
    creds = credentials()
    if not creds.valid:
        raise ScenarioError(0, "Add your Scenario API key and secret in Preferences")
    from .. import __version__

    return ScenarioClient(creds.key, creds.secret, user_agent=f"ScenarioBlender/{__version__}")


def ensure_manager():
    if state.manager is None:
        p = paths()
        registry = JobRegistry(p.registry_file).load()
        state.manager = JobManager(make_client, registry, p)
        state.manager.resume()
    return state.manager


def ensure_catalog():
    if state.catalog is None:
        state.catalog = Catalog(make_client(), paths().cache_dir)
    return state.catalog


def enum_items(key):
    return state.enum_cache.get(key) or [("NONE", "Loading...", "Model list not loaded yet")]


def set_enum_items(key, items):
    state.enum_cache[key] = [tuple(item) for item in items] or [("NONE", "None available", "")]


def set_message(text):
    state.last_message = text
    log.info(text)


def previews():
    import bpy.utils.previews

    if state.previews is None:
        state.previews = bpy.utils.previews.new()
    return state.previews


def shutdown():
    if state.manager:
        state.manager.shutdown()
    if state.mcp is not None:
        state.mcp.stop()
    if state.previews is not None:
        import bpy.utils.previews

        bpy.utils.previews.remove(state.previews)
    state.reset()
