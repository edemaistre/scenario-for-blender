# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Gaussian splats (.spz from Marble and HY World, .ply point clouds) into Blender as coloured point clouds.

Blender has no Gaussian splat renderer. The splat centres become a mesh of vertices with a colour attribute and a
Geometry Nodes modifier turns them into points sized from the splat scales, so the world reads in the viewport and
renders in EEVEE / Cycles as a dense coloured cloud."""
import logging
import statistics

import bpy

from ..core.scene import spz

log = logging.getLogger("scenario.splat")
DEFAULT_MAX_POINTS = 1_000_000


def _ensure_material():
    mat = bpy.data.materials.get("Scenario Splat")
    if mat is not None:
        return mat
    mat = bpy.data.materials.new("Scenario Splat")
    if hasattr(mat, "use_nodes"):
        try:
            mat.use_nodes = True
        except AttributeError:
            pass
    tree = mat.node_tree
    if tree is None:
        return mat
    nodes, links = tree.nodes, tree.links
    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    attr = nodes.new("ShaderNodeAttribute")
    attr.attribute_name = "color"
    attr.location = (-400, 0)
    if bsdf is not None:
        links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
        if "Emission Color" in bsdf.inputs:
            links.new(attr.outputs["Color"], bsdf.inputs["Emission Color"])
            bsdf.inputs["Emission Strength"].default_value = 0.6
        bsdf.inputs["Roughness"].default_value = 1.0
    return mat


def _points_modifier(obj, radius):
    """Mesh to Points with a fixed radius, plus the splat material, through a small Geometry Nodes tree."""
    tree = bpy.data.node_groups.new("Scenario Splat Points", "GeometryNodeTree")
    tree.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    tree.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    nodes, links = tree.nodes, tree.links
    group_in = nodes.new("NodeGroupInput")
    group_out = nodes.new("NodeGroupOutput")
    to_points = nodes.new("GeometryNodeMeshToPoints")
    to_points.inputs["Radius"].default_value = float(radius)
    set_mat = nodes.new("GeometryNodeSetMaterial")
    set_mat.inputs["Material"].default_value = _ensure_material()
    group_in.location, to_points.location, set_mat.location, group_out.location = (-400, 0), (-150, 0), (100, 0), (350, 0)
    links.new(group_in.outputs[0], to_points.inputs["Mesh"])
    links.new(to_points.outputs["Points"], set_mat.inputs["Geometry"])
    links.new(set_mat.outputs["Geometry"], group_out.inputs[0])
    mod = obj.modifiers.new("Scenario Splat", 'NODES')
    mod.node_group = tree
    return mod


def import_spz(context, path, max_points=DEFAULT_MAX_POINTS, name=None, collection=None):
    """Read an .spz file and add a point-cloud object at the origin (Y-up converted to Z-up). Returns the object."""
    data = spz.read_spz(path, max_points=max_points)
    positions = [spz.y_up_to_z_up(p) for p in data["positions"]]
    mesh = bpy.data.meshes.new(name or "Scenario Splat")
    mesh.from_pydata(positions, [], [])
    color_attr = mesh.color_attributes.new("color", 'FLOAT_COLOR', 'POINT')
    flat = []
    for (r, g, b), a in zip(data["colors"], data["alphas"]):
        flat.extend((r, g, b, a))
    color_attr.data.foreach_set("color", flat)
    mesh.update()
    obj = bpy.data.objects.new(mesh.name, mesh)
    target = collection or context.scene.collection
    target.objects.link(obj)
    radius = statistics.median(data["scales"]) if data["scales"] else 0.02
    radius = max(0.005, min(0.25, radius * (data["step"] ** 0.5)))  # subsampled clouds get larger points to stay dense
    try:
        _points_modifier(obj, radius)
    except (RuntimeError, KeyError, AttributeError) as err:  # older Blender without these nodes: keep the vertex cloud
        log.warning("splat points modifier not available: %s", err)
    obj["scenario_splat_points"] = data["count"]
    obj["scenario_splat_kept"] = data["kept"]
    log.info("splat %s: %d of %d points, radius %.3f", path, data["kept"], data["count"], radius)
    return obj


def import_ply(context, path):
    """PLY through Blender's importer (Gaussian splat PLYs come in as vertices with colour attributes)."""
    before = set(bpy.data.objects.keys())
    bpy.ops.wm.ply_import(filepath=str(path))
    return [o for o in bpy.data.objects if o.name not in before]
