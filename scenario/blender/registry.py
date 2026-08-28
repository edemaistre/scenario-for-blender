# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Registers every Blender class of the extension in dependency order."""
import logging

import bpy

from .. import prefs

log = logging.getLogger("scenario")


_log_handler = None


def _modules():
    from . import props, shot_planner, operators, prompt_tools, model_picker, panels, popover, composer  # noqa: F401

    modules = [props, shot_planner, operators, prompt_tools, model_picker, panels, popover, composer]
    try:
        from . import icons  # Scenario's modality icons; optional so a build without the PNGs still loads

        modules.insert(0, icons)
    except ImportError:
        pass
    return modules


def _configure_logging():
    global _log_handler
    if _log_handler is not None:
        return
    _log_handler = logging.StreamHandler()
    _log_handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    log.addHandler(_log_handler)
    log.setLevel(logging.INFO)
    log.propagate = False


def register():
    _configure_logging()
    for cls in prefs.CLASSES:
        bpy.utils.register_class(cls)
    for module in _modules():
        module.register()
    from . import mcp_service, pump

    pump.start()
    if not bpy.app.background:
        mcp_service.start()
    try:
        runtime_module = __import__(__package__ + ".runtime", fromlist=["state"])
        runtime_module.state.cli_handle = bpy.utils.register_cli_command("scenario-mcp", mcp_service.cli)
    except (AttributeError, ValueError, RuntimeError) as err:
        log.debug("cli command not registered: %s", err)
    log.info("Scenario for Blender registered")


def unregister():
    from . import mcp_service, pump, runtime

    handle = getattr(runtime.state, "cli_handle", None)
    if handle is not None:
        try:
            bpy.utils.unregister_cli_command(handle)
        except (AttributeError, ValueError, RuntimeError, TypeError):
            pass
        runtime.state.cli_handle = None
    mcp_service.stop()
    pump.stop()
    for module in reversed(_modules()):
        module.unregister()
    for cls in reversed(prefs.CLASSES):
        bpy.utils.unregister_class(cls)
    runtime.shutdown()
    log.info("Scenario for Blender unregistered")
    global _log_handler
    if _log_handler is not None:
        log.removeHandler(_log_handler)
        _log_handler = None
