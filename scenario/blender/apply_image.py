# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bring image results into Blender: datablocks, Image Editor window, textures, planes."""
import logging
import pathlib

import bpy

from . import runtime

log = logging.getLogger("scenario.image")


def _ensure_nodes(mat):
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    if mat.node_tree is None:  # very old files
        mat.use_nodes = True
    return mat.node_tree


def load_image(path, pack=True):
    path = str(pathlib.Path(path))
    image = bpy.data.images.load(path, check_existing=True)
    if pack and image.packed_file is None:
        try:
            image.pack()
        except RuntimeError as err:
            log.warning("could not pack %s: %s", path, err)
    return image


def show_in_image_editor(image):
    """Prefer an existing Image Editor; otherwise open a new window showing the image."""
    wm = bpy.context.window_manager
    for window in wm.windows:
        for area in window.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.spaces.active.image = image
                _fit_view(window, area)
                area.tag_redraw()
                return True
    if not wm.windows:
        return False
    window = wm.windows[0]
    try:
        with bpy.context.temp_override(window=window, screen=window.screen, area=window.screen.areas[0]):
            bpy.ops.wm.window_new()
        new_window = wm.windows[-1]
        area = new_window.screen.areas[0]
        area.type = 'IMAGE_EDITOR'
        area.spaces.active.image = image
        _fit_view(new_window, area)
        return True
    except (RuntimeError, IndexError) as err:
        log.warning("could not open an image window: %s", err)
        return False


def _fit_view(window, area):
    """Show the whole image (the editor keeps the previous zoom, which crops a portrait image to a square)."""
    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
    if region is None:
        return

    def _fit():
        try:
            with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region):
                bpy.ops.image.view_all(fit_view=True)
        except (RuntimeError, TypeError) as err:
            log.debug("view_all failed: %s", err)
        return None

    _fit()
    if not bpy.app.background:
        bpy.app.timers.register(_fit, first_interval=0.05)  # a fresh window has no size yet on its first draw


def material_with_image(name, image):
    mat = bpy.data.materials.new(name)
    tree = _ensure_nodes(mat)
    nodes, links = tree.nodes, tree.links
    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None) or nodes.new("ShaderNodeBsdfPrincipled")
    output = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None) or nodes.new("ShaderNodeOutputMaterial")
    if not any(l.to_node is output for l in links):
        links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    tex = nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.location = (bsdf.location.x - 400, bsdf.location.y)
    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def apply_as_texture(obj, image):
    mat = material_with_image(f"Scenario {image.name}", image)
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)
    obj.active_material_index = 0
    _material_preview()
    return mat


def add_as_plane(context, image):
    scene = context.scene
    width, height = image.size[0] or 1, image.size[1] or 1
    aspect = width / height
    bpy.ops.mesh.primitive_plane_add(location=scene.cursor.location)
    plane = context.active_object
    plane.name = f"Scenario {image.name}"
    plane.scale = (aspect if aspect >= 1 else 1.0, 1.0 if aspect >= 1 else 1.0 / aspect, 1.0)
    region = _first_region_3d(context)
    if region is not None:
        plane.rotation_euler = region.view_rotation.to_euler()
    plane.data.materials.append(material_with_image(f"Scenario {image.name}", image))
    _material_preview()
    return plane


def on_image_result(rec):
    names = []
    for index, path in enumerate(rec.files):
        if not pathlib.Path(path).exists():
            continue
        image = load_image(path)
        names.append(image.name)
        if index == 0:
            show_in_image_editor(image)
    runtime.set_message(f"{len(names)} image(s) ready from {rec.meta.get('model_name') or rec.model_id}")
    return names


def _first_region_3d(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                return area.spaces.active.region_3d
    return None


def _material_preview():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                shading = area.spaces.active.shading
                if shading.type == 'SOLID':
                    shading.type = 'MATERIAL'
