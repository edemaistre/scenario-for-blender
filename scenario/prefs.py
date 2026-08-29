# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Add-on preferences: credentials, output folder, composer, MCP."""
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty

PORTAL_KEYS_URL = "https://app.scenario.com/team"


class ScenarioPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    api_key: StringProperty(name="API Key", subtype='PASSWORD', description="Scenario API key (Project or Team scoped). Created in the Scenario portal")
    api_secret: StringProperty(name="API Secret", subtype='PASSWORD', description="Shown once when the key is created")
    output_dir: StringProperty(name="Output Folder", subtype='DIR_PATH', default="~/Downloads/Scenario", description="Generated files are saved here, one subfolder per kind")
    composer_enabled: BoolProperty(name="Floating composer in the viewport", default=True, update=lambda self, context: __import__(__package__ + ".blender.composer", fromlist=["set_enabled"]).set_enabled(self.composer_enabled))
    composer_offset_x: FloatProperty(name="Composer offset X", default=0.0, description="Where the floating composer was dragged to, from its default bottom-centre spot (pixels)")
    composer_offset_y: FloatProperty(name="Composer offset Y", default=0.0, description="Where the floating composer was dragged to, from its default bottom-centre spot (pixels)")
    composer_width: IntProperty(name="Composer width", default=0, min=0, description="Width of the expanded composer in pixels (0 = default)")
    mcp_port: IntProperty(name="MCP Port", default=9876, min=1024, max=65535)
    mcp_allow_python: BoolProperty(name="Allow connected agents to run Python", default=False, description="Off by default: connected agents keep the read and scene tools; turn on only to let them run arbitrary bpy code in this Blender")
    log_level: EnumProperty(name="Log Level", items=[('INFO', "Info", ""), ('DEBUG', "Debug", "")], default='INFO', update=lambda self, context: __import__(__package__ + ".blender.registry", fromlist=["apply_log_level"]).apply_log_level(self.log_level))

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
        row = layout.row(align=True)
        row.enabled = self.composer_enabled
        row.label(text="Composer placement", icon='ARROW_LEFTRIGHT')
        row.prop(self, "composer_offset_x", text="X")
        row.prop(self, "composer_offset_y", text="Y")
        row.prop(self, "composer_width", text="Width")
        row.operator("scenario.composer_reset_layout", text="", icon='LOOP_BACK')
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
