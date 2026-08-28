# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Placement math, importer selection and primary-mesh choice for 3D results. No bpy."""
import json
import pathlib
import struct

_IMPORTERS = {".glb": "gltf", ".gltf": "gltf", ".fbx": "fbx", ".obj": "obj"}
_FORMAT_RANK = {"gltf": 0, "fbx": 1, "obj": 2}


def importer_for(path):
    return _IMPORTERS.get(pathlib.Path(str(path)).suffix.lower())


def bottom_center_offset(bbox_min, bbox_max, target):
    cx = (bbox_min[0] + bbox_max[0]) / 2.0
    cy = (bbox_min[1] + bbox_max[1]) / 2.0
    return (float(target[0] - cx), float(target[1] - cy), float(target[2] - bbox_min[2]))


def glb_summary(path):
    """Read the JSON chunk of a binary glTF: image count and whether the first material has PBR textures."""
    try:
        with open(path, "rb") as fh:
            magic, _version, _length = struct.unpack("<4sII", fh.read(12))
            if magic != b"glTF":
                return {"images": 0, "pbr_textures": 0, "materials": 0}
            chunk_len, _chunk_type = struct.unpack("<II", fh.read(8))
            js = json.loads(fh.read(chunk_len))
    except (OSError, ValueError, struct.error):
        return {"images": 0, "pbr_textures": 0, "materials": 0}
    materials = js.get("materials") or []
    pbr = 0
    for mat in materials:
        pbr += sum(1 for key in (mat.get("pbrMetallicRoughness") or {}) if key.endswith("Texture"))
        pbr += sum(1 for key in ("normalTexture", "occlusionTexture") if key in mat)
    return {"images": len(js.get("images") or []), "pbr_textures": pbr, "materials": len(materials)}


def rank_mesh_files(paths):
    """Order mesh files from the one to import first to the least useful.

    Providers ship several variants of one result (Meshy: GLB + OBJ + textures, Rodin with material=All: a shaded GLB
    and a PBR GLB). Prefer glTF, then the file with the most PBR textures, then the most images, then the larger file.
    """
    ranked = []
    for path in paths:
        kind = importer_for(path)
        if kind is None:
            continue
        info = glb_summary(path) if kind == "gltf" else {"images": 0, "pbr_textures": 0, "materials": 0}
        try:
            size = pathlib.Path(path).stat().st_size
        except OSError:
            size = 0
        ranked.append((_FORMAT_RANK[kind], -info["pbr_textures"], -info["images"], -size, str(path), info))
    ranked.sort()
    return [(entry[4], entry[5]) for entry in ranked]


def pick_primary_mesh(paths):
    """Return (primary_path, alternates) or (None, [])."""
    ranked = rank_mesh_files(paths)
    if not ranked:
        return None, []
    return ranked[0][0], [path for path, _ in ranked[1:]]
