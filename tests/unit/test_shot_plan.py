# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import math

import pytest

from scenario.core.scene import shot_plan as sp

BOX = ((-1.0, -0.5, 0.0), (1.0, 0.5, 2.0))
CENTRE = (0.0, 0.0, 1.0)
DIAGONAL = math.sqrt(2 ** 2 + 1 ** 2 + 2 ** 2)


def _frames(keys):
    return [f for f, _ in keys]


def _dist(wp):
    return sp.distance(wp.position, CENTRE)


# -- schedule ------------------------------------------------------------------

def test_schedule_starts_at_one_ends_at_duration_and_is_monotonic():
    wps = [sp.Waypoint((0, 0, 0)), sp.Waypoint((1, 0, 0)), sp.Waypoint((3, 0, 0))]
    keys = sp.frame_schedule(wps, 6.0, 24)
    assert keys[0] == (1, 0)
    assert keys[-1] == (144, 2)
    frames = _frames(keys)
    assert frames == sorted(frames) and len(set(frames)) == len(frames)
    assert [i for _, i in keys] == [0, 1, 2]
    # the longer segment (2 units) gets about twice the frames of the short one (1 unit)
    seg1, seg2 = frames[1] - frames[0], frames[2] - frames[1]
    assert abs(seg2 / seg1 - 2.0) < 0.1


def test_schedule_holds_add_a_second_key_and_zero_length_segments_still_move():
    wps = [sp.Waypoint((0, 0, 0), hold=1.0), sp.Waypoint((0, 0, 0)), sp.Waypoint((4, 0, 0), hold=0.5)]
    keys = sp.frame_schedule(wps, 8.0, 24)
    indices = [i for _, i in keys]
    assert indices == [0, 0, 1, 2, 2]
    frames = _frames(keys)
    assert frames[1] - frames[0] == 24  # one second of hold
    assert frames[2] > frames[1]  # the zero-length segment still takes time
    assert frames[-1] == 192


def test_schedule_single_waypoint_and_empty():
    assert sp.frame_schedule([sp.Waypoint((0, 0, 0))], 2.0, 30) == [(1, 0), (60, 0)]
    assert sp.frame_schedule([], 2.0, 30) == []


def test_schedule_scales_excessive_holds_down():
    wps = [sp.Waypoint((0, 0, 0), hold=10.0), sp.Waypoint((1, 0, 0), hold=10.0)]
    keys = sp.frame_schedule(wps, 4.0, 24)
    assert keys[0] == (1, 0) and keys[-1] == (96, 1)
    assert _frames(keys) == sorted(_frames(keys))


def test_schedule_of_a_closed_orbit_is_even_and_ends_on_the_closing_waypoint():
    wps = sp.orbit(*BOX, focal=35.0)
    keys = sp.frame_schedule(wps, 12.0, 24)
    assert len(keys) == len(wps) == 13
    assert keys[0] == (1, 0) and keys[-1] == (288, 12)
    gaps = [b - a for (a, _), (b, _) in zip(keys, keys[1:])]
    assert max(gaps) - min(gaps) <= 1  # equal segments, equal time (rounding aside)


# -- geometry helpers -----------------------------------------------------------

def test_fit_distance_grows_with_focal_and_size():
    assert sp.fit_distance(2.0, 50.0) > sp.fit_distance(2.0, 24.0)
    assert sp.fit_distance(4.0, 35.0) > sp.fit_distance(2.0, 35.0)
    half_fov = math.atan(18.0 / 35.0)
    assert sp.fit_distance(2.0, 35.0) == pytest.approx(2.0 / (2 * 0.7 * math.tan(half_fov)))


# -- the library ---------------------------------------------------------------

def test_library_has_about_twenty_grouped_presets_and_a_default():
    assert len(sp.PRESETS) == 20
    grouped = [name for _group, names in sp.PRESET_GROUPS for name in names]
    assert sorted(grouped) == sorted(sp.PRESETS)  # every preset in exactly one group
    assert len(grouped) == len(set(grouped))
    assert sp.DEFAULT_PRESET in sp.PRESETS
    items = sp.preset_items()
    assert items.count(None) == len(sp.PRESET_GROUPS) - 1
    assert [i for i in items if i is not None][0][0] == "orbit"
    assert all(len(i) == 3 for i in items if i is not None)


@pytest.mark.parametrize("name", list(sp.PRESETS))
def test_presets_look_at_the_centre_and_stay_at_a_sensible_distance(name):
    wps = sp.preset_waypoints(name, *BOX, focal=35.0)
    d = sp.fit_distance(DIAGONAL, 35.0)
    assert len(wps) >= 2
    for wp in wps:
        assert wp.look_at == CENTRE
        assert all(math.isfinite(v) for v in wp.position)
        assert 0.5 * d <= _dist(wp) <= 3.0 * d
        if name != "zoom_in":
            assert wp.focal == 35.0


@pytest.mark.parametrize("name", sp.CLOSED_PRESETS)
def test_closed_moves_return_exactly_to_the_start(name):
    wps = sp.preset_waypoints(name, *BOX, focal=35.0)
    assert wps[0].position == wps[-1].position
    assert wps[0].look_at == wps[-1].look_at
    assert len(wps) == 13
    # the loop visits the far side: some waypoint sits behind the subject (positive Y)
    assert any(wp.position[1] > CENTRE[1] for wp in wps)


def test_orbits_keep_their_distance_and_height():
    for name in ("orbit", "orbit_high", "orbit_low"):
        wps = sp.preset_waypoints(name, *BOX)
        dists = [_dist(wp) for wp in wps]
        assert max(dists) - min(dists) < 1e-6, name
        assert len({round(wp.position[2], 6) for wp in wps}) == 1, name
    assert sp.orbit_high(*BOX)[0].position[2] > sp.orbit(*BOX)[0].position[2] > sp.orbit_low(*BOX)[0].position[2]
    assert sp.orbit_low(*BOX)[0].position[2] < CENTRE[2]


def test_ellipses_have_the_expected_shapes():
    e1 = sp.ellipse_1(*BOX)
    widths = [abs(wp.position[0] - CENTRE[0]) for wp in e1]
    depths = [abs(wp.position[1] - CENTRE[1]) for wp in e1]
    assert max(widths) == pytest.approx(2.0 * max(depths), rel=1e-6)  # 2:1
    assert len({round(wp.position[2], 6) for wp in e1}) == 1
    e2 = sp.ellipse_2(*BOX)
    front, back = e2[0].position[2], e2[6].position[2]
    assert back > front  # rises on the far side
    assert e2[0].position[2] == e2[-1].position[2]
    e3 = sp.ellipse_3(*BOX)
    assert max(_dist(wp) for wp in e3) < max(_dist(wp) for wp in e1)  # tight
    depths3 = [abs(wp.position[1] - CENTRE[1]) for wp in e3]
    widths3 = [abs(wp.position[0] - CENTRE[0]) for wp in e3]
    assert max(depths3) > max(widths3)  # longer in depth


def test_spiral_in_turns_once_and_ends_closer():
    wps = sp.spiral_in(*BOX)
    assert len(wps) == 13
    assert _dist(wps[-1]) < 0.6 * _dist(wps[0])
    assert wps[0].position != wps[-1].position
    # same angle at start and end (both in front of the subject: x at the centre, negative Y side)
    assert wps[0].position[0] == pytest.approx(CENTRE[0]) and wps[-1].position[0] == pytest.approx(CENTRE[0])
    assert wps[0].position[1] < CENTRE[1] and wps[-1].position[1] < CENTRE[1]


def test_dolly_moves_and_their_aliases():
    a, b = sp.dolly_in(*BOX)
    assert _dist(a) > _dist(b)
    assert [w.position for w in sp.dolly_out(*BOX)] == [b.position, a.position]
    assert sp.push_in is sp.dolly_in and sp.pull_back is sp.dolly_out
    assert sp.resolve_preset("push_in") == "dolly_in" and sp.resolve_preset("pull_back") == "dolly_out"
    assert [w.position for w in sp.preset_waypoints("push_in", *BOX)] == [w.position for w in sp.dolly_in(*BOX)]


def test_truck_and_pedestal_move_along_one_axis():
    left = sp.truck_left(*BOX)
    right = sp.truck_right(*BOX)
    assert left[0].position[0] > left[-1].position[0]
    assert right[0].position[0] < right[-1].position[0]
    assert len({round(wp.position[1], 6) for wp in left}) == 1  # constant depth
    assert len({round(wp.position[2], 6) for wp in left}) == 1
    up = sp.pedestal_up(*BOX)
    down = sp.pedestal_down(*BOX)
    assert up[0].position[2] < up[-1].position[2]
    assert [w.position for w in down] == [w.position for w in reversed(up)]
    assert len({(round(wp.position[0], 6), round(wp.position[1], 6)) for wp in up}) == 1


def test_zoom_in_changes_focal_only():
    wps = sp.zoom_in(*BOX, focal=50.0)
    assert len(wps) == 2
    assert wps[0].position == wps[1].position
    assert wps[0].focal == 25.0 and wps[1].focal == 50.0
    assert sp.zoom_in(*BOX, focal=12.0)[0].focal == 8.0  # never below 8 mm


def test_crane_arcs_top_down_and_flyover():
    low, high = sp.crane(*BOX)
    assert high.position[2] > low.position[2]
    left, right = sp.arc_left(*BOX), sp.arc_right(*BOX)
    assert len(left) == len(right) == 5
    assert left[0].position == right[0].position  # both start in front
    assert left[-1].position[0] < CENTRE[0] < right[-1].position[0]
    assert left[-1].position[1] == pytest.approx(CENTRE[1], abs=1e-6)  # a quarter turn ends beside the subject
    top = sp.top_down(*BOX)
    assert top[0].position[2] > top[-1].position[2] > CENTRE[2]
    fly = sp.flyover(*BOX)
    assert fly[0].position[2] > fly[-1].position[2]


def test_unknown_preset_falls_back_to_orbit():
    assert sp.resolve_preset("nope") == "orbit"
    assert [w.position for w in sp.preset_waypoints("nope", *BOX)] == [w.position for w in sp.orbit(*BOX)]


# -- text parser ----------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("slow orbit around the robot, 10s at 50mm", {"preset": "orbit", "duration": 15.0, "focal": 50.0}),
    ("push in closer on the teapot", {"preset": "dolly_in", "duration": 6.0, "focal": 35.0}),
    ("dolly in on the hero", {"preset": "dolly_in", "duration": 6.0, "focal": 35.0}),
    ("pull back to reveal the whole city", {"preset": "dolly_out", "duration": 6.0, "focal": 35.0}),
    ("dolly out, 5 s", {"preset": "dolly_out", "duration": 5.0, "focal": 35.0}),
    ("fast drone flyover of the village", {"preset": "flyover", "duration": 3.6, "focal": 35.0}),
    ("pan left to right, 4 seconds", {"preset": "pan", "duration": 4.0, "focal": 35.0}),
    ("crane up over the castle, wide", {"preset": "crane", "duration": 6.0, "focal": 24.0}),
    ("zoom in fast on a tight lens", {"preset": "zoom_in", "duration": 3.6, "focal": 85.0}),
    ("ellipse around the car", {"preset": "ellipse_1", "duration": 6.0, "focal": 35.0}),
    ("ellipse 2, 8s", {"preset": "ellipse_2", "duration": 8.0, "focal": 35.0}),
    ("slow elliptical 3 move", {"preset": "ellipse_3", "duration": 9.0, "focal": 35.0}),
    ("truck left along the facade", {"preset": "truck_left", "duration": 6.0, "focal": 35.0}),
    ("truck to the right", {"preset": "truck_right", "duration": 6.0, "focal": 35.0}),
    ("pedestal up slowly", {"preset": "pedestal_up", "duration": 9.0, "focal": 35.0}),
    ("boom down", {"preset": "pedestal_down", "duration": 6.0, "focal": 35.0}),
    ("arc left around the statue", {"preset": "arc_left", "duration": 6.0, "focal": 35.0}),
    ("arc right", {"preset": "arc_right", "duration": 6.0, "focal": 35.0}),
    ("spiral in on the tower", {"preset": "spiral_in", "duration": 6.0, "focal": 35.0}),
    ("top down view descending", {"preset": "top_down", "duration": 6.0, "focal": 35.0}),
    ("overhead shot", {"preset": "top_down", "duration": 6.0, "focal": 35.0}),
    ("low angle orbit, hero shot", {"preset": "orbit_low", "duration": 6.0, "focal": 35.0}),
    ("high angle turn around", {"preset": "orbit_high", "duration": 6.0, "focal": 35.0}),
    ("", {"preset": "orbit", "duration": 6.0, "focal": 35.0}),
    ("a 500 sec epic", {"preset": "orbit", "duration": 60.0, "focal": 35.0}),
    # one move per path: when several are named, the first written wins (predictable from the text)
    ("dolly in and then orbit", {"preset": "dolly_in", "duration": 6.0, "focal": 35.0}),
    ("orbit then dolly in closer", {"preset": "orbit", "duration": 6.0, "focal": 35.0}),
    # a hold/pause is read out and does not become the move duration
    ("dolly in 8 s, hold 2 s", {"preset": "dolly_in", "duration": 8.0, "focal": 35.0, "hold": 2.0}),
    ("orbit, stay for 3 seconds", {"preset": "orbit", "duration": 6.0, "focal": 35.0, "hold": 3.0}),
    ("push in and pause 1.5s", {"preset": "dolly_in", "duration": 6.0, "focal": 35.0, "hold": 1.5}),
])
def test_plan_from_text(text, expected):
    expected.setdefault("hold", 0.0)  # existing cases have no hold
    assert sp.plan_from_text(text) == expected


def test_is_closed_marker_waypoints_and_close_loop():
    lo, hi = (-1.0, -1.0, 0.0), (1.0, 1.0, 2.0)
    for name in sp.CLOSED_PRESETS:
        assert sp.is_closed(name)
        full = sp.preset_waypoints(name, lo, hi)
        markers = sp.marker_waypoints(name, lo, hi)
        assert len(markers) == len(full) - 1, name  # the closing duplicate is not a marker
        assert sp.distance(markers[0].position, markers[-1].position) > 1e-6
        closed = sp.close_loop(markers)
        assert len(closed) == len(markers) + 1
        assert closed[-1].position == closed[0].position and closed[-1].focal == closed[0].focal and closed[-1].hold == 0.0
        assert sp.close_loop(closed) == closed  # already closed: nothing appended
    assert not sp.is_closed("dolly_in") and not sp.is_closed("push_in")
    assert len(sp.marker_waypoints("dolly_in", lo, hi)) == len(sp.preset_waypoints("dolly_in", lo, hi))
    assert sp.close_loop([sp.Waypoint((0, 0, 0))]) == [sp.Waypoint((0, 0, 0))]
