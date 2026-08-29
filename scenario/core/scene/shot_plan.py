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


def _ring(centre, rx, ry, height, focal, steps=12, start=0.0, sweep=2 * math.pi, rise=0.0):
    """Waypoints on an ellipse around `centre` (rx across the front, ry in depth), angle 0 in front of the subject
    (negative Y), turning counter-clockwise seen from above. `rise` lifts the far side (angle pi) by that amount.
    A full sweep closes the loop: the last waypoint repeats the first exactly."""
    out = []
    closed = abs(sweep - 2 * math.pi) < 1e-9
    count = steps + 1
    for i in range(count):
        if closed and i == steps:
            out.append(Waypoint(out[0].position, look_at=out[0].look_at, focal=out[0].focal))
            continue
        a = start + sweep * i / steps
        z = height + rise * (1.0 - math.cos(a)) / 2.0
        out.append(_wp((centre[0] + rx * math.sin(a), centre[1] - ry * math.cos(a), z), centre, focal))
    return out


def _horizontal_radius(d, dz):
    """Radius of a ring at height offset dz that keeps the camera at distance d from the centre."""
    return math.sqrt(max(d * d - dz * dz, (0.5 * d) ** 2))


# Orbits ---------------------------------------------------------------------

def orbit(bbox_min, bbox_max, focal=DEFAULT_FOCAL, steps=12):
    """A full turn around the subject at a constant height, ending exactly where it started (steps + 1 waypoints)."""
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    dz = 0.35 * size
    r = _horizontal_radius(d, dz)
    return _ring(centre, r, r, centre[2] + dz, focal, steps=steps)


def orbit_high(bbox_min, bbox_max, focal=DEFAULT_FOCAL, steps=12):
    """A full turn from above, looking down on the subject."""
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    dz = 0.95 * size
    r = _horizontal_radius(1.15 * d, dz)
    return _ring(centre, r, r, centre[2] + dz, focal, steps=steps)


def orbit_low(bbox_min, bbox_max, focal=DEFAULT_FOCAL, steps=12):
    """A full turn from a hero angle, below the centre height, looking up."""
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    dz = -0.3 * size
    r = _horizontal_radius(d, dz)
    return _ring(centre, r, r, centre[2] + dz, focal, steps=steps)


def spiral_in(bbox_min, bbox_max, focal=DEFAULT_FOCAL, steps=12):
    """One turn around the subject while closing in: from 1.6x the fit distance down to 0.8x, descending a little."""
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    out = []
    for i in range(steps + 1):
        t = i / steps
        a = 2 * math.pi * t
        r = d * (1.6 - 0.8 * t)
        z = centre[2] + size * (0.6 - 0.35 * t)
        out.append(_wp((centre[0] + r * math.sin(a), centre[1] - r * math.cos(a), z), centre, focal))
    return out


# Ellipses -------------------------------------------------------------------

def ellipse_1(bbox_min, bbox_max, focal=DEFAULT_FOCAL, steps=12):
    """A wide 2:1 ellipse around the subject, twice as wide as deep, at a constant height."""
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    return _ring(centre, 1.7 * d, 0.85 * d, centre[2] + 0.3 * size, focal, steps=steps)


def ellipse_2(bbox_min, bbox_max, focal=DEFAULT_FOCAL, steps=12):
    """A tilted ellipse: low in front of the subject, rising over the far side, back down to the start."""
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    return _ring(centre, 1.3 * d, 0.9 * d, centre[2] + 0.1 * size, focal, steps=steps, rise=1.1 * size)


def ellipse_3(bbox_min, bbox_max, focal=DEFAULT_FOCAL, steps=12):
    """A tight ellipse close to the subject, longer in depth, so the back is revealed slowly."""
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    return _ring(centre, 0.6 * d, 0.95 * d, centre[2] + 0.25 * size, focal, steps=steps)


# Dolly, truck, pedestal, zoom -------------------------------------------------

def dolly_in(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    """Straight in along the view axis, from far away up to the subject."""
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    height = centre[2] + 0.25 * size
    return [_wp((centre[0], centre[1] - 2.2 * d, height), centre, focal), _wp((centre[0], centre[1] - 0.8 * d, height), centre, focal)]


def dolly_out(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    """Straight out along the view axis, from the subject to a wide reveal."""
    return list(reversed(dolly_in(bbox_min, bbox_max, focal)))


push_in = dolly_in    # names used by 0.6.0 scenes and the text parser
pull_back = dolly_out


def _truck(bbox_min, bbox_max, focal, direction):
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    height = centre[2] + 0.2 * size
    xs = (0.7 * d, 0.0, -0.7 * d) if direction < 0 else (-0.7 * d, 0.0, 0.7 * d)
    return [_wp((centre[0] + x, centre[1] - d, height), centre, focal) for x in xs]


def truck_left(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    """Lateral move to the left in front of the subject, at a constant depth, keeping the subject framed."""
    return _truck(bbox_min, bbox_max, focal, -1)


def truck_right(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    """Lateral move to the right in front of the subject, at a constant depth, keeping the subject framed."""
    return _truck(bbox_min, bbox_max, focal, +1)


def _pedestal(bbox_min, bbox_max, focal, direction):
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    zs = (centre[2] - 0.4 * size, centre[2] + 0.25 * size, centre[2] + 0.9 * size)
    if direction < 0:
        zs = tuple(reversed(zs))
    return [_wp((centre[0], centre[1] - d, z), centre, focal) for z in zs]


def pedestal_up(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    """Vertical move up in front of the subject, from below its centre to above it."""
    return _pedestal(bbox_min, bbox_max, focal, +1)


def pedestal_down(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    """Vertical move down in front of the subject, from above it to below its centre."""
    return _pedestal(bbox_min, bbox_max, focal, -1)


def zoom_in(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    """The camera does not move: the lens goes from wide (half the focal) to the requested focal length."""
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    position = (centre[0], centre[1] - 1.1 * d, centre[2] + 0.25 * size)
    return [Waypoint(position, look_at=centre, focal=max(8.0, float(focal) / 2.0)), Waypoint(position, look_at=centre, focal=float(focal))]


# Crane, arcs, top down --------------------------------------------------------

def crane(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    """Low in front, rising to look down on the subject."""
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    return [_wp((centre[0], centre[1] - d, centre[2] - 0.2 * size), centre, focal),
            _wp((centre[0], centre[1] - 0.9 * d, centre[2] + 1.2 * size), centre, focal)]


def _arc(bbox_min, bbox_max, focal, direction, steps=4):
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    dz = 0.3 * size
    r = _horizontal_radius(d, dz)
    return _ring(centre, r, r, centre[2] + dz, focal, steps=steps, sweep=direction * math.pi / 2.0)


def arc_left(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    """A quarter turn from the front to the subject's left side."""
    return _arc(bbox_min, bbox_max, focal, -1)


def arc_right(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    """A quarter turn from the front to the subject's right side."""
    return _arc(bbox_min, bbox_max, focal, +1)


def top_down(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    """From high above the subject, descending towards it, looking down."""
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    return [_wp((centre[0], centre[1] - 0.15 * d, centre[2] + 2.2 * d), centre, focal),
            _wp((centre[0], centre[1] - 0.25 * d, centre[2] + 1.4 * d), centre, focal),
            _wp((centre[0], centre[1] - 0.35 * d, centre[2] + 0.9 * d), centre, focal)]


# Other ----------------------------------------------------------------------

def pan(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    """Left to right in front of the subject, wider than a truck, keeping it framed."""
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    height = centre[2] + 0.2 * size
    return [_wp((centre[0] - 0.9 * d, centre[1] - d, height), centre, focal),
            _wp((centre[0], centre[1] - d, height), centre, focal),
            _wp((centre[0] + 0.9 * d, centre[1] - d, height), centre, focal)]


def flyover(bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    """High and far, swooping down towards the subject."""
    centre, size, diagonal = _box(bbox_min, bbox_max)
    d = fit_distance(diagonal, focal)
    return [_wp((centre[0] - 0.6 * d, centre[1] - 2.0 * d, centre[2] + 1.5 * size), centre, focal),
            _wp((centre[0], centre[1] - 1.3 * d, centre[2] + 0.9 * size), centre, focal),
            _wp((centre[0] + 0.3 * d, centre[1] - 0.8 * d, centre[2] + 0.4 * size), centre, focal)]


PRESETS = {
    "orbit": ("Orbit", "A full turn around the subject, back to the start", orbit),
    "orbit_high": ("Orbit high", "A full turn from above, looking down, back to the start", orbit_high),
    "orbit_low": ("Orbit low", "A full turn from a hero angle below the centre, back to the start", orbit_low),
    "spiral_in": ("Spiral in", "One turn around the subject while closing in", spiral_in),
    "ellipse_1": ("Ellipse 1", "A wide 2:1 ellipse around the subject, back to the start", ellipse_1),
    "ellipse_2": ("Ellipse 2", "A tilted ellipse rising over the far side, back to the start", ellipse_2),
    "ellipse_3": ("Ellipse 3", "A tight ellipse close to the subject, slow reveal of the back", ellipse_3),
    "dolly_in": ("Dolly in", "Straight in, from far away up to the subject", dolly_in),
    "dolly_out": ("Dolly out", "Straight out, from the subject to a wide reveal", dolly_out),
    "truck_left": ("Truck left", "Lateral move to the left, subject kept in frame", truck_left),
    "truck_right": ("Truck right", "Lateral move to the right, subject kept in frame", truck_right),
    "pedestal_up": ("Pedestal up", "Vertical move up in front of the subject", pedestal_up),
    "pedestal_down": ("Pedestal down", "Vertical move down in front of the subject", pedestal_down),
    "zoom_in": ("Zoom in", "Fixed camera, lens from wide to the chosen focal length", zoom_in),
    "crane": ("Crane", "Low in front, rising to look down on the subject", crane),
    "arc_left": ("Arc left", "A quarter turn from the front to the left side", arc_left),
    "arc_right": ("Arc right", "A quarter turn from the front to the right side", arc_right),
    "top_down": ("Top down", "From high above, descending towards the subject", top_down),
    "pan": ("Pan", "Left to right in front of the subject", pan),
    "flyover": ("Flyover", "High and far, swooping down towards the subject", flyover),
}
PRESET_ALIASES = {"push_in": "dolly_in", "pull_back": "dolly_out"}
PRESET_GROUPS = (
    ("Orbits", ("orbit", "orbit_high", "orbit_low", "spiral_in")),
    ("Ellipses", ("ellipse_1", "ellipse_2", "ellipse_3")),
    ("Dolly & truck", ("dolly_in", "dolly_out", "truck_left", "truck_right", "pedestal_up", "pedestal_down", "zoom_in")),
    ("Crane & arcs", ("crane", "arc_left", "arc_right", "top_down")),
    ("Other", ("pan", "flyover")),
)
CLOSED_PRESETS = ("orbit", "orbit_high", "orbit_low", "ellipse_1", "ellipse_2", "ellipse_3")
DEFAULT_PRESET = "orbit"


def resolve_preset(name):
    """Canonical preset name: aliases from 0.6.0 (push_in, pull_back) map to the dolly moves, unknown names to the default."""
    name = PRESET_ALIASES.get(name, name)
    return name if name in PRESETS else DEFAULT_PRESET


def preset_waypoints(name, bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    label, description, fn = PRESETS[resolve_preset(name)]
    return fn(bbox_min, bbox_max, focal)


def is_closed(name):
    """True for moves that end where they start (orbits, ellipses)."""
    return resolve_preset(name) in CLOSED_PRESETS


def _same_spot(a, b):
    return distance(a.position, b.position) < 1e-9


def marker_waypoints(name, bbox_min, bbox_max, focal=DEFAULT_FOCAL):
    """The waypoints to place as editable markers: a closed move loses its closing duplicate (the loop is closed
    again at build time with `close_loop`), so an orbit gives 12 markers, not 13."""
    waypoints = preset_waypoints(name, bbox_min, bbox_max, focal)
    if is_closed(name) and len(waypoints) > 1 and _same_spot(waypoints[0], waypoints[-1]):
        return waypoints[:-1]
    return waypoints


def close_loop(waypoints):
    """Append a copy of the first waypoint (same position, aim, focal, no hold) unless the path already ends there."""
    waypoints = list(waypoints)
    if len(waypoints) < 2 or _same_spot(waypoints[0], waypoints[-1]):
        return waypoints
    first = waypoints[0]
    waypoints.append(Waypoint(first.position, rotation_euler=first.rotation_euler, look_at=first.look_at, focal=first.focal, hold=0.0))
    return waypoints


def preset_items():
    """(name, label, description) in group order, with None between groups (Blender draws None as a menu separator)."""
    items = []
    for gi, (_group, names) in enumerate(PRESET_GROUPS):
        if gi:
            items.append(None)
        for name in names:
            label, description, _fn = PRESETS[name]
            items.append((name, label, description))
    return items


# -- text to plan ---------------------------------------------------------------

_PRESET_PATTERNS = (
    ("ellipse_3", r"\bellip(?:se|sis|tical)\w*\s*(?:3|three|iii)\b"),
    ("ellipse_2", r"\bellip(?:se|sis|tical)\w*\s*(?:2|two|ii)\b"),
    ("ellipse_1", r"\bellip(?:se|sis|tical|soid)\w*"),
    ("spiral_in", r"\bspiral(?:s|ing|ling)?\b"),
    ("zoom_in", r"\bzoom(?:s|ing)?\s*in\b"),
    ("dolly_out", r"\b(pulls?(?:ing)?\s*(?:back|out|away)|zoom(?:s|ing)?\s*out|dolly\s*(?:out|back)|away|reveal(?:s|ing)?|back\s*off)\b"),
    ("dolly_in", r"\b(push(?:es|ing)?(?:\s*in)?|closer|close[- ]?up|dolly(?:\s*in)?|approach(?:es|ing)?|move\s*in)\b"),
    ("truck_left", r"\b(truck(?:s|ing)?|slide(?:s|ing)?|crab(?:s|bing)?)\s*(?:to\s+the\s+)?left\b"),
    ("truck_right", r"\b(truck(?:s|ing)?|slide(?:s|ing)?|crab(?:s|bing)?)\s*(?:to\s+the\s+)?right\b"),
    ("pedestal_up", r"\b(pedestal|boom)\s*up\b"),
    ("pedestal_down", r"\b(pedestal|boom)\s*down\b"),
    ("arc_left", r"\barc(?:s|ing)?\s*(?:to\s+the\s+)?left\b"),
    ("arc_right", r"\barc(?:s|ing)?\s*(?:to\s+the\s+)?right\b"),
    ("top_down", r"\b(top[- ]?down|overhead|from\s+above|bird'?s?[- ]?eye|straight\s+down)\b"),
    ("orbit_low", r"\b(low[- ]angle|hero\s+angle|from\s+below|worm'?s?[- ]?eye)\b"),
    ("orbit_high", r"\b(high[- ]angle|elevated|looking\s+down\s+(?:while\s+)?(?:orbit|circl|turn))\b"),
    ("crane", r"\b(crane|ris(?:e|es|ing)|lift(?:s|ing)?|ascend(?:s|ing)?|up\s+and\s+over|tilt(?:s|ing)?\s*down)\b"),
    ("flyover", r"\b(fly(?:ing|over|by)?|fly-?over|drone|aerial|swoop(?:s|ing)?|over|bird)\b"),
    ("pan", r"\b(pan(?:s|ning)?|left\s+to\s+right|right\s+to\s+left|sweep(?:s|ing)?|track(?:s|ing)?\s*(?:along|past)?|sideways|lateral)\b"),
    ("orbit", r"\b(orbit(?:s|ing)?|turntable|around|circle(?:s|ing)?|spin(?:s|ning)?|revolv(?:e|es|ing)|360|rotate(?:s)?|turn(?:s)?\s*around)\b"),
)
_DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)\b", re.I)
_FOCAL = re.compile(r"(\d+(?:\.\d+)?)\s*mm\b", re.I)


def plan_from_text(text):
    """A deterministic reading of a shot description: {"preset", "duration", "focal"}. Unknown text keeps the defaults."""
    text = (text or "").strip().lower()
    # one move per path: when several are named ("dolly in and then orbit"), the one written first wins, so the
    # result is predictable from what the user typed; a more specific pattern breaks a tie at the same position.
    preset = DEFAULT_PRESET
    best_start = None
    for name, pattern in _PRESET_PATTERNS:
        match = re.search(pattern, text)
        if match and (best_start is None or match.start() < best_start):
            best_start, preset = match.start(), name
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
