# Scenario for Blender P1 Implementation Plan (Materials, 3D, Generations)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On top of P0, add the Materials lane (Patina PBR sets applied as Principled BSDF materials on the selected meshes), the 3D lane (text, image and multi-view to 3D imported at the 3D cursor) and the Generations history (cloud job list with thumbnails and per-kind actions).

**Architecture:** Pure planning logic stays in `scenario/core` (material graph plan from typed assets, 3D import placement math, history paging) and is unit-tested; Blender builders in `scenario/blender` consume those plans and are tested headless with the Patina fixtures and a generated GLB. Results flow through the same job manager and `handlers.RESULT_HANDLERS` registry as images.

**Tech Stack:** same as P0.

**Spec:** `docs/superpowers/specs/2026-08-28-scenario-for-blender-design.md` (sections 3.1 `core/scene`, 4 lanes 3D and Materials, 4 Generations)

## Global Constraints

Same as the P0 plan (`docs/superpowers/plans/2026-08-28-p0-skeleton-image-lane.md`), plus:
- Patina map roles come from `asset.metadata.type`: `texture-albedo`, `texture-normal`, `texture-smoothness`, `texture-metallic`, `texture-height`, base texture `inference-txt2img-texture`. Roughness = 1 - smoothness (Invert node). Non-color data for every map except albedo and base.
- 3D results are imported into a collection named `Scenario`, placed so the bounding box bottom centre sits on the 3D cursor, selected and made active.
- Work on branch `p1-materials-3d-history`; merge `--no-ff` into `main` at the end.

---

### Task 12: Material plan from typed assets (pure Python)

**Files:**
- Create: `scenario/core/scene/__init__.py`, `scenario/core/scene/material_plan.py`
- Test: `tests/unit/test_material_plan.py`

**Interfaces:**
- Produces: `MapRole` constants `ALBEDO, NORMAL, SMOOTHNESS, ROUGHNESS, METALLIC, HEIGHT, BASE`; `ROLE_BY_TYPE: dict[str, str]`; `MaterialPlan(name, textures: dict[role, path], invert_smoothness: bool, has_displacement: bool)` with `.color_space(role) -> "sRGB" | "Non-Color"`; `plan_material(name, typed_files: list[tuple[str, str]]) -> MaterialPlan` where `typed_files` pairs `(metadata_type, file_path)`; `roles_from_record(rec) -> list[tuple[str, str]]` mapping a `JobRecord` (files + asset_types + asset_ids order) to typed files.

- [ ] **Step 1: Failing tests**

`tests/unit/test_material_plan.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json

from conftest import FIXTURES
from scenario.core.jobs.records import JobRecord
from scenario.core.scene import material_plan as mp


def typed_fixture_files():
    manifest = json.loads((FIXTURES / "patina-copper-512" / "manifest.json").read_text())
    return [(a["type"], str(FIXTURES / "patina-copper-512" / a["file"])) for a in manifest["assets"]]


def test_plan_maps_every_patina_type():
    plan = mp.plan_material("Copper", typed_fixture_files())
    assert plan.name == "Copper"
    assert set(plan.textures) == {mp.ALBEDO, mp.NORMAL, mp.SMOOTHNESS, mp.METALLIC, mp.HEIGHT, mp.BASE}
    assert plan.textures[mp.ALBEDO].endswith("albedo.png")
    assert plan.invert_smoothness and plan.has_displacement
    assert plan.color_space(mp.ALBEDO) == "sRGB" and plan.color_space(mp.BASE) == "sRGB"
    for role in (mp.NORMAL, mp.SMOOTHNESS, mp.METALLIC, mp.HEIGHT):
        assert plan.color_space(role) == "Non-Color"


def test_plan_without_maps_uses_base_as_color():
    plan = mp.plan_material("Flat", [("inference-txt2img-texture", "/x/base.png")])
    assert plan.base_color_path == "/x/base.png"
    assert not plan.has_displacement and not plan.invert_smoothness


def test_plan_accepts_roughness_typed_asset_without_inversion():
    plan = mp.plan_material("R", [("texture-albedo", "/a.png"), ("texture-roughness", "/r.png")])
    assert plan.textures[mp.ROUGHNESS] == "/r.png" and not plan.invert_smoothness


def test_roles_from_record_pairs_files_with_asset_types():
    rec = JobRecord.new(lane="material", kind="material", model_id="model_patina-material", body={})
    rec.asset_ids = ["a1", "a2"]
    rec.asset_types = {"a1": "texture-albedo", "a2": "texture-normal"}
    rec.files = ["/out/1.png", "/out/2.png"]
    assert mp.roles_from_record(rec) == [("texture-albedo", "/out/1.png"), ("texture-normal", "/out/2.png")]
```

- [ ] **Step 2: Run to see it fail, then implement**

`scenario/core/scene/__init__.py`: SPDX header only.

`scenario/core/scene/material_plan.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Decide how a set of typed texture files becomes a PBR material. No bpy."""
from dataclasses import dataclass, field

ALBEDO, NORMAL, SMOOTHNESS, ROUGHNESS, METALLIC, HEIGHT, BASE = "albedo", "normal", "smoothness", "roughness", "metallic", "height", "base"

ROLE_BY_TYPE = {
    "texture-albedo": ALBEDO, "texture-basecolor": ALBEDO, "texture-normal": NORMAL, "texture-smoothness": SMOOTHNESS,
    "texture-roughness": ROUGHNESS, "texture-metallic": METALLIC, "texture-metalness": METALLIC, "texture-height": HEIGHT,
    "texture-displacement": HEIGHT, "inference-txt2img-texture": BASE, "inference-img2img-texture": BASE,
}
COLOR_ROLES = {ALBEDO, BASE}


@dataclass
class MaterialPlan:
    name: str
    textures: dict = field(default_factory=dict)

    @property
    def invert_smoothness(self):
        return SMOOTHNESS in self.textures and ROUGHNESS not in self.textures

    @property
    def has_displacement(self):
        return HEIGHT in self.textures

    @property
    def base_color_path(self):
        return self.textures.get(ALBEDO) or self.textures.get(BASE)

    @staticmethod
    def color_space(role):
        return "sRGB" if role in COLOR_ROLES else "Non-Color"


def plan_material(name, typed_files):
    plan = MaterialPlan(name=name)
    for metadata_type, path in typed_files:
        role = ROLE_BY_TYPE.get(metadata_type)
        if role and role not in plan.textures:
            plan.textures[role] = path
    return plan


def roles_from_record(rec):
    pairs = []
    for asset_id, path in zip(rec.asset_ids, rec.files):
        pairs.append((rec.asset_types.get(asset_id, ""), path))
    return pairs
```

Run: `python3 -m pytest tests/unit/test_material_plan.py -v` Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git checkout -b p1-materials-3d-history && git add -A && git commit -m "feat(core): material plan from typed Patina assets"
```

---

### Task 13: Blender material builder and selection assignment

**Files:**
- Create: `scenario/blender/apply_material.py`
- Modify: `scenario/blender/handlers.py` (register `"material"` result handler)
- Test: `tests/blender/test_apply_material.py`

**Interfaces:**
- Produces: `apply_material.build_material(plan) -> bpy.types.Material`; `apply_material.assign_to_objects(mat, objects)`; `apply_material.on_material_result(rec) -> Material` (assigns to the meshes selected when the job was submitted, recorded in `rec.meta["target_objects"]`, falling back to the current selection, else just creates the material); `apply_material.set_tiling(mat, scale)`.

- [ ] **Step 1: Failing headless test**

`tests/blender/test_apply_material.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


def typed_files():
    manifest = json.loads((FIXTURES / "patina-copper-512" / "manifest.json").read_text())
    return [(a["type"], str(FIXTURES / "patina-copper-512" / a["file"])) for a in manifest["assets"]]


def node_of(mat, ntype):
    return [n for n in mat.node_tree.nodes if n.type == ntype]


def link_into(mat, node, socket_name):
    return next((l for l in mat.node_tree.links if l.to_node is node and l.to_socket.name == socket_name), None)


class ApplyMaterialTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.mp = submodule("core.scene.material_plan")
        self.apply_material = submodule("blender.apply_material")

    def test_build_material_wires_pbr_graph(self):
        mat = self.apply_material.build_material(self.mp.plan_material("Copper", typed_files()))
        bsdf = node_of(mat, 'BSDF_PRINCIPLED')[0]
        images = node_of(mat, 'TEX_IMAGE')
        self.assertEqual(len(images), 5)  # albedo, normal, smoothness, metallic, height (base unused when albedo exists)
        base = link_into(mat, bsdf, "Base Color")
        self.assertEqual(base.from_node.image.colorspace_settings.name, "sRGB")
        rough = link_into(mat, bsdf, "Roughness")
        self.assertEqual(rough.from_node.type, 'INVERT')
        smooth_tex = link_into(mat, rough.from_node, "Color").from_node
        self.assertEqual(smooth_tex.image.colorspace_settings.name, "Non-Color")
        self.assertEqual(link_into(mat, bsdf, "Metallic").from_node.type, 'TEX_IMAGE')
        self.assertEqual(link_into(mat, bsdf, "Normal").from_node.type, 'NORMAL_MAP')
        output = node_of(mat, 'OUTPUT_MATERIAL')[0]
        self.assertEqual(link_into(mat, output, "Displacement").from_node.type, 'DISPLACEMENT')
        mapping = node_of(mat, 'MAPPING')
        self.assertEqual(len(mapping), 1)
        for tex in images:
            self.assertIsNotNone(link_into(mat, tex, "Vector"))

    def test_assign_to_selected_meshes_and_tiling(self):
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.active_object
        bpy.ops.mesh.primitive_uv_sphere_add()
        sphere = bpy.context.active_object
        mat = self.apply_material.build_material(self.mp.plan_material("Copper", typed_files()))
        self.apply_material.assign_to_objects(mat, [cube, sphere])
        self.assertIs(cube.active_material, mat)
        self.assertIs(sphere.active_material, mat)
        self.apply_material.set_tiling(mat, 3.0)
        mapping = node_of(mat, 'MAPPING')[0]
        self.assertEqual(tuple(mapping.inputs["Scale"].default_value), (3.0, 3.0, 3.0))

    def test_on_material_result_uses_recorded_targets(self):
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.active_object
        records = submodule("core.jobs.records")
        rec = records.JobRecord.new(lane="material", kind="material", model_id="model_patina-material", body={"prompt": "copper"})
        manifest = json.loads((FIXTURES / "patina-copper-512" / "manifest.json").read_text())
        rec.asset_ids = [a["assetId"] for a in manifest["assets"]]
        rec.asset_types = {a["assetId"]: a["type"] for a in manifest["assets"]}
        rec.files = [str(FIXTURES / "patina-copper-512" / a["file"]) for a in manifest["assets"]]
        rec.meta["target_objects"] = [cube.name]
        rec.meta["prompt"] = "weathered copper"
        mat = self.apply_material.on_material_result(rec)
        self.assertIs(cube.active_material, mat)
        self.assertTrue(mat.name.startswith("Scenario weathered copper"))
```

- [ ] **Step 2: Run to see it fail, then implement**

`scenario/blender/apply_material.py`:
```python
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
    if not any(l.to_node is output and l.to_socket.name == "Surface" for l in links):
        links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    coords = nodes.new("ShaderNodeTexCoord")
    coords.location = (bsdf.location.x - 1400, bsdf.location.y)
    mapping = nodes.new("ShaderNodeMapping")
    mapping.location = (bsdf.location.x - 1200, bsdf.location.y)
    links.new(coords.outputs["UV"], mapping.inputs["Vector"])
    x = bsdf.location.x - 800
    y = bsdf.location.y + 300
    tex_nodes = []

    def add_tex(role):
        nonlocal y
        node = _image_node(tree, plan.textures[role], plan.color_space(role), x, y)
        node.label = role.title()
        links.new(mapping.outputs["Vector"], node.inputs["Vector"])
        tex_nodes.append(node)
        y -= 300
        return node

    color_path = plan.base_color_path
    if color_path:
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
```

In `scenario/blender/handlers.py`: `from . import apply_material` and `RESULT_HANDLERS = {"image": apply_image.on_image_result, "material": apply_material.on_material_result}`.

Run: `./tools/install_dev.sh && make test-blender` Expected: OK (20 tests).

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat(blender): Patina material builder and assignment"
```

---

### Task 14: Materials lane UI

**Files:**
- Modify: `scenario/blender/generation.py` (record `target_objects` in meta for the material lane; default maps), `scenario/blender/panels.py` (Materials lane header text and the "Apply to: N selected meshes" hint), `scenario/blender/operators.py` (add `scenario.retile_material`)
- Test: `tests/blender/test_material_lane.py`

**Interfaces:**
- Produces: `generation.submit_generation` stores `meta["target_objects"]` = names of selected mesh objects for lane `material`; operator `scenario.retile_material(material_name, scale)`; panel shows "Applies to: <n> selected mesh(es)" or "Select a mesh to apply the material" in the Materials lane.

- [ ] **Step 1: Failing headless test**

`tests/blender/test_material_lane.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

import bpy

from helpers import FIXTURES, reset_scene, submodule


class MaterialLaneTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.generation = submodule("blender.generation")
        self.runtime = submodule("blender.runtime")
        catalog = submodule("core.api.catalog")
        handlers = submodule("blender.handlers")
        self.runtime.state.reset()
        data = json.loads((FIXTURES / "models" / "model_patina-material.json").read_text())["model"]
        rec = catalog.ModelRecord.from_api(data)
        handlers.dispatch(("catalog", {"privacy": "public", "records": [rec], "detailed": [rec]}))

    def test_material_request_records_selected_meshes(self):
        bpy.ops.mesh.primitive_cube_add()
        cube = bpy.context.active_object
        lane = bpy.context.scene.scenario.lane_state("material")
        lane.prompt = "mossy stone"
        request = self.generation.build_request(bpy.context.scene, "material")
        self.assertEqual(request.model_id, "model_patina-material")
        self.assertEqual(request.body["maps"], ["basecolor", "normal", "roughness", "metalness", "height"])
        meta = self.generation.request_meta(bpy.context, "material")
        self.assertEqual(meta["target_objects"], [cube.name])

    def test_retile_operator_changes_mapping_scale(self):
        mp = submodule("core.scene.material_plan")
        apply_material = submodule("blender.apply_material")
        manifest = json.loads((FIXTURES / "patina-copper-512" / "manifest.json").read_text())
        files = [(a["type"], str(FIXTURES / "patina-copper-512" / a["file"])) for a in manifest["assets"]]
        mat = apply_material.build_material(mp.plan_material("T", files))
        bpy.ops.scenario.retile_material(material_name=mat.name, scale=2.5)
        mapping = next(n for n in mat.node_tree.nodes if n.type == 'MAPPING')
        self.assertEqual(tuple(mapping.inputs["Scale"].default_value), (2.5, 2.5, 2.5))
```

- [ ] **Step 2: Implement**

In `scenario/blender/generation.py` add:
```python
def request_meta(context, lane):
    lane_state = context.scene.scenario.lane_state(lane)
    record = runtime.state.records.get(lane_state.model_id)
    meta = {"prompt": lane_state.prompt, "model_name": record.name if record else lane_state.model_id}
    if lane == "material":
        meta["target_objects"] = [o.name for o in context.selected_objects if o.type == 'MESH']
    return meta
```
and in `submit_generation` replace the inline `meta={...}` with `meta=request_meta(context, lane)`.

In `scenario/blender/operators.py` add:
```python
class SCENARIO_OT_retile_material(bpy.types.Operator):
    bl_idname = "scenario.retile_material"
    bl_label = "Set material tiling"
    bl_description = "Scale the UV mapping of a Scenario material"
    material_name: StringProperty()
    scale: bpy.props.FloatProperty(name="Tiling", default=1.0, min=0.01, max=100.0)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        from . import apply_material

        mat = bpy.data.materials.get(self.material_name)
        if mat is None:
            self.report({'ERROR'}, "Material not found")
            return {'CANCELLED'}
        apply_material.set_tiling(mat, self.scale)
        return {'FINISHED'}
```
and append it to `CLASSES`.

In `scenario/blender/panels.py`, inside `draw_generate_lane` before the Generate row, add:
```python
    if lane == "material":
        meshes = [o for o in context.selected_objects if o.type == 'MESH']
        if meshes:
            layout.label(text=f"Applies to {len(meshes)} selected mesh(es)", icon='MATERIAL')
        else:
            layout.label(text="Select a mesh to apply the material on arrival", icon='INFO')
```
and in `SCENARIO_PT_results.draw`, for `rec.kind == "material"` rows show `box.label(text="PBR material", icon='MATERIAL')` plus a `scenario.retile_material` button when a material named `Scenario <prompt[:40]>` exists (`bpy.data.materials.get(...)`).

Also enable the Materials lane and the 3D lane in `SCENARIO_PT_main.draw` (`lane in ("image", "3d", "material")` already covers it).

Run: `./tools/install_dev.sh && make test-blender` Expected: OK. GUI screenshot: `... tools/gui_screenshot.py -- ~/Developer/scratch/playwright-screenshots/scenario-blender/p1-materials.png material` and check the maps toggles, the "Applies to" hint and the CU on Generate.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat(blender): Materials lane with Patina, target selection and tiling"
```

---

### Task 15: 3D import at the cursor (pure placement math + Blender importer)

**Files:**
- Create: `scenario/core/scene/placement.py`, `scenario/blender/apply_3d.py`
- Modify: `scenario/blender/handlers.py` (register `"3d"`)
- Test: `tests/unit/test_placement.py`, `tests/blender/test_apply_3d.py`

**Interfaces:**
- Produces: `placement.bottom_center_offset(bbox_min, bbox_max, target) -> (dx, dy, dz)`; `placement.importer_for(path) -> "gltf" | "fbx" | "obj" | None`; `apply_3d.import_model(context, path, at_cursor=True) -> list[Object]`; `apply_3d.ensure_collection(scene, name="Scenario") -> Collection`; `apply_3d.on_3d_result(rec) -> list[Object]`.

- [ ] **Step 1: Failing tests**

`tests/unit/test_placement.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
from scenario.core.scene import placement


def test_bottom_center_offset_moves_bbox_bottom_to_target():
    dx, dy, dz = placement.bottom_center_offset((-1, -2, 0.5), (3, 2, 4.5), (10, 20, 30))
    assert (dx, dy, dz) == (9.0, 20.0, 29.5)


def test_importer_for_extension():
    assert placement.importer_for("a.glb") == "gltf" and placement.importer_for("b.GLTF") == "gltf"
    assert placement.importer_for("c.fbx") == "fbx" and placement.importer_for("d.obj") == "obj"
    assert placement.importer_for("e.vox") is None
```

`tests/blender/test_apply_3d.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import tempfile
import unittest
from pathlib import Path

import bpy

from helpers import reset_scene, submodule


def make_glb(path):
    bpy.ops.mesh.primitive_cube_add(location=(5, 5, 5))
    bpy.ops.export_scene.gltf(filepath=str(path), use_selection=True, export_format='GLB')
    bpy.ops.object.delete()


class Apply3DTests(unittest.TestCase):
    def setUp(self):
        reset_scene()
        self.apply_3d = submodule("blender.apply_3d")
        self.tmp = Path(tempfile.mkdtemp(prefix="scenario-3d-"))
        self.glb = self.tmp / "cube.glb"
        make_glb(self.glb)

    def test_import_places_bottom_center_on_cursor_in_scenario_collection(self):
        bpy.context.scene.cursor.location = (2.0, -3.0, 1.0)
        objects = self.apply_3d.import_model(bpy.context, str(self.glb), at_cursor=True)
        self.assertEqual(len(objects), 1)
        obj = objects[0]
        bpy.context.view_layer.update()
        corners = [obj.matrix_world @ __import__("mathutils").Vector(c) for c in obj.bound_box]
        zmin = min(c.z for c in corners)
        xs = [c.x for c in corners]
        self.assertAlmostEqual(zmin, 1.0, places=4)
        self.assertAlmostEqual((min(xs) + max(xs)) / 2, 2.0, places=4)
        self.assertIn(obj.name, bpy.data.collections["Scenario"].objects)
        self.assertIs(bpy.context.view_layer.objects.active, obj)

    def test_on_3d_result_imports_every_file(self):
        records = submodule("core.jobs.records")
        rec = records.JobRecord.new(lane="3d", kind="3d", model_id="model_meshy-7-txt23d", body={})
        rec.files = [str(self.glb)]
        rec.meta["prompt"] = "a cube"
        objects = self.apply_3d.on_3d_result(rec)
        self.assertEqual(len(objects), 1)
        self.assertTrue(objects[0].name.startswith("Scenario a cube") or objects[0].name == "Cube")
```

- [ ] **Step 2: Implement**

`scenario/core/scene/placement.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Placement math and importer selection for 3D results. No bpy."""
import pathlib

_IMPORTERS = {".glb": "gltf", ".gltf": "gltf", ".fbx": "fbx", ".obj": "obj"}


def importer_for(path):
    return _IMPORTERS.get(pathlib.Path(str(path)).suffix.lower())


def bottom_center_offset(bbox_min, bbox_max, target):
    cx = (bbox_min[0] + bbox_max[0]) / 2.0
    cy = (bbox_min[1] + bbox_max[1]) / 2.0
    return (float(target[0] - cx), float(target[1] - cy), float(target[2] - bbox_min[2]))
```

`scenario/blender/apply_3d.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Import GLB/FBX/OBJ results, place them at the 3D cursor inside a 'Scenario' collection."""
import logging

import bpy
from mathutils import Vector

from . import runtime
from ..core.scene import placement

log = logging.getLogger("scenario.3d")


def ensure_collection(scene, name="Scenario"):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    return coll


def _run_importer(kind, path):
    if kind == "gltf":
        bpy.ops.import_scene.gltf(filepath=path)
    elif kind == "fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    elif kind == "obj":
        bpy.ops.wm.obj_import(filepath=path)
    else:
        raise RuntimeError(f"no importer for {path}")


def _world_bbox(objects):
    points = []
    for obj in objects:
        if obj.type != 'MESH':
            continue
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not points:
        return None
    return (tuple(min(p[i] for p in points) for i in range(3)), tuple(max(p[i] for p in points) for i in range(3)))


def import_model(context, path, at_cursor=True, collection_name="Scenario"):
    kind = placement.importer_for(path)
    before = set(bpy.data.objects)
    _run_importer(kind, path)
    new_objects = [o for o in bpy.data.objects if o not in before]
    scene = context.scene
    coll = ensure_collection(scene, collection_name)
    for obj in new_objects:
        for other in list(obj.users_collection):
            if other is not coll:
                other.objects.unlink(obj)
        if obj.name not in coll.objects:
            coll.objects.link(obj)
    context.view_layer.update()
    roots = [o for o in new_objects if o.parent is None or o.parent not in new_objects]
    if at_cursor and roots:
        bbox = _world_bbox(new_objects)
        if bbox is not None:
            dx, dy, dz = placement.bottom_center_offset(bbox[0], bbox[1], tuple(scene.cursor.location))
            for root in roots:
                root.location = (root.location.x + dx, root.location.y + dy, root.location.z + dz)
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    for obj in new_objects:
        obj.select_set(True)
    if roots:
        context.view_layer.objects.active = roots[0]
    return new_objects


def on_3d_result(rec):
    imported = []
    prompt = (rec.meta.get("prompt") or "").strip()
    for path in rec.files:
        if placement.importer_for(path) is None:
            log.info("skipping non-mesh result %s", path)
            continue
        objects = import_model(bpy.context, path, at_cursor=True)
        if prompt and len(objects) == 1:
            objects[0].name = f"Scenario {prompt[:40]}"
        imported.extend(objects)
    runtime.set_message(f"Imported {len(imported)} object(s) at the 3D cursor")
    return imported
```

Register in `handlers.py`: `RESULT_HANDLERS["3d"] = apply_3d.on_3d_result` (import `apply_3d`).

Run: `python3 -m pytest tests/unit/test_placement.py -v` (2 passed) then `./tools/install_dev.sh && make test-blender` (OK).

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat(blender): import 3D results at the cursor in a Scenario collection"
```

---

### Task 16: 3D lane UI with Text / Image / Multi-view modes

**Files:**
- Modify: `scenario/blender/props.py` (add `three_d_mode` enum to `ScenarioSceneProps`), `scenario/blender/generation.py` (filter models by mode), `scenario/blender/panels.py` (mode row)
- Test: `tests/blender/test_3d_lane.py`

**Interfaces:**
- Produces: `ScenarioSceneProps.three_d_mode` in `('TEXT', 'IMAGE', 'MULTI')`; `generation.three_d_models(mode, records) -> list[ModelRecord]` (TEXT = `txt23d` capability; IMAGE = `img23d` with a scalar `file` image input or `file_array` max 1; MULTI = `img23d` with a `file_array` image input allowing more than one); the 3D lane's model enum refreshes when the mode changes.

- [ ] **Step 1: Failing headless test**

`tests/blender/test_3d_lane.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import unittest

import bpy

from helpers import FIXTURES, submodule


def rec(name):
    catalog = submodule("core.api.catalog")
    return catalog.ModelRecord.from_api(json.loads((FIXTURES / "models" / f"{name}.json").read_text())["model"])


class ThreeDLaneTests(unittest.TestCase):
    def test_three_d_models_by_mode(self):
        generation = submodule("blender.generation")
        records = [rec("model_meshy-7-txt23d"), rec("model_meshy-7-img23d"), rec("model_tripo-v3-1-image-to-3d")]
        self.assertEqual([r.id for r in generation.three_d_models('TEXT', records)], ["model_meshy-7-txt23d"])
        image_ids = [r.id for r in generation.three_d_models('IMAGE', records)]
        self.assertIn("model_tripo-v3-1-image-to-3d", image_ids)
        multi_ids = [r.id for r in generation.three_d_models('MULTI', records)]
        self.assertIn("model_meshy-7-img23d", multi_ids)
        self.assertNotIn("model_meshy-7-txt23d", multi_ids)

    def test_mode_change_refreshes_model_enum(self):
        runtime = submodule("blender.runtime")
        handlers = submodule("blender.handlers")
        runtime.state.reset()
        records = [rec("model_meshy-7-txt23d"), rec("model_meshy-7-img23d")]
        handlers.dispatch(("catalog", {"privacy": "public", "records": records, "detailed": records}))
        scene = bpy.context.scene
        scene.scenario.three_d_mode = 'TEXT'
        self.assertEqual([i[0] for i in runtime.enum_items(("models", "3d"))], ["model_meshy-7-txt23d"])
        scene.scenario.three_d_mode = 'MULTI'
        self.assertEqual([i[0] for i in runtime.enum_items(("models", "3d"))], ["model_meshy-7-img23d"])
```

- [ ] **Step 2: Implement**

In `props.py`, add to `ScenarioSceneProps`:
```python
    three_d_mode: EnumProperty(name="Input", items=[('TEXT', "Text", "Describe the object"), ('IMAGE', "Image", "One reference image"), ('MULTI', "Multi-view", "Several views of the same object")], default='TEXT', update=lambda self, context: __import__(__package__ + ".generation", fromlist=["refresh_3d_models"]).refresh_3d_models(context))
```
(Keep the lambda short; if the import expression is awkward, define `def _on_mode_change(self, context): from . import generation; generation.refresh_3d_models(context)` above the class and use `update=_on_mode_change`.)

In `generation.py` add:
```python
def _image_inputs(record):
    return [p for p in record.parameters if p.get("type") in ("file", "file_array") and (p.get("kind") or "image") == "image"]


def three_d_models(mode, records):
    out = []
    for record in records:
        caps = set(record.capabilities)
        if record.deprecated_successor:
            continue
        if mode == 'TEXT':
            if "txt23d" in caps:
                out.append(record)
            continue
        if "img23d" not in caps:
            continue
        inputs = _image_inputs(record)
        if not inputs:
            continue
        multi = any(p.get("type") == "file_array" and (p.get("maxLength") or 2) > 1 for p in inputs)
        if (mode == 'MULTI' and multi) or (mode == 'IMAGE' and not (multi and all(p.get("type") == "file_array" for p in inputs))):
            out.append(record)
    return models_for_lane("3d", out)


def refresh_3d_models(context):
    scene = context.scene if context else bpy.context.scene
    all_records = list(runtime.state.records.values())
    records = three_d_models(scene.scenario.three_d_mode, all_records)
    runtime.state.lane_models["3d"] = records
    runtime.set_enum_items(("models", "3d"), [(r.id, r.name, r.short_description) for r in records])
    on_model_changed(context, scene.scenario.lane_state("3d"))
```
and in `set_catalog`, after the lane loop, call `refresh_3d_models(bpy.context)` (guarded by `if bpy.context.scene is not None`). Note: `three_d_models` needs detailed records (with `parameters`) to detect inputs; list entries without parameters fall into the IMAGE bucket only when they carry `img23d`; that is acceptable for P1 and the P4 polish fetches details lazily.

In `panels.py` `draw_generate_lane`, for `lane == "3d"` draw `layout.row(align=True).prop(context.scene.scenario, "three_d_mode", expand=True)` above the model dropdown.

Run: `./tools/install_dev.sh && make test-blender` Expected: OK. Screenshot `p1-3d.png` with lane `3d`.

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat(blender): 3D lane with text, image and multi-view modes"
```

---

### Task 17: Generations history (cloud jobs + local records, thumbnails, actions)

**Files:**
- Create: `scenario/core/history.py`, `scenario/blender/history.py`
- Modify: `scenario/blender/panels.py` (history lane), `scenario/blender/operators.py` (`scenario.history_refresh`, `scenario.history_older`, `scenario.import_result`)
- Test: `tests/unit/test_history.py`, `tests/blender/test_history.py`

**Interfaces:**
- Produces: `history.HistoryEntry(job_id, kind, model_id, prompt, status, created_at, cu_cost, asset_ids, local_files)`; `history.entries_from_jobs(jobs, registry_records) -> list[HistoryEntry]` (merges cloud jobs with local files by `job_id`, newest first, only `jobType == "custom"` with assets or failures); `history.kind_for_job(job) -> str` (`3d` when any `metadata.input` key hints a mesh model via `LANE_CAPS`? no: use the model record capabilities when known, else `image`); `blender.history.refresh()` (worker: `jobs.list_jobs` page 1 -> event `("history", {"entries": [...], "token": str})`), `blender.history.older()`; `runtime.state.history` list and `runtime.state.history_token`; operator `scenario.import_result(job_id)` downloads assets of a cloud job not present locally and applies by kind.

- [ ] **Step 1: Failing unit test**

`tests/unit/test_history.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
from scenario.core import history
from scenario.core.jobs.records import JobRecord


def test_entries_merge_cloud_jobs_with_local_files():
    local = JobRecord.new(lane="image", kind="image", model_id="model_g", body={})
    local.job_id, local.status, local.files = "job_a", "success", ["/out/a.png"]
    jobs = [
        {"jobId": "job_a", "jobType": "custom", "status": "success", "createdAt": "2026-08-28T07:37:09.434Z", "billing": {"cuCost": 6},
         "metadata": {"input": {"modelId": "model_g", "prompt": "teapot"}, "assetIds": ["asset_1"]}},
        {"jobId": "job_b", "jobType": "upload", "status": "success", "createdAt": "2026-08-28T07:40:00.000Z", "metadata": {"input": {}}},
        {"jobId": "job_c", "jobType": "custom", "status": "failure", "createdAt": "2026-08-28T08:00:00.000Z", "metadata": {"input": {"modelId": "model_m", "prompt": "x"}, "assetIds": []}},
    ]
    entries = history.entries_from_jobs(jobs, [local], kinds={"model_m": "3d"})
    assert [e.job_id for e in entries] == ["job_c", "job_a"]
    a = entries[1]
    assert a.local_files == ["/out/a.png"] and a.prompt == "teapot" and a.cu_cost == 6.0 and a.kind == "image"
    assert entries[0].kind == "3d" and entries[0].status == "failure"
```

- [ ] **Step 2: Implement core**

`scenario/core/history.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Merge the cloud job list with local job records for the Generations panel. No bpy."""
from dataclasses import dataclass, field


@dataclass
class HistoryEntry:
    job_id: str
    kind: str
    model_id: str
    prompt: str
    status: str
    created_at: str
    cu_cost: float = None
    asset_ids: list = field(default_factory=list)
    local_files: list = field(default_factory=list)

    @property
    def is_success(self):
        return self.status in ("success", "succeeded", "completed")


def entries_from_jobs(jobs, local_records, kinds=None):
    kinds = kinds or {}
    local_by_job = {r.job_id: r for r in local_records if r.job_id}
    entries = []
    for job in jobs:
        if job.get("jobType") != "custom":
            continue
        meta = job.get("metadata") or {}
        inp = meta.get("input") or {}
        job_id = job.get("jobId") or job.get("id")
        local = local_by_job.get(job_id)
        model_id = inp.get("modelId") or (local.model_id if local else "")
        billing = job.get("billing") or {}
        entries.append(HistoryEntry(
            job_id=job_id,
            kind=(local.kind if local else kinds.get(model_id, "image")),
            model_id=model_id,
            prompt=str(inp.get("prompt") or (local.meta.get("prompt") if local else "") or ""),
            status=(job.get("status") or "").lower(),
            created_at=job.get("createdAt") or "",
            cu_cost=float(billing["cuCost"]) if billing.get("cuCost") is not None else None,
            asset_ids=list(meta.get("assetIds") or []),
            local_files=list(local.files) if local else [],
        ))
    entries.sort(key=lambda e: e.created_at, reverse=True)
    return entries
```

Run: `python3 -m pytest tests/unit/test_history.py -v` Expected: 1 passed.

- [ ] **Step 3: Blender side: worker, event, panel, operators**

`scenario/blender/history.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generations panel data: cloud job pages merged with local records."""
import threading

from . import runtime
from ..core import history as core_history
from ..core.api import jobs as jobs_api
from ..core.api.errors import ScenarioError


def _kinds():
    kinds = {}
    for lane, records in runtime.state.lane_models.items():
        kind = {"image": "image", "video": "video", "3d": "3d", "material": "material"}.get(lane)
        if kind:
            for record in records:
                kinds.setdefault(record.id, kind)
    return kinds


def _fetch(token, append):
    manager = runtime.state.manager
    try:
        client = runtime.make_client()
        rows, next_token = jobs_api.list_jobs(client, page_size=50, token=token)
    except ScenarioError as err:
        manager.events.put(("error", f"history: {err.reason}"))
        return
    manager.events.put(("history", {"jobs": rows, "token": next_token, "append": append}))


def refresh():
    manager = runtime.ensure_manager()
    threading.Thread(target=_fetch, args=(None, False), daemon=True, name="scenario-history").start()
    return manager


def older():
    token = runtime.state.history_token
    if not token:
        return False
    runtime.ensure_manager()
    threading.Thread(target=_fetch, args=(token, True), daemon=True, name="scenario-history").start()
    return True


def on_history_event(payload):
    entries = core_history.entries_from_jobs(payload["jobs"], runtime.state.manager.registry.all(), kinds=_kinds())
    if payload.get("append"):
        known = {e.job_id for e in runtime.state.history}
        runtime.state.history.extend(e for e in entries if e.job_id not in known)
    else:
        runtime.state.history = entries
    runtime.state.history_token = payload.get("token")
```

Add to `RuntimeState.__init__`: `self.history = []` and `self.history_token = None`. In `handlers.dispatch` add `elif name == "history": history.on_history_event(payload)` (import `history`).

Operators (append to `operators.py` and `CLASSES`):
```python
class SCENARIO_OT_history_refresh(bpy.types.Operator):
    bl_idname = "scenario.history_refresh"
    bl_label = "Refresh generations"

    def execute(self, context):
        from . import history

        history.refresh()
        return {'FINISHED'}


class SCENARIO_OT_history_older(bpy.types.Operator):
    bl_idname = "scenario.history_older"
    bl_label = "Load older"

    def execute(self, context):
        from . import history

        return {'FINISHED'} if history.older() else {'CANCELLED'}


class SCENARIO_OT_import_result(bpy.types.Operator):
    bl_idname = "scenario.import_result"
    bl_label = "Import into scene"
    bl_description = "Download this generation (if needed) and bring it into the scene"
    job_id: StringProperty()
    kind: StringProperty(default="image")
    model_id: StringProperty()
    prompt: StringProperty()

    def execute(self, context):
        from ..core.jobs.records import JobRecord

        manager = runtime.ensure_manager()
        existing = next((r for r in manager.registry.all() if r.job_id == self.job_id and r.files), None)
        if existing is not None:
            from . import handlers

            handlers.dispatch(("job_done", existing))
            return {'FINISHED'}
        rec = JobRecord.new(lane=self.kind if self.kind != "3d" else "3d", kind=self.kind, model_id=self.model_id, body={}, meta={"prompt": self.prompt, "model_name": self.model_id})
        rec.job_id, rec.status = self.job_id, "in-progress"
        rec.meta["target_objects"] = [o.name for o in context.selected_objects if o.type == 'MESH']
        manager.registry.add(rec)
        manager.registry.save()
        manager._spawn(manager._poll_job, rec)
        runtime.state.jobs_view.insert(0, rec)
        self.report({'INFO'}, "Downloading generation")
        return {'FINISHED'}
```

Panel: in `SCENARIO_PT_main.draw`, for `lane == "history"` call `draw_history(layout, context)`:
```python
def draw_history(layout, context):
    row = layout.row(align=True)
    row.operator("scenario.history_refresh", icon='FILE_REFRESH')
    row.operator("scenario.open_output_folder", text="", icon='FILE_FOLDER')
    if not runtime.state.history:
        layout.label(text="Press Refresh to list this project's generations")
        return
    for entry in runtime.state.history[:24]:
        box = layout.box()
        header = box.row()
        icon = {'image': 'IMAGE_DATA', 'video': 'FILE_MOVIE', '3d': 'MESH_DATA', 'material': 'MATERIAL'}.get(entry.kind, 'FILE')
        header.label(text=(entry.prompt or entry.model_id)[:48], icon=icon)
        header.label(text=f"{entry.cu_cost:g} CU" if entry.cu_cost is not None else entry.status)
        if entry.local_files and entry.kind == "image":
            icon_id = _thumbnail(entry.local_files[0])
            if icon_id:
                box.template_icon(icon_value=icon_id, scale=3.0)
        if entry.is_success:
            op = box.operator("scenario.import_result", text="Import into scene" if not entry.local_files else "Bring into scene again", icon='IMPORT')
            op.job_id, op.kind, op.model_id, op.prompt = entry.job_id, entry.kind, entry.model_id, entry.prompt
        elif entry.status not in ("success",):
            box.label(text=entry.status, icon='ERROR' if entry.status in ("failure", "canceled") else 'TIME')
    if runtime.state.history_token:
        layout.operator("scenario.history_older", icon='TRIA_DOWN')
```

`tests/blender/test_history.py`:
```python
# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest

from helpers import submodule


class HistoryTests(unittest.TestCase):
    def test_history_event_populates_state(self):
        runtime = submodule("blender.runtime")
        handlers = submodule("blender.handlers")
        runtime.state.reset()
        runtime.ensure_manager()
        jobs = [{"jobId": "job_h", "jobType": "custom", "status": "success", "createdAt": "2026-08-28T07:37:09.434Z",
                 "metadata": {"input": {"modelId": "model_g", "prompt": "hello"}, "assetIds": ["asset_1"]}}]
        handlers.dispatch(("history", {"jobs": jobs, "token": "tok2", "append": False}))
        self.assertEqual([e.job_id for e in runtime.state.history], ["job_h"])
        self.assertEqual(runtime.state.history_token, "tok2")
        handlers.dispatch(("history", {"jobs": jobs, "token": None, "append": True}))
        self.assertEqual(len(runtime.state.history), 1)
```

Note: `runtime.ensure_manager()` needs valid credentials for `make_client`, but the manager is created lazily with a factory, so it works without a key; if `ensure_manager` raises in the headless test, set prefs `api_key`/`api_secret` to `"k"`/`"s"` in `setUp` and clear in `tearDown`.

Run: `./tools/install_dev.sh && make test-blender` Expected: OK. Screenshot `p1-history.png` (after pressing Refresh in a GUI session with the key set) and look at it.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat(blender): Generations history with cloud jobs, thumbnails and import"
```

---

### Task 18: P1 smoke, docs and merge

**Files:**
- Create: `tests/smoke/smoke_material.py`
- Modify: `CHANGELOG.md`, `README.md`, `CLAUDE.md`

- [ ] **Step 1: Opt-in material smoke (about 7 CU)**

`tests/smoke/smoke_material.py`: same shape as `tests/smoke/smoke_image.py` but `model_patina-material`, body `{"prompt": "mossy stone wall", "width": 512, "height": 512, "numOutputs": 1}`, lane/kind `material`, and on `job_done` assert `len(payload.files) == 6` and print `payload.asset_types`. Run: `SCENARIO_SMOKE=1 python3 tests/smoke/smoke_material.py`.

- [ ] **Step 2: Headless end-to-end with the real result (no GUI needed)**

Run inside Blender: `$BLENDER --background --python-expr "import bpy, json, importlib; name=[n for n in bpy.context.preferences.addons.keys() if n.endswith('.scenario')][0]; mp=importlib.import_module(name+'.core.scene.material_plan'); am=importlib.import_module(name+'.blender.apply_material'); import glob; files=sorted(glob.glob('<output_dir printed by the smoke>/*.png')); print(len(files))"` and confirm 6 files exist in `~/Downloads/Scenario/materials/` (or the smoke's temp dir). Then take GUI screenshots `p1-materials.png`, `p1-3d.png`, `p1-history.png` and look at them.

- [ ] **Step 3: Docs and merge**

CHANGELOG `0.2.0 (P1)`: Materials lane (Patina, material applied on selection, tiling), 3D lane (text / image / multi-view, import at cursor in a Scenario collection), Generations history (cloud jobs, thumbnails, import). README: update the file list and the CU spent. CLAUDE.md: state "P1 done, P2 next".

```bash
make test && make test-blender && git add -A && git commit -m "feat: P1 smoke, docs" && git checkout main && git merge --no-ff p1-materials-3d-history -m "Merge P1: Materials, 3D and Generations" && git log --oneline | head -3
```
