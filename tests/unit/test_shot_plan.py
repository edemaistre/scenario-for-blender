# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import math

import pytest

from scenario.core.scene import shot_plan as sp

BOX = ((-1.0, -0.5, 0.0), (1.0, 0.5, 2.0))
CENTRE = (0.0, 0.0, 1.0)


def _frames(keys):
    return [f for f, _ in keys]


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


def test_fit_distance_grows_with_focal_and_size():
    assert sp.fit_distance(2.0, 50.0) > sp.fit_distance(2.0, 24.0)
    assert sp.fit_distance(4.0, 35.0) > sp.fit_distance(2.0, 35.0)
    half_fov = math.atan(18.0 / 35.0)
    assert sp.fit_distance(2.0, 35.0) == pytest.approx(2.0 / (2 * 0.7 * math.tan(half_fov)))


@pytest.mark.parametrize("name", list(sp.PRESETS))
def test_presets_look_at_the_centre_and_stay_at_a_sensible_distance(name):
    wps = sp.preset_waypoints(name, *BOX, focal=35.0)
    d = sp.fit_distance(math.sqrt(2 ** 2 + 1 ** 2 + 2 ** 2), 35.0)
    assert len(wps) >= 2
    for wp in wps:
        assert wp.look_at == CENTRE
        assert wp.focal == 35.0
        assert all(math.isfinite(v) for v in wp.position)
        assert 0.5 * d <= sp.distance(wp.position, CENTRE) <= 3.0 * d


def test_orbit_is_closed_and_keeps_its_distance():
    wps = sp.orbit(*BOX, focal=35.0)
    assert len(wps) == 9
    assert wps[0].position == wps[-1].position
    dists = [sp.distance(wp.position, CENTRE) for wp in wps]
    assert max(dists) - min(dists) < 1e-6
    assert len({round(wp.position[2], 6) for wp in wps}) == 1


def test_push_in_moves_closer_and_pull_back_is_its_reverse():
    a, b = sp.push_in(*BOX)
    assert sp.distance(a.position, CENTRE) > sp.distance(b.position, CENTRE)
    assert [w.position for w in sp.pull_back(*BOX)] == [b.position, a.position]


def test_crane_rises_and_flyover_descends():
    low, high = sp.crane(*BOX)
    assert high.position[2] > low.position[2]
    fly = sp.flyover(*BOX)
    assert fly[0].position[2] > fly[-1].position[2]


def test_unknown_preset_falls_back_to_orbit():
    assert [w.position for w in sp.preset_waypoints("nope", *BOX)] == [w.position for w in sp.orbit(*BOX)]


@pytest.mark.parametrize("text,expected", [
    ("slow orbit around the robot, 10s at 50mm", {"preset": "orbit", "duration": 15.0, "focal": 50.0}),
    ("push in closer on the teapot", {"preset": "push_in", "duration": 6.0, "focal": 35.0}),
    ("pull back to reveal the whole city", {"preset": "pull_back", "duration": 6.0, "focal": 35.0}),
    ("fast drone flyover of the village", {"preset": "flyover", "duration": 3.6, "focal": 35.0}),
    ("pan left to right, 4 seconds", {"preset": "pan", "duration": 4.0, "focal": 35.0}),
    ("crane up over the castle, wide", {"preset": "crane", "duration": 6.0, "focal": 24.0}),
    ("zoom in fast on a tight lens", {"preset": "push_in", "duration": 3.6, "focal": 85.0}),
    ("", {"preset": "orbit", "duration": 6.0, "focal": 35.0}),
    ("a 500 sec epic", {"preset": "orbit", "duration": 60.0, "focal": 35.0}),
])
def test_plan_from_text(text, expected):
    assert sp.plan_from_text(text) == expected
