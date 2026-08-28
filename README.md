# Scenario for Blender

A Blender 4.2+ extension bringing Scenario's image, video, 3D and PBR material generation into the viewport, with a local MCP server so agents (Claude Code, Cursor, Claude Desktop) can build and generate in the open scene.

**How to resume:** `claude --resume f634b620-910d-4c24-aeef-bc9232faeca7` (2026-08-28: research, design, P0 skeleton)

## Why

[redacted] shipped a Blender plugin on 2026-08-20 (7 tabs, MCP bridge). Emmanuel asked for the same features and more on Scenario (2026-08-28). A Feb 2026 PRD (`Scenario-Blender-Plugin-PRD.docx`) and [redacted]'s April 2026 "Playblast to Seedance 2.0" prototype (see `~/Developer/[redacted]/01_blender_plugin.html`) already pointed the same way. Decisions taken 2026-08-28: API key + secret first (OAuth later, feasible via mcp.scenario.com dynamic client registration), v1 extras = render-to-real + Patina materials, native N-panel plus a floating composer, skyboxes and the Scenario-only 3D utilities (retopo, retexture, rigging, motion) in v2.

## Files

- `docs/superpowers/specs/2026-08-28-scenario-for-blender-design.md`: the v1 design (architecture, lanes, phases, tests).
- `research/00-synthesis.md`: parity matrix and architecture lessons (workflow output; verification log appended).
- `research/01-06-[redacted]-*.md`: clean-room behavioural specs of [redacted] Blender 1.5.47 (API layer, UI, Blender integration, MCP bridge, motion/realtime/phonecam, product inventory).
- `research/10-scenario-api-mcp-auth.md`, `11-scenario-models-for-blender.md`, `12-blender-platform-constraints.md`: Scenario and Blender platform maps.
- `research/20-live-api-probes.md`: what was verified live against the API on 2026-08-28 (dryRun, uploads, Patina output contract, 3D asset shape).
- `research/fixtures/patina-copper-512/`: a real Patina Material job (6 maps, job/model/dryRun JSON) used as test fixtures.
- `Scenario-Blender-Plugin-PRD.docx`: the February 2026 PRD (kept as-is).
- `versions/`: previous states of deliverables (v0 = idea-stage README).
- `.env.local` (git-ignored): dev credentials for the "Blender Plugin Tests" project.
- `scenario/` (from P0): the extension source. `tests/`, `tools/`: tests and build scripts.

## Verified vs assumed

Verified live (2026-08-28): REST Basic auth, model records carry UI schema, `?dryRun=true` cost preview, Patina returns 6 typed map assets, multipart upload flow, GLB asset shape, Blender 5.1.1 Python 3.13.9 with gltf/fbx/obj importers and `render.opengl`, OAuth dynamic registration on mcp.scenario.com. Assumed: Patina smoothness semantics (pixels suggest dark = rough), normal-map convention, Blender 4.2/4.5 behaviour (only 5.1.1 installed here).

## Provenance

[redacted]'s GPL source was read for behaviour only (specs in `research/`), no code copied. The MCP bridge follows the Blender Lab `blender_mcp` protocol shape, rewritten.
