# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build Principled BSDF materials from a MaterialPlan and assign them to meshes."""
import logging

import bpy

from . import apply_image, runtime
from ..core.scene import material_plan as mp

log = logging.getLogger("scenario.material")


def _tree(mat):
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    if mat.node_tree is None:
        mat.use_nodes = True
    return mat.node_tree


def _image_node(tree, path, color_space, x, y):
    node = tree.nodes.new("ShaderNodeTexImage")
    node.image = apply_image.load_image(path)
    node.image.colorspace_settings.name = color_space
    node.location = (x, y)
    node.interpolation = 'Linear'
    return node


def build_material(plan):
    mat = bpy.data.materials.new(plan.name)
    tree = _tree(mat)
    nodes, links = tree.nodes, tree.links
    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None) or nodes.new("ShaderNodeBsdfPrincipled")
    output = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None) or nodes.new("ShaderNodeOutputMaterial")
    if not any(l.to_node == output and l.to_socket.name == "Surface" for l in links):
        links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    coords = nodes.new("ShaderNodeTexCoord")
    coords.location = (bsdf.location.x - 1400, bsdf.location.y)
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (bsdf.location.x - 1200, bsdf.location.y)
    links.new(coords.outputs["UV"], mapping.inputs["Vector"])
    x = bsdf.location.x - 800
    state = {"y": bsdf.location.y + 300}

    def add_tex(role):
        node = _image_node(tree, plan.textures[role], plan.color_space(role), x, state["y"])
        node.label = role.title()
        links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        state["y"] -= 300
        return node

    if plan.base_color_path:
        role = mp.ALBEDO if mp.ALBEDO in plan.textures else mp.BASE
        links.new(add_tex(role).outputs["Color"], bsdf.inputs["Base Color"])
    if mp.ROUGHNESS in plan.textures:
        links.new(add_tex(mp.ROUGHNESS).outputs["Color"], bsdf.inputs["Roughness"])
    elif mp.SMOOTHNESS in plan.textures:
        smooth = add_tex(mp.SMOOTHNESS)
        invert = nodes.new("ShaderNodeInvert")
        invert.label = "Smoothness to Roughness"
        invert.location = (x + 300, smooth.location.y)
        links.new(smooth.outputs["Color"], invert.inputs["Color"])
        links.new(invert.outputs["Color"], bsdf.inputs["Roughness"])
    if mp.METALLIC in plan.textures:
        links.new(add_tex(mp.METALLIC).outputs["Color"], bsdf.inputs["Metallic"])
    if mp.NORMAL in plan.textures:
        normal_tex = add_tex(mp.NORMAL)
        normal_map = nodes.new("ShaderNodeNormalMap")
        normal_map.location = (x + 300, normal_tex.location.y)
        links.new(normal_tex.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])
    if mp.HEIGHT in plan.textures:
        height_tex = add_tex(mp.HEIGHT)
        disp = nodes.new("ShaderNodeDisplacement")
        disp.location = (x + 300, height_tex.location.y)
        disp.inputs["Scale"].default_value = 0.05
        links.new(height_tex.outputs["Color"], disp.inputs["Height"])
        links.new(disp.outputs["Displacement"], output.inputs["Displacement"])
        try:
            mat.displacement_method = 'BUMP'
        except (AttributeError, TypeError):
            pass
    return mat


def set_tiling(mat, scale):
    mapping = next((n for n in mat.node_tree.nodes if n.type == 'MAPPING'), None)
    if mapping is not None:
        mapping.inputs["Scale"].default_value = (scale, scale, scale)


def assign_to_objects(mat, objects):
    for obj in objects:
        if obj is None or obj.type != 'MESH':
            continue
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
        obj.active_material_index = 0


def on_material_result(rec):
    prompt = (rec.meta.get("prompt") or rec.model_id).strip()
    plan = mp.plan_material(f"Scenario {prompt[:40]}", mp.roles_from_record(rec))
    mat = build_material(plan)
    names = rec.meta.get("target_objects") or []
    targets = [bpy.data.objects.get(n) for n in names if bpy.data.objects.get(n) is not None]
    if not targets:
        targets = [o for o in bpy.context.selected_objects if o.type == 'MESH']
    assign_to_objects(mat, targets)
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D' and area.spaces.active.shading.type == 'SOLID':
                area.spaces.active.shading.type = 'MATERIAL'
    runtime.set_message(f"Material '{mat.name}' ready" + (f", applied to {len(targets)} object(s)" if targets else ""))
    return mat
