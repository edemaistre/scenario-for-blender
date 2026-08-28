# Scenario for Blender (project pointer)

Read `README.md` first, then `docs/superpowers/specs/2026-08-28-scenario-for-blender-design.md` (the approved v1 design).

**State (2026-08-28):** P0 to P3 merged on `main` (Image, Materials via Patina, 3D import at cursor, Generations history, Video lane with captures, Render-to-real, local MCP server with 16 tools; 62 unit + 47 headless tests green; four real smokes OK). Next: P4 (gpu/blf floating composer, extension repository, distribution polish), then the v2 backlog in the spec. P4 plan still to be written. Research notes in `research/` (clean-room behavioural specs of [redacted] 1.5.47 + Scenario API/model maps + live probes). Dev credentials in git-ignored `.env.local` (workspace "Blender Plugin Tests", ~$30 test cap, never print them).

Hard rules for this folder:
- Clean-room: never copy code from the [redacted] source in `~/Developer/scratch/2026-08-28 [redacted] Blender Plugin 1.5.47/`; behaviour only.
- Pure Python, no wheels; `bpy` on the main thread only; GPL-3.0-or-later SPDX header on every source file; no em dashes anywhere.
- `dryRun` is a QUERY param on REST (body flag runs a paid job).
- Version before overwrite (`versions/`), archive instead of delete (`archive/`), one commit per phase, tests + headless checks + GUI screenshots before saying "delivered".

**Resume this work:** `claude --resume f634b620-910d-4c24-aeef-bc9232faeca7` (2026-08-28, research + design + P0)
