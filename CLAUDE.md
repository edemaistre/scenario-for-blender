# Scenario for Blender (project pointer)

Read `README.md` first, then `docs/superpowers/specs/2026-08-28-scenario-for-blender-design.md` (the approved v1 design).

**State (2026-08-28, evening):** v0.6.0 on `main`: Render Image / Render Video lanes with Prompt Spark (`POST /generate/prompt`) and role-explicit prompts (`core/scene/render_prompt.py`), camera path planner (`shot_planner.py`, markers + presets + MCP `camera_path`), Edit 3D lane (mesh export to GLB, result next to the source), model picker dialog, composer text selection, four panels (Scenario / Jobs / Generations / Agents), dated output folders. Render-to-real archived in `archive/0.5.x/`. Versioning rule applied: `versions/` for docs, `archive/` for retired code, one zip per version in `dist/`. Previous state: v0.5.2 (0.5.0 + the 3D import fixes + retrying downloads). User docs: `docs/USER_GUIDE.md` and `docs/user-guide.html` (published artifact https://claude.ai/code/artifact/6d24a64f-5a31-4cd8-9fc9-7decd743e154, republish from this file path to keep the URL), `CHANGELOG.md` in Keep-a-Changelog form (previous form in `versions/`). P0 to P4 delivered: Image, Materials via Patina, 3D import at cursor, Generations history, Video lane with captures, Render-to-real, local MCP server (16 tools), floating gpu/blf composer, extension repository build; 76 unit + 54 headless tests green; four real smokes OK; 29 of 31 review findings fixed (open ones in BUGS.md). Next: v2 backlog in the spec section 4 (skyboxes, mesh utilities, rigging/motion, LoRAs, Workflows, OAuth), and the BUGS.md items. Research notes in `research/` (clean-room behavioural specs of [redacted] 1.5.47 + Scenario API/model maps + live probes). Dev credentials in git-ignored `.env.local` (workspace "Blender Plugin Tests", ~$30 test cap, never print them).

Hard rules for this folder:
- Clean-room: never copy code from the [redacted] source in `~/Developer/scratch/2026-08-28 [redacted] Blender Plugin 1.5.47/`; behaviour only.
- Pure Python, no wheels; `bpy` on the main thread only; GPL-3.0-or-later SPDX header on every source file; no em dashes anywhere.
- `dryRun` is a QUERY param on REST (body flag runs a paid job).
- Version before overwrite (`versions/`), archive instead of delete (`archive/`), one commit per phase, tests + headless checks + GUI screenshots before saying "delivered".

**Resume this work:** `claude --resume f634b620-910d-4c24-aeef-bc9232faeca7` (2026-08-28, research + design + P0)
