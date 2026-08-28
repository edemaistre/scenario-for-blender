# Changelog

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
