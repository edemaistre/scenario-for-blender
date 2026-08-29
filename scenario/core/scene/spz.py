# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reader for SPZ Gaussian splats (Niantic's compressed format, what Marble and HY World return). No bpy.

An .spz file is a gzip stream: a 16-byte header (magic "NGSP", version, point count, SH degree, fractional bits,
flags), then the attributes packed per point in fixed order: positions (3 x 24-bit fixed point), alphas (u8),
colours (3 x u8, the SH DC term), scales (3 x u8, log scale), rotations, spherical harmonics. Blender has no splat
renderer, so we read positions, colours, alphas and scales and hand back a point cloud; rotations and SH are skipped."""
import gzip
import math
import struct

MAGIC = 0x5053474E  # "NGSP"
SH_C0 = 0.28209479177387814
COLOR_SCALE = 0.15


class SpzError(ValueError):
    pass



def sniff_spz(path):
    """True when the file is a gzip stream whose first bytes are the SPZ magic (a splat saved with a .bin extension)."""
    try:
        with gzip.open(str(path), "rb") as handle:
            head = handle.read(4)
    except (OSError, EOFError, ValueError):
        return False
    return len(head) == 4 and struct.unpack("<I", head)[0] == MAGIC


def read_spz(path, max_points=None):
    """Decode an .spz file. Returns a dict with `count`, `positions` [(x, y, z)], `colors` [(r, g, b)], `alphas`,
    `scales` (median world scale per point), `version`, `sh_degree`; the layout is Y-up like the file.

    `max_points` keeps every n-th point so multi-million splats stay interactive in Blender."""
    with gzip.open(str(path), "rb") as handle:
        data = handle.read()
    if len(data) < 16:
        raise SpzError("not an SPZ file (too short)")
    magic, version, count, sh_degree, fractional_bits, _flags, _reserved = struct.unpack_from("<IIIBBBB", data, 0)
    if magic != MAGIC:
        raise SpzError("not an SPZ file (bad magic)")
    if version not in (1, 2, 3):
        raise SpzError(f"unsupported SPZ version {version}")
    pos_off = 16
    alpha_off = pos_off + count * 9
    color_off = alpha_off + count
    scale_off = color_off + count * 3
    rot_off = scale_off + count * 3
    needed = rot_off
    if len(data) < needed:
        raise SpzError(f"truncated SPZ file: {len(data)} bytes for {count} points")
    step = 1
    if max_points and count > max_points:
        step = int(math.ceil(count / float(max_points)))
    denom = float(1 << fractional_bits)
    positions, colors, alphas, scales = [], [], [], []
    for i in range(0, count, step):
        p = pos_off + i * 9
        xyz = []
        for k in range(3):
            b0, b1, b2 = data[p + 3 * k], data[p + 3 * k + 1], data[p + 3 * k + 2]
            raw = b0 | (b1 << 8) | (b2 << 16)
            if raw & 0x800000:
                raw -= 0x1000000
            xyz.append(raw / denom)
        positions.append(tuple(xyz))
        c = color_off + i * 3
        rgb = []
        for k in range(3):
            sh0 = (data[c + k] / 255.0 - 0.5) / COLOR_SCALE
            rgb.append(min(1.0, max(0.0, 0.5 + SH_C0 * sh0)))
        colors.append(tuple(rgb))
        alphas.append(data[alpha_off + i] / 255.0)
        s = scale_off + i * 3
        logs = sorted(data[s + k] / 16.0 - 10.0 for k in range(3))
        scales.append(math.exp(logs[1]))
    return {"count": count, "kept": len(positions), "step": step, "version": version, "sh_degree": sh_degree,
            "positions": positions, "colors": colors, "alphas": alphas, "scales": scales}


def y_up_to_z_up(position):
    """SPZ files are Y-up (glTF convention); Blender is Z-up."""
    x, y, z = position
    return (x, -z, y)


def write_spz(path, positions, colors, alphas=None, scales=None, fractional_bits=12):
    """Encode a minimal SPZ (version 2, no SH, identity rotations). Used by tests and to round-trip subsamples."""
    count = len(positions)
    alphas = alphas or [1.0] * count
    scales = scales or [0.01] * count
    out = bytearray(struct.pack("<IIIBBBB", MAGIC, 2, count, 0, fractional_bits, 0, 0))
    scale = float(1 << fractional_bits)
    for x, y, z in positions:
        for v in (x, y, z):
            raw = int(round(v * scale)) & 0xFFFFFF
            out += bytes((raw & 0xFF, (raw >> 8) & 0xFF, (raw >> 16) & 0xFF))
    out += bytes(int(round(min(1.0, max(0.0, a)) * 255)) for a in alphas)
    for r, g, b in colors:
        for v in (r, g, b):
            sh0 = (min(1.0, max(0.0, v)) - 0.5) / SH_C0
            out.append(int(round(min(1.0, max(0.0, sh0 * COLOR_SCALE + 0.5)) * 255)))
    for s in scales:
        byte = int(round((math.log(max(1e-6, s)) + 10.0) * 16.0))
        out += bytes((min(255, max(0, byte)),) * 3)
    out += bytes(count * 3)  # rotations
    with gzip.open(str(path), "wb") as handle:
        handle.write(bytes(out))
    return path
