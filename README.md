# Scenario for Blender

**Status: experimental, v0.6.0 (2026-08-28).** A Blender 4.2+ extension that brings [Scenario](https://scenario.com) image, video, 3D and PBR material generation into the viewport, renders the scene as a finished still or clip (Render Image / Render Video, with Prompt Spark writing the look and a camera path planner), edits the selected mesh with Scenario's 3D tools (retexture, retopology, rigging, animation, UV unwrap, segmentation), and runs a local MCP server so agents (Claude Code, Cursor, Claude Desktop, Codex) can build and generate in the open scene. Pure Python, no bundled wheels, GPL-3.0-or-later. You need a Scenario account and an API key (Pro plan or above).

**User guide: [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)**, also as a single-file HTML handbook with screenshots: [`docs/user-guide.html`](docs/user-guide.html). Changelog: [`CHANGELOG.md`](CHANGELOG.md).

Quick start: download `scenario-<version>.zip` from the releases (or run `./tools/build.sh`), drag it onto Blender, paste your key in Preferences > Add-ons > Scenario, press N in the 3D viewport and open the Scenario tab. Details, tests and the agent setup are below; the design lives in `docs/superpowers/specs/`, the delivery plans in `docs/superpowers/plans/`, and the clean-room research that shaped it in `research/`.

---


**How to resume:** `claude --resume f634b620-910d-4c24-aeef-bc9232faeca7` (2026-08-28: research, design, P0 skeleton)

## Why

[redacted] shipped a Blender plugin on 2026-08-20 (7 tabs, MCP bridge). Emmanuel asked for the same features and more on Scenario (2026-08-28). A Feb 2026 PRD (`Scenario-Blender-Plugin-PRD.docx`) and [redacted]'s April 2026 "Playblast to Seedance 2.0" prototype (see `~/Developer/[redacted]/01_blender_plugin.html`) already pointed the same way. Decisions taken 2026-08-28: API key + secret first (OAuth later, feasible via mcp.scenario.com dynamic client registration), v1 extras = render-to-real + Patina materials, native N-panel plus a floating composer, skyboxes and the Scenario-only 3D utilities (retopo, retexture, rigging, motion) in v2.

## Files

- `docs/USER_GUIDE.md`, `docs/user-guide.html`, `docs/images/`: the user guide (Markdown, and a self-contained HTML handbook with the cropped panel screenshots embedded).
- `docs/user-guide.src.html` + `tools/build_docs_html.py`: edit the source, run the script to rebuild `docs/user-guide.html` with the images embedded.
- `docs/superpowers/specs/2026-08-28-scenario-for-blender-design.md`: the v1 design (architecture, lanes, phases, tests).
- `research/00-synthesis.md`: parity matrix and architecture lessons (workflow output; verification log appended).
- `research/01-06-[redacted]-*.md`: clean-room behavioural specs of [redacted] Blender 1.5.47 (API layer, UI, Blender integration, MCP bridge, motion/realtime/phonecam, product inventory).
- `research/10-scenario-api-mcp-auth.md`, `11-scenario-models-for-blender.md`, `12-blender-platform-constraints.md`: Scenario and Blender platform maps.
- `research/20-live-api-probes.md`: what was verified live against the API on 2026-08-28 (dryRun, uploads, Patina output contract, 3D asset shape).
- `research/fixtures/patina-copper-512/`: a real Patina Material job (6 maps, job/model/dryRun JSON) used as test fixtures.
- `Scenario-Blender-Plugin-PRD.docx`: the February 2026 PRD (kept as-is).
- `versions/`: previous states of deliverables (v0 = idea-stage README).
- `.env.local` (git-ignored): dev credentials for the "Blender Plugin Tests" project.
- `scenario/`: the extension source (`core/` is plain Python, `blender/` is the bpy glue). `blender_manifest.toml` at its root.
- `tests/unit/` (pytest, no Blender), `tests/blender/` (run inside `blender --background`), `tests/smoke/` (opt-in, spends credits), `tests/fixtures/` (recorded API records and a real Patina job).
- `tools/build.sh`, `tools/install_dev.sh`, `tools/record_fixtures.py`, `tools/gui_screenshot.py`, `tools/blank.blend`. `dist/` (ignored) holds built zips.
- `docs/superpowers/plans/`: P0 and P1 implementation plans (executed task by task).
- `CHANGELOG.md`: what shipped per phase.

## Run it

1. `./tools/install_dev.sh` (builds, validates and installs the zip into Blender's `user_default` repository and enables it). Restart running Blender instances.
2. Blender > Edit > Preferences > Add-ons > Scenario: paste an API key and secret (Scenario portal > Team > API Keys, Project or Team scope), press Test connection.
3. In the 3D viewport press N, open the Scenario tab (or the Scenario button in the viewport header), pick a model, type a prompt, read the CU price on Generate, generate.

## 3D results: one mesh per job

Providers return several variants of one result (Meshy: GLB + OBJ + texture PNGs; Rodin with `material=All`: a shaded GLB and a PBR GLB). The add-on imports one primary mesh (glTF first, then the variant with the most PBR textures), switches the viewport to Material Preview so textures show, and lists the other mesh files in Generations with an Add button (plus Add to scene and Select for the primary mesh). Rodin defaults to `PBR`. Root causes and the fix are in `CHANGELOG.md` 0.5.1.

## Floating composer

A pill at the bottom of every 3D viewport shows the current prompt and a Generate button; click it to expand lane tabs (Image, Video, 3D, Materials, Render Img, Render Vid), an editable prompt with real text selection (click, drag, Shift+arrows, double-click, Ctrl/Cmd+A/C/X/V; Enter generates, Esc blurs), the model chip (opens the model picker), a Settings chip (opens the sidebar) and the live CU quote. The composer is the quick path; every setting lives in the sidebar, which the header "Scenario" button opens. The sidebar tab has four panels: Scenario (lane tabs), Jobs, Generations, Agents (MCP). If drawing ever fails repeatedly the composer switches itself off; re-enable it in Preferences.

## Install from a repository (updates through Blender)

`./tools/build_repo.sh` builds `dist/repo/` (index.json, the zip, an HTML listing). Host that folder on any static HTTPS server, then in Blender: Preferences > Get Extensions > Repositories > add the `index.json` URL (requires Allow Online Access). Updates then appear in Blender's own updater. The Extensions store itself is not an option for an account-gated add-on (ToS 3.10 / 4.3), see the spec.

## Agents (MCP)

The add-on runs a local MCP server (default `http://127.0.0.1:9876/mcp`, bearer token shown in the MCP tab, new token per Blender session). Copy a setup from the MCP tab:

- Claude Code: `claude mcp add --transport http scenario-blender http://127.0.0.1:9876/mcp --header "Authorization: Bearer <token>"`
- Cursor: paste the `mcp.json` snippet.
- Claude Desktop: stdio snippet running `scenario/mcp/stdio_shim.py` with Blender's Python.
- Headless: `blender --background scene.blend --command scenario-mcp --port 9876 --token <token>`.

Agents get scene tools (summary, object detail, select, set frame, screenshots, quick renders, gated Python) and Scenario tools (models, schema, cost, generate, job status, import into scene, capture a reference from the viewport, history). Verified 2026-08-28: curl from another process listed 16 tools and read the scene.

## Tests

- `make test`: unit tests (pytest, no Blender).
- `make test-blender`: integration tests inside Blender 5.1.1 headless (requires `./tools/install_dev.sh` first), including the MCP server over real HTTP.
- `SCENARIO_SMOKE=1 python3 tests/smoke/smoke_image.py`, `smoke_material.py`, `smoke_video.py`: one real generation each through the core (about 9, 7 and 76 CU; the video smoke aborts if its dry run exceeds 150 CU).
- GUI check: `blender tools/blank.blend --python tools/gui_screenshot.py -- out.png image 10`, screenshots reviewed under `~/Developer/scratch/playwright-screenshots/scenario-blender/`.

Credits spent on this project so far: about 207 CU (185 CU of probes and smokes, plus two accidental 11 CU GPT Image 2 jobs on 2026-08-28 triggered by keyboard focus landing in an automated GUI test window; the screenshot tool now disables Generate) (two Patina probes 12 CU, Gemini smoke 9 CU, Patina smoke 6 CU, Seedance smoke 76 CU plus one failed 76 CU attempt on a 0.5 s clip, quality-gate fees), cap agreed about $30.

## Verified vs assumed

Verified live (2026-08-28): REST Basic auth, model records carry UI schema, `?dryRun=true` cost preview, Patina returns 6 typed map assets, multipart upload flow, GLB asset shape, Blender 5.1.1 Python 3.13.9 with gltf/fbx/obj importers and `render.opengl`, OAuth dynamic registration on mcp.scenario.com. Assumed: Patina smoothness semantics (pixels suggest dark = rough), normal-map convention, Blender 4.2/4.5 behaviour (only 5.1.1 installed here).

## Licence and provenance

GPL-3.0-or-later (see `LICENSE`), the licence Blender requires for add-ons that use `bpy`. 
[redacted]'s GPL source was read for behaviour only (specs in `research/`), no code copied. The MCP bridge follows the Blender Lab `blender_mcp` protocol shape, rewritten.
