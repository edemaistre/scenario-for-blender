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
    return [(rec.asset_types.get(asset_id, ""), path) for asset_id, path in zip(rec.asset_ids, rec.files)]
