# Changelog

All notable changes to Scenario for Blender. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow semantic versioning and match `scenario/blender_manifest.toml`. Each version has a zip on the [releases page](https://github.com/edemaistre/scenario-for-blender/releases).

## [Unreleased]

Planned (see the spec, section 4, and `BUGS.md`): skyboxes applied to the World, remesh, UV unwrap, retexture, part segmentation, auto-rig, text-to-motion with Blender-axis FBX, custom LoRAs, Scenario Workflows, sign in with Scenario (OAuth), an in-Blender agent chat, drag and drop from Generations, a project switcher for team keys.

## [0.6.0] - 2026-08-28

### Added
- **Render Image** and **Render Video** lanes replace Render-to-real. Render Image: a capture of the viewport or the camera plus optional style images and a look prompt, with any image edit model (Gemini 3.1, GPT Image 2, Seedream 5.0 Pro, FLUX 2, Reve Remix, Qwen Edit, MAI Image 2.5 Pro Edit, Grok Imagine 2.0, Z-Image and every other img2img model). Render Video: a playblast of the timeline plus images (the rendered first frame, style references) and a look, with any video model that takes a reference video (Seedance 2.0 / 2.5 / Mini, Minimax H3, Runway Aleph 2, Happy Horse Video Edit, Gemini Omni Edit, Grok Edit Video...). A Render Image result becomes the first frame of Render Video automatically.
- **Prompt Spark**: with an empty look, a still of the view goes to Scenario's prompt writer (`POST /generate/prompt`, 0.75 CU) which writes the art-direction brief before the job is submitted; the Jobs panel shows "Prompt Spark is writing the look". The look it wrote is kept on the lane and in Generations.
- **Precise render prompts** (`core/scene/render_prompt.py`): every input has a stated role. Image 1 / @video1 is the exact scene to render (objects, positions, camera, framing frozen); the other images are look references whose content must not appear. The first tests had put a character from a style image on a roof.
- **Camera path planner** in Render Video: numbered shot markers (small cameras `Shot 1`, `Shot 2`... placed at the cursor or from the current view, each with its own focal length and hold), or a preset around the subject (orbit, push in, pull back, crane, pan, flyover), a free-text "Plan" field (`slow orbit, 8 s, 35mm`), Build camera path (keyframed camera, Track To the subject), Preview. Also an MCP tool `camera_path` so agents can set the move.
- **Edit 3D** lane: select a mesh, pick a task (Retexture, Retopology, Rigging, Animation, UV unwrap, Segment, Stylize), the mesh is exported as GLB at generate time and the result is imported next to the original (Meshy 7 Retexture, Tripo Retopology, Meshy Rigging / Animation / UV Unwrap, Tripo Segmentation, Hunyuan Polygen, Trellis 2 Retexture, Cartwheel...).
- **Model picker**: a search dialog with filter chips (All, Featured, Scenario, Partners, Recent), a list with thumbnails and the description of the highlighted model, in place of the 600-entry dropdown (still available as a small arrow next to it).
- **Composer text selection**: Shift+arrows, Shift+Home/End, click and drag, double-click selects a word, Ctrl/Cmd+C copies, Ctrl/Cmd+X cuts, typing replaces the selection. The collapse control is a proper minus button in the top-right corner; a "Settings" chip opens the full panel.
- Reference thumbnails in every lane and an "Inputs" strip on results, so the images used in an inference are visible. 3D results have "Add to scene" and "Select"; image results have "Use as video first frame".

### Changed
- The Scenario tab is four panels: **Scenario** (lane tabs: Image, Video, 3D, Materials, Render Image, Render Video, Edit 3D), **Jobs** (everything running, with a count in the header), **Generations** (this session's results with their actions, then the project's cloud history) and **Agents (MCP)**. Generations and MCP are no longer lane tabs.
- The header "Scenario" button opens the sidebar on the Scenario tab instead of a second small form; the floating composer remains the quick path.
- Output folders carry the day: `<output>/<kind>/YYYYMMDD/` (Downloads synced to Dropbox stays browsable).
- Version, catalog lanes (`render_image`, `render_video`, `edit3d`) and MCP `generate` lanes extended accordingly.

### Fixed
- Numeric choice parameters (Seedance `duration`: Auto, 4 to 15 s) were edited through the dropdown but read from the integer field, so the request always carried the default (-1, Auto) whatever the dropdown or Match timeline said. The value shown is now the value sent.

### Removed
- Render-to-real (two-step concept then Seedance) and the header popover; the code is archived under `archive/0.5.x/`.

## [0.5.2] - 2026-08-28

### Fixed
- A finished Meshy 6 job never reached the scene. Root cause: the CDN closed the connection while the add-on downloaded one of the seven result files (Meshy bundles include a 200+ MB OBJ), downloads had no retry, and any failure marked the whole job failed. Downloads now stream to disk with three retries and short backoff, 3D bundles fetch the meshes first, and a 3D job stays successful when at least one mesh arrived; missing alternates or textures are recorded on the job. Jobs that already failed this way can be re-imported from Generations.

## [0.5.1] - 2026-08-28

### Fixed
- 3D results looked untextured (Meshy 7). Root cause: a Meshy job returns seven assets (a GLB with three embedded PBR textures, a 205 MB OBJ whose `.mtl` arrives under a `.bin` name, and four texture PNGs); the importer loaded every file it could open, so an untextured OBJ copy sat exactly on top of the textured GLB. Now one primary mesh is imported per job (glTF first, then the variant with the most PBR textures), the viewport switches to Material Preview, and the other mesh files stay on disk with an Import button in Results.
- Two robots from Rodin Gen-2.5. Root cause: the schema default `material = All` makes Rodin return a baked Shaded GLB and a PBR GLB; both were imported. Rodin now defaults to `PBR` in the add-on.

### Changed
- Image to 3D and Multi-view to 3D: the dedicated multi-view models (Meshy 7 Multi Image, Tripo 3.1 Multi View, Hunyuan 3.1 Pro Multiview) and Tripo P1 are curated defaults, models known only from the catalog list are classified by name, and the schemas of the models shown in a mode load in the background.

## [0.5.0] - 2026-08-28

### Added
- Floating composer in the viewport: a collapsed pill with the prompt and Generate, an expanded card with lane tabs, an editable prompt (caret, arrows, Home/End, paste, select all, Enter generates, Esc blurs), the model chip and the live CU quote. It shares its state with the N-panel; a circuit breaker switches it off after repeated drawing errors, the preference switches it back on.
- `tools/build_repo.sh` builds a static extension repository (`index.json`, zip, HTML listing) so updates flow through Blender's own updater.

### Fixed
Results of a 36-agent adversarial review of the first two phases (31 confirmed findings, 29 fixed):
- API clients are created on the main thread before any worker starts; jobs that cannot resume without a key are retried once a key exists.
- Job registry writes are thread-safe and per process; download failures no longer leave half a material behind.
- Catalog failures show a message and a Retry button instead of "Loading models..." forever; a changed key rebuilds the catalog client.
- Model selection is stored by id, so it survives catalog changes and file reloads.
- Edit-mode safety and undo for scene operators; online-access checks on every network operator.
- Non-curated models load their schema in the background instead of blocking the interface.
- No disk writes during cost estimates (Render Result references are encoded at submit time only).
- Debounce timestamps no longer live in a 32-bit property (they rounded to 128 s and froze the quote at random).
- Automated GUI checks disable every Generate path (`SCENARIO_GUI_PROBE=1`).

## [0.4.0] - 2026-08-28

### Added
- Local MCP server (Streamable HTTP on 127.0.0.1, per-session bearer token) started with the add-on; tool calls run on Blender's main thread with a 120 s timeout.
- 16 tools: scene_summary, object_detail, execute_python (preference-gated, quit and factory-reset calls blocked), select_objects, set_frame, screenshot_viewport, render_still, list_models, model_schema, estimate_cost, generate, job_status, wait_for_job, import_result, capture_reference, list_generations.
- MCP tab: status, masked token, Start/Stop, Python toggle, one-click setup copy for Claude Code, Cursor, Claude Desktop (stdio shim), Codex and a curl test.
- Headless serving: `blender --background file.blend --command scenario-mcp --port 9876 --token T`.

## [0.3.0] - 2026-08-28

### Added
- Captures: viewport or scene-camera stills and 1280x720 H.264 playblasts at generate time, overlays and gizmos hidden, optional grey-clay shading, render settings and the current frame restored afterwards.
- Video lane: any txt2video / img2video / video2video model, Viewport clip and Camera clip references, Match timeline picks the clip duration from the frame range, Seedance prompts get their @video1 / @image1 tags, results play with the system player or Blender's player.
- Render-to-real: step 1 restyles a capture into a concept still (Gemini 3.1 or GPT Image 2), step 2 sends the playblast plus the concept to Seedance 2.0 with a playblast-aware prompt.
- Playblasts shorter than 4 s (Seedance's minimum) are padded.

## [0.2.0] - 2026-08-28

### Added
- Materials lane (Patina): prompt to a seamless PBR set (base color, normal, smoothness, metallic, height) built as a Principled BSDF material with UV mapping and displacement, applied to the meshes selected at submit time; tiling control.
- 3D lane: Text / Image / Multi-view modes; GLB, FBX and OBJ results imported into a "Scenario" collection with the bounding box bottom centre on the 3D cursor.
- Generations: the project's cloud job history merged with local files, thumbnails, Import into scene for results generated elsewhere, paging.

## [0.1.0] - 2026-08-28

### Added
- Extension skeleton (Blender 4.2+, pure Python, no wheels), preferences with API key and secret, output folder.
- REST client with Basic auth, bounded retries, typed errors, dry-run cost preview (`?dryRun=true`).
- Model catalog with disk cache and pagination; schema-driven parameter UI built from each model record.
- Image lane: prompt, references (file, render result), live CU estimate on the Generate button, results loaded as packed images with Show / Apply as texture / Add as plane.
- Threaded job manager with a persisted registry (unfinished jobs resume after a restart), main-thread pump, viewport header popover.

[Unreleased]: https://github.com/edemaistre/scenario-for-blender/compare/v0.5.2...HEAD
[0.5.2]: https://github.com/edemaistre/scenario-for-blender/releases/tag/v0.5.2
[0.5.1]: https://github.com/edemaistre/scenario-for-blender/releases/tag/v0.5.1
[0.5.0]: https://github.com/edemaistre/scenario-for-blender/releases/tag/v0.5.0
[0.4.0]: https://github.com/edemaistre/scenario-for-blender/commits/v0.5.0
[0.3.0]: https://github.com/edemaistre/scenario-for-blender/commits/v0.5.0
[0.2.0]: https://github.com/edemaistre/scenario-for-blender/commits/v0.5.0
[0.1.0]: https://github.com/edemaistre/scenario-for-blender/commits/v0.5.0
