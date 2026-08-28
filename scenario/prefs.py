# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Add-on preferences: credentials, output folder, composer, MCP."""
import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty, StringProperty

PORTAL_KEYS_URL = "https://app.scenario.com/team"


class ScenarioPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    api_key: StringProperty(name="API Key", subtype='PASSWORD', description="Scenario API key (Project or Team scoped). Created in the Scenario portal")
    api_secret: StringProperty(name="API Secret", subtype='PASSWORD', description="Shown once when the key is created")
    output_dir: StringProperty(name="Output Folder", subtype='DIR_PATH', default="~/Downloads/Scenario", description="Generated files are saved here, one subfolder per kind")
    composer_enabled: BoolProperty(name="Floating composer in the viewport", default=True)
    mcp_port: IntProperty(name="MCP Port", default=9876, min=1024, max=65535)
    mcp_allow_python: BoolProperty(name="Allow connected agents to run Python", default=True, description="Agents connected through the local MCP server may execute bpy code in this Blender")
    log_level: EnumProperty(name="Log Level", items=[('INFO', "Info", ""), ('DEBUG', "Debug", "")], default='INFO')

    def draw(self, context):
        from .blender import runtime

        layout = self.layout
        box = layout.box()
        box.label(text="Account", icon='USER')
        box.prop(self, "api_key")
        box.prop(self, "api_secret")
        row = box.row(align=True)
        row.operator("wm.url_open", text="Create a key in the portal", icon='URL').url = PORTAL_KEYS_URL
        row.operator("scenario.test_connection", text="Test connection", icon='CHECKMARK')
        if runtime.state.account_label:
            box.label(text=runtime.state.account_label, icon='INFO')
        if not runtime.online():
            box.label(text="Allow Online Access is off in Blender's System preferences", icon='ERROR')
        layout.prop(self, "output_dir")
        layout.prop(self, "composer_enabled")
        box = layout.box()
        box.label(text="MCP server (agents)", icon='PLUGIN')
        box.prop(self, "mcp_port")
        box.prop(self, "mcp_allow_python")
        layout.prop(self, "log_level")


def get_prefs(context=None):
    context = context or bpy.context
    entry = context.preferences.addons.get(__package__)
    return entry.preferences if entry else None


CLASSES = (ScenarioPreferences,)
