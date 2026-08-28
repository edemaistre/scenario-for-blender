# Changelog

## 0.3.0 (P2, 2026-08-28)
- Captures: viewport or scene-camera stills and 1280x720 H.264 playblasts at generate time, overlays and gizmos hidden, optional grey-clay shading, every render setting and the current frame restored afterwards.
- Video lane: any txt2video / img2video / video2video model, "Viewport clip" and "Camera clip" references, Match timeline picks the clip duration from the frame range, Seedance prompts get their @video1 / @image1 tags, results play with the system player or Blender's player.
- Render-to-real: step 1 restyles a capture into a concept still (Gemini 3.1 or GPT Image 2), step 2 sends the playblast plus the concept to Seedance 2.0 with a playblast-aware prompt.
- Playblasts shorter than 2 s are padded (a 0.5 s clip made Seedance fail with an internal error; 3 s succeeded).
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
