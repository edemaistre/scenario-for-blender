# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
import datetime as dt

from scenario.core import config


def test_env_overrides_prefs():
    creds = config.resolve_credentials("pref_key", "pref_secret", environ={"SCENARIO_API_KEY": " env_key ", "SCENARIO_API_SECRET": "env_secret"})
    assert creds.key == "env_key" and creds.secret == "env_secret" and creds.valid


def test_prefs_used_when_env_missing_and_invalid_when_empty():
    assert config.resolve_credentials("k", "s", environ={}).valid
    assert not config.resolve_credentials("", "s", environ={}).valid
    assert not config.resolve_credentials(None, None, environ={}).valid


def test_load_dotenv(tmp_path):
    p = tmp_path / ".env.local"
    p.write_text("# comment\nSCENARIO_API_KEY=abc\nSCENARIO_API_SECRET='quoted'\nEMPTY=\n")
    assert config.load_dotenv(p) == {"SCENARIO_API_KEY": "abc", "SCENARIO_API_SECRET": "quoted", "EMPTY": ""}
    assert config.load_dotenv(tmp_path / "missing") == {}


def test_paths_layout(tmp_path):
    paths = config.Paths(state_dir=tmp_path / "state", cache_dir=tmp_path / "cache", output_dir=tmp_path / "out")
    assert paths.models_cache_dir == tmp_path / "cache" / "models"
    assert paths.registry_file == tmp_path / "state" / "jobs.json"
    when = dt.datetime(2026, 8, 28, 9, 30, 5)
    assert paths.output_for("image", when) == tmp_path / "out" / "images" / "20260828"
    assert paths.output_for("3d", when) == tmp_path / "out" / "3d" / "20260828"
    assert paths.output_for("material", when) == tmp_path / "out" / "materials" / "20260828"
    assert paths.output_for("weird", when) == tmp_path / "out" / "other" / "20260828"
    today = f"{dt.datetime.now():%Y%m%d}"
    assert paths.output_for("video").name == today


def test_ext_for_mime():
    assert config.ext_for_mime("image/png") == "png"
    assert config.ext_for_mime("model/gltf-binary") == "glb"
    assert config.ext_for_mime("video/mp4") == "mp4"
    assert config.ext_for_mime("application/x-unknown") == "bin"
    assert config.ext_for_mime(None) == "bin"


def test_output_filename_is_readable_and_unique():
    when = dt.datetime(2026, 8, 28, 9, 30, 5)
    name = config.output_filename("image", "model_patina-material", "job_KWxxsnSdVXDFZRMsoCvLTmKY", 2, "png", when=when)
    assert name == "20260828_093005_patina-material_soCvLTmKY_02.png"
    assert config.slug("model_Google Gemini 3.1 🍌", limit=12) == "google-gemin"
