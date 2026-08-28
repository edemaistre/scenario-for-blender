# Changelog

## 0.5.1 (2026-08-28)
Fixes from the first hands-on session.
- **3D results looked untextured (Meshy 7).** Root cause: a Meshy job returns seven assets (a GLB with three embedded PBR textures, a 205 MB OBJ whose `.mtl` arrives under a `.bin` name, and four texture PNGs); the importer loaded every file it could open, so an untextured OBJ copy sat exactly on top of the textured GLB. Now one primary mesh is imported per job (glTF first, then the variant with the most PBR textures), the viewport switches to Material Preview, and the other mesh files stay on disk with an Import button in Results.
- **Two robots from Rodin Gen-2.5.** Root cause: the schema default `material = All` makes Rodin return a baked "Shaded" GLB and a PBR GLB; both were imported. Rodin now defaults to `PBR` in the add-on (curated parameter override), and the single-mesh import above covers the other variants.
- **Image to 3D and Multi-view to 3D.** Models known only from the catalog list had no schema, so they never appeared in Multi-view and their forms stayed empty. The dedicated multi-view models (Meshy 7 Multi Image, Tripo 3.1 Multi View, Hunyuan 3.1 Pro Multiview) and Tripo P1 are curated defaults now, list-only models are classified by name, and schemas of the visible models load in the background when a mode is selected.

## 0.5.0 (P4, 2026-08-28)
- Floating composer in the viewport: collapsed pill with the prompt and Generate, expanded card with lane tabs, an editable prompt (caret, arrows, Home/End, paste, select all, Enter to generate, Esc to blur), model chip and the live CU quote; shares its state with the N-panel; a circuit breaker removes it after repeated draw errors and the preference re-enables it.
- Review fixes (36-agent adversarial review of P0+P1): API clients are resolved on the main thread before any worker starts, jobs that cannot be resumed without a key are retried once a key exists, registry snapshots are thread-safe and per-process, download failures no longer leave half a material behind, catalog failures show a message instead of "Loading models..." forever, model selection is stored by id (no drift when the catalog changes), edit-mode safety and undo for scene operators, online-access checks on every network operator, non-curated models load in the background, no more disk writes during cost estimates.

## 0.4.0 (P3, 2026-08-28)
- Local MCP server (Streamable HTTP on 127.0.0.1, per-session bearer token) started with the add-on; tool calls run on Blender's main thread through the pump, with a 120 s timeout instead of a frozen client.
- 16 tools: scene_summary, object_detail, execute_python (preference-gated, quit and factory-reset calls blocked), select_objects, set_frame, screenshot_viewport, render_still, list_models, model_schema, estimate_cost, generate, job_status, wait_for_job, import_result, capture_reference, list_generations.
- MCP tab: status, masked token, Start/Stop, Python toggle, one-click setup copy for Claude Code, Cursor, Claude Desktop (stdio shim), Codex and a curl test.
- Headless serving: `blender --background file.blend --command scenario-mcp --port 9876 --token T`.
- Proof: from a separate process, curl listed the tools and read the scene through the live server.

## 0.3.0 (P2, 2026-08-28)
- Captures: viewport or scene-camera stills and 1280x720 H.264 playblasts at generate time, overlays and gizmos hidden, optional grey-clay shading, every render setting and the current frame restored afterwards.
- Video lane: any txt2video / img2video / video2video model, "Viewport clip" and "Camera clip" references, Match timeline picks the clip duration from the frame range, Seedance prompts get their @video1 / @image1 tags, results play with the system player or Blender's player.
- Render-to-real: step 1 restyles a capture into a concept still (Gemini 3.1 or GPT Image 2), step 2 sends the playblast plus the concept to Seedance 2.0 with a playblast-aware prompt.
- Playblasts shorter than 4 s (Seedance's minimum duration) are padded; a 0.5 s clip made Seedance fail with an internal error, 3 s succeeded.
- Smoke: a real 3 s playblast through Seedance 2.0 at 480p / 4 s: 76 CU, MP4 downloaded.

## 0.2.0 (P1, 2026-08-28)
- Materials lane (Patina): prompt to a seamless PBR set (base color, normal, smoothness, metallic, height) built as a Principled BSDF material with UV mapping and displacement, applied to the meshes selected at submit time; tiling control.
- 3D lane: Text / Image / Multi-view modes pick the right models (Meshy 7, Tripo 3.1, Hunyuan 3.1 Pro, Rodin 2.5, and any other txt23d / img23d model); GLB/FBX/OBJ results imported into a "Scenario" collection with the bounding box bottom centre on the 3D cursor.
- Generations: the project's cloud job history merged with local files, thumbnails, "Import into scene" for results generated elsewhere (downloads on demand), paging.
- Smoke: one real Patina material (6 CU) produced six typed maps and a valid material plan.

## 0.1.0 (P0, 2026-08-28)
- Extension skeleton (Blender 4.2+, pure Python, no wheels), preferences with API key and secret, output folder.
- REST client with Basic auth, bounded retries, typed errors, dry-run cost preview (`?dryRun=true`).
- Model catalog with disk cache and pagination; schema-driven parameter UI built from each model record.
- Image lane: prompt, references (file, render result), live CU estimate on the Generate button, results loaded as packed images with Show / Apply as texture / Add as plane.
- Threaded job manager with a persisted registry (unfinished jobs resume after a restart), main-thread pump.
- Viewport header popover (model, prompt, Generate).
- Smoke test (opt-in) ran one real Gemini 3.1 image end to end: 9 CU, PNG downloaded.
