# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Camera path planning for the Render Video lane: waypoints, frame schedules, one-click presets, a text parser. No bpy."""
import math
import re
from dataclasses import dataclass

SENSOR_WIDTH = 36.0      # mm, Blender's default camera sensor
FILL = 0.7               # the subject fills about 70% of the frame at the preset distance
MIN_SEGMENT_SHARE = 0.05  # a zero-length segment (two markers at the same spot) still gets 5% of the move time
DEFAULT_DURATION = 6.0
DEFAULT_FOCAL = 35.0
MIN_DURATION, MAX_DURATION = 1.0, 60.0


@dataclass
class Waypoint:
    """One camera pose. `rotation_euler` wins over `look_at`; with neither, the caller aims the camera."""
    position: tuple
    rotation_euler: tuple = None
    look_at: tuple = None
    focal: float = DEFAULT_FOCAL
    hold: float = 0.0


def distance(a, b):
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def frame_schedule(waypoints, duration, fps):
    """Keyframes as (frame, waypoint_index) pairs from frame 1 to round(duration * fps): a 12 s move at 24 fps spans frames 1 to 288.

    Each waypoint holds still for `hold` seconds (a held waypoint yields two keys), the remaining time is split
    between segments in proportion to their length, with a floor so a zero-length segment still takes time."""
    n = len(waypoints)
    if n == 0:
        return []
    duration = max(1e-6, float(duration))
    total = max(2, int(round(duration * float(fps or 24))))
    last = total
    if n == 1:
        return [(1, 0), (last, 0)]
    holds = [max(0.0, float(wp.hold or 0.0)) for wp in waypoints]
    hold_total = sum(holds)
    if hold_total > 0 and hold_total >= duration * 0.75:
        factor = (duration * 0.75) / hold_total  # keep at least a quarter of the time for the moves
        holds = [h * factor for h in holds]
        hold_total = sum(holds)
    move_time = max(0.0, duration - hold_total)
    dists = [distance(waypoints[i].position, waypoints[i + 1].position) for i in range(n - 1)]
    total_d = sum(dists)
    shares = [(d / total_d) if total_d > 0 else 1.0 / (n - 1) for d in dists]
    shares = [max(s, MIN_SEGMENT_SHARE) for s in shares]
    share_sum = sum(shares)
    shares = [s / share_sum for s in shares]
    times = [(0.0, 0)]
    t = 0.0
    if holds[0] > 0:
        t += holds[0]
        times.append((t, 0))
    for i, share in enumerate(shares):
        t += share * move_time
        times.append((t, i + 1))
        if holds[i + 1] > 0:
            t += holds[i + 1]
            times.append((t, i + 1))
    keys = []
    for time_s, index in times:
        frame = 1 + int(round(time_s / duration * (total - 1)))
        if keys and frame <= keys[-1][0]:
            if keys[-1][1] == index:
                continue  # a hold collapsed onto one frame
            frame = keys[-1][0] + 1
        keys.append((frame, index))
    end_frame = max(last, keys[-1][0])
    keys[-1] = (end_frame, keys[-1][1])
    return keys


# -- presets ------------------------------------------------------------------

def _box(bbox_min, bbox_max):
    lo = tuple(float(v) for v in bbox_min)
    hi = tuple(float(v) for v in bbox_max)
    centre = tuple((a + b) / 2.0 for a, b in zip(lo, hi))
    extents = tuple(max(1e-3, b - a) for a, b in zip(lo, hi))
    size = max(extents)
    diagonal = math.sqrt(sum(e * e for e in extents))
    return centre, size, diagonal


def fit_distance(diagonal, focal):
    """Camera distance at which a sphere of the box's diagonal fills FILL of the frame width."""
    half_fov = math.atan((SENSOR_WIDTH / 2.0) / max(1.0, float(focal)))
    return max(1e-3, diagonal) / (2.0 * FILL * math.tan(half_fov))


def _wp(position, centre, focal):
    return Waypoint(tuple(position), look_at=tuple(centre), focal=float(focal))


def orbit(bbox_min, bbox_max, focal=DEFAULT_FOCAL, steps=8):
    """A full turn around the subject at a constant height, ending where it started (steps + 1 waypoints)."""
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    height = centre[2] + 0.35 * size
    dz = height - centre[2]
    radius = math.sqrt(max(d * d - dz * dz, (0.5 * d) ** 2))
    out = []
    for i in range(steps + 1):
        a = 2 * math.pi * (i % steps) / steps
        out.append(_wp((centre[0] + radius * math.sin(a), centre[1] - radius * math.cos(a), height), centre, focal))
    return out


def push_in(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    height = centre[2] + 0.25 * size
    return [_wp((centre[0], centre[1] - 2.2 * d, height), centre, focal), _wp((centre[0], centre[1] - 0.8 * d, height), centre, focal)]


def pull_back(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    return list(reversed(push_in(bbox_min, bbox_max, focal)))


def crane(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    return [_wp((centre[0], centre[1] - d, centre[2] - 0.2 * size), centre, focal),
            _wp((centre[0], centre[1] - 0.9 * d, centre[2] + 1.2 * size), centre, focal)]


def pan(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    height = centre[2] + 0.2 * size
    return [_wp((centre[0] - 0.9 * d, centre[1] - d, height), centre, focal),
            _wp((centre[0], centre[1] - d, height), centre, focal),
            _wp((centre[0] + 0.9 * d, centre[1] - d, height), centre, focal)]


def flyover(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    return [_wp((centre[0] - 0.6 * d, centre[1] - 2.0 * d, centre[2] + 1.5 * size), centre, focal),
            _wp((centre[0], centre[1] - 1.3 * d, centre[2] + 0.9 * size), centre, focal),
            _wp((centre[0] + 0.3 * d, centre[1] - 0.8 * d, centre[2] + 0.4 * size), centre, focal)]


PRESETS = {
    "orbit": ("Orbit", "A full turn around the subject", orbit),
    "push_in": ("Push in", "From far away up to the subject", push_in),
    "pull_back": ("Pull back", "From the subject out to a wide reveal", pull_back),
    "crane": ("Crane", "Low in front, rising to look down on the subject", crane),
    "pan": ("Pan", "Left to right in front of the subject", pan),
    "flyover": ("Flyover", "High and far, swooping down towards the subject", flyover),
}
DEFAULT_PRESET = "orbit"


def preset_waypoints(name, bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    label, description, fn = PRESETS.get(name) or PRESETS[DEFAULT_PRESET]
    return fn(bbox_min, bbox_max, focal)


# -- text to plan ---------------------------------------------------------------

_PRESET_PATTERNS = (
    ("pull_back", r"\b(pulls?(?:ing)?\s*(?:back|out|away)|zoom(?:s|ing)?\s*out|dolly\s*out|away|reveal(?:s|ing)?|back\s*off)\b"),
    ("push_in", r"\b(push(?:es|ing)?(?:\s*in)?|closer|close[- ]?up|zoom(?:s|ing)?\s*in|dolly\s*in|approach(?:es|ing)?|move\s*in)\b"),
    ("crane", r"\b(crane|ris(?:e|es|ing)|lift(?:s|ing)?|ascend(?:s|ing)?|up\s+and\s+over|tilt(?:s|ing)?\s*down)\b"),
    ("flyover", r"\b(fly(?:ing|over|by)?|fly-?over|drone|aerial|swoop(?:s|ing)?|over(?:head)?|bird)\b"),
    ("pan", r"\b(pan(?:s|ning)?|left\s+to\s+right|right\s+to\s+left|sweep(?:s|ing)?|track(?:s|ing)?\s*(?:along|past)?|sideways|lateral)\b"),
    ("orbit", r"\b(orbit(?:s|ing)?|turntable|around|circle(?:s|ing)?|spin(?:s|ning)?|revolv(?:e|es|ing)|360|rotate(?:s)?|turn(?:s)?\s*around)\b"),
)
_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)\b", re.I)
_FOCAL = re.compile(r"(\d+(?:\.\d+)?)\s*mm\b", re.I)


def plan_from_text(text):
    """A deterministic reading of a shot description: {"preset", "duration", "focal"}. Unknown text keeps the defaults."""
    text = (text or "").strip().lower()
    preset = DEFAULT_PRESET
    for name, pattern in _PRESET_PATTERNS:
        if re.search(pattern, text):
            preset = name
            break
    duration = DEFAULT_DURATION
    match = _DURATION.search(text)
    if match:
        duration = float(match.group(1))
    if re.search(r"\b(slow|slowly|gentle|gently)\b", text):
        duration *= 1.5
    if re.search(r"\b(fast|quick|quickly|snappy|rapid)\b", text):
        duration *= 0.6
    duration = max(MIN_DURATION, min(MAX_DURATION, duration))
    focal = DEFAULT_FOCAL
    match = _FOCAL.search(text)
    if match:
        focal = max(8.0, min(400.0, float(match.group(1))))
    elif re.search(r"\b(wide|wide[- ]angle)\b", text):
        focal = 24.0
    elif re.search(r"\b(tele|telephoto|long lens|tight)\b", text):
        focal = 85.0
    return {"preset": preset, "duration": round(duration, 3), "focal": focal}
