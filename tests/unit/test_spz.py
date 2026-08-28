# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import gzip

import pytest

from scenario.core.scene import spz


def test_roundtrip_positions_colors_alphas_scales(tmp_path):
    path = tmp_path / "cloud.spz"
    positions = [(0.0, 0.0, 0.0), (1.5, -2.25, 3.0), (-100.125, 50.5, 0.75)]
    colors = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.2, 0.4, 0.6)]
    spz.write_spz(path, positions, colors, alphas=[1.0, 0.5, 0.0], scales=[0.01, 0.1, 1.0])
    data = spz.read_spz(path)
    assert data["count"] == 3 and data["kept"] == 3 and data["step"] == 1 and data["version"] == 2
    for got, want in zip(data["positions"], positions):
        assert all(abs(a - b) < 1e-3 for a, b in zip(got, want))
    for got, want in zip(data["colors"], colors):
        assert all(abs(a - b) < 0.02 for a, b in zip(got, want))
    assert [round(a, 2) for a in data["alphas"]] == [1.0, 0.5, 0.0]
    assert all(abs(a - b) / b < 0.1 for a, b in zip(data["scales"], [0.01, 0.1, 1.0]))


def test_subsampling_keeps_every_nth_point(tmp_path):
    path = tmp_path / "many.spz"
    positions = [(float(i), 0.0, 0.0) for i in range(100)]
    spz.write_spz(path, positions, [(0.5, 0.5, 0.5)] * 100)
    data = spz.read_spz(path, max_points=25)
    assert data["count"] == 100 and data["kept"] == 25 and data["step"] == 4
    assert data["positions"][1][0] == pytest.approx(4.0, abs=1e-3)


def test_axis_conversion_and_bad_files(tmp_path):
    assert spz.y_up_to_z_up((1.0, 2.0, 3.0)) == (1.0, -3.0, 2.0)
    bad = tmp_path / "bad.spz"
    with gzip.open(bad, "wb") as handle:
        handle.write(b"not a splat file at all")
    with pytest.raises(spz.SpzError):
        spz.read_spz(bad)


def test_sniff_recognises_a_splat_saved_as_bin(tmp_path):
    path = tmp_path / "world.bin"
    spz.write_spz(path, [(0.0, 0.0, 0.0)], [(0.5, 0.5, 0.5)])
    assert spz.sniff_spz(path)
    (tmp_path / "plain.bin").write_bytes(b"\x00\x01\x02\x03")
    assert not spz.sniff_spz(tmp_path / "plain.bin")
    from scenario.core.scene import placement
    assert placement.importer_for(path) == "spz"
    assert placement.importer_for(tmp_path / "plain.bin") is None
