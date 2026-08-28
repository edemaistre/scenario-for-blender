# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import json
import struct

from scenario.core.scene import placement


def make_glb(path, images=0, pbr_textures=0):
    material = {"pbrMetallicRoughness": {}}
    keys = ["baseColorTexture", "metallicRoughnessTexture"]
    for i in range(min(pbr_textures, 2)):
        material["pbrMetallicRoughness"][keys[i]] = {"index": i}
    if pbr_textures > 2:
        material["normalTexture"] = {"index": 2}
    js = json.dumps({"asset": {"version": "2.0"}, "images": [{"bufferView": i} for i in range(images)], "materials": [material]}).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    body = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js)) + struct.pack("<II", len(js), 0x4E4F534A) + js
    path.write_bytes(body)
    return str(path)


def test_glb_summary_reads_images_and_pbr_textures(tmp_path):
    p = make_glb(tmp_path / "pbr.glb", images=3, pbr_textures=3)
    assert placement.glb_summary(p) == {"images": 3, "pbr_textures": 3, "materials": 1}
    (tmp_path / "junk.glb").write_bytes(b"not a glb")
    assert placement.glb_summary(tmp_path / "junk.glb")["images"] == 0


def test_pick_primary_prefers_pbr_glb_over_shaded_glb_and_obj(tmp_path):
    shaded = make_glb(tmp_path / "a_00.glb", images=1, pbr_textures=0)
    pbr = make_glb(tmp_path / "a_02.glb", images=3, pbr_textures=3)
    obj = tmp_path / "a_01.obj"
    obj.write_text("o model\nv 0 0 0\n" * 1000)
    (tmp_path / "a_03.png").write_bytes(b"png")
    primary, alternates = placement.pick_primary_mesh([shaded, str(obj), pbr, str(tmp_path / "a_03.png")])
    assert primary == pbr
    assert alternates == [shaded, str(obj)]


def test_pick_primary_handles_no_mesh():
    assert placement.pick_primary_mesh(["/x/a.png", "/x/b.webp"]) == (None, [])
