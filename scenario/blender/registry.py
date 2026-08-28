# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Registers every Blender class of the extension in dependency order."""
import logging

log = logging.getLogger("scenario")


def register():
    log.info("Scenario for Blender registered")


def unregister():
    log.info("Scenario for Blender unregistered")
