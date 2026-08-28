# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Registers every Blender class of the extension in dependency order."""
import logging

import bpy

from .. import prefs

log = logging.getLogger("scenario")


def _modules():
    from . import props, operators, panels, popover  # noqa: F401

    return [props, operators, panels, popover]


def register():
    logging.basicConfig(level=logging.INFO)
    for cls in prefs.CLASSES:
        bpy.utils.register_class(cls)
    try:
        modules = _modules()
    except ImportError:
        modules = []
    for module in modules:
        module.register()
    from . import mcp_service, pump

    pump.start()
    if not bpy.app.background:
        mcp_service.start()
    try:
        bpy.utils.register_cli_command("scenario-mcp", mcp_service.cli)
    except (AttributeError, ValueError, RuntimeError) as err:
        log.debug("cli command not registered: %s", err)
    log.info("Scenario for Blender registered")


def unregister():
    from . import mcp_service, pump, runtime

    try:
        bpy.utils.unregister_cli_command("scenario-mcp")
    except (AttributeError, ValueError, RuntimeError, KeyError):
        pass
    mcp_service.stop()
    pump.stop()
    try:
        modules = _modules()
    except ImportError:
        modules = []
    for module in reversed(modules):
        module.unregister()
    for cls in reversed(prefs.CLASSES):
        bpy.utils.unregister_class(cls)
    runtime.shutdown()
    log.info("Scenario for Blender unregistered")
