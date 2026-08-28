# Changelog

## 0.1.0 (P0, 2026-08-28)
- Extension skeleton (Blender 4.2+, pure Python, no wheels), preferences with API key and secret, output folder.
- REST client with Basic auth, bounded retries, typed errors, dry-run cost preview (`?dryRun=true`).
- Model catalog with disk cache and pagination; schema-driven parameter UI built from each model record.
- Image lane: prompt, references (file, render result), live CU estimate on the Generate button, results loaded as packed images with Show / Apply as texture / Add as plane.
- Threaded job manager with a persisted registry (unfinished jobs resume after a restart), main-thread pump.
- Viewport header popover (model, prompt, Generate).
- Smoke test (opt-in) ran one real Gemini 3.1 image end to end: 9 CU, PNG downloaded.
