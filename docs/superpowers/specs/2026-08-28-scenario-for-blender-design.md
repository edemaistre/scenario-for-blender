# Scenario for Blender: design spec (v1)

Date: 2026-08-28. Status: approved direction (Emmanuel, 2026-08-28: API key first, OAuth later; v1 "more" = render-to-real + Patina materials; native N-panel + floating composer; clean-room). Session: f634b620-910d-4c24-aeef-bc9232faeca7.

## 1. Goal

A Blender extension that gives artists a full creative toolkit (image, video, 3D, scene/agent bridge, camera capture, asset history) on top of Scenario's models and API, plus Scenario-only strengths: Patina PBR materials applied straight onto meshes, and a first-class render-to-real flow (viewport capture and playblast to styled stills and video). A complete first release is the floor, the phased plan reaches it; skyboxes, mesh utilities, rigging and motion, LoRAs, Workflows, OAuth and in-Blender chat are v2 and already mapped to live Scenario models.

Non-goals for v1: phone camera, realtime prerender, hosted relay, in-Blender agent chat, telemetry, self-updater.

## 2. Constraints and decisions

- **All original code.** No code copied from any third-party reference implementation. Blender Lab `blender_mcp` protocol shape is reused as behaviour, code rewritten.
- **Licence** GPL-3.0-or-later (bpy add-ons are GPL territory; Blender Lab base is GPL). SPDX header on every file. Bundled icons CC0 or Scenario-owned.
- **Distribution off-store**: extensions.blender.org ToS 3.10 (no keys or registration gating features) and 4.3 (login-gated services only if complete and aligned) exclude a Scenario-account add-on. Ship: `.zip` drag-and-drop install, plus a Scenario-hosted extension repository (`index.json` from `blender --command extension server-generate`) so updates flow through Blender's own updater. Follow every store guideline anyway: `network` and `files` permissions with reasons, `bpy.app.online_access` checked before any socket, no auto-update code, no telemetry, no in-UI upsell, data leaves the machine only on explicit user action, name without "Blender", no Blender logo.
- **Blender target**: `blender_version_min = "4.2.0"`, tested on 5.1.1 (local). Pure Python: no wheels, stdlib `urllib`/`ssl`/`json`/`threading`/`queue` (all verified importable in Blender's Python 3.13.9; 4.x ships 3.11). Avoid `Material.use_nodes` reliance on 5.x (deprecated), set it on 4.x only.
- **Threading**: `bpy` on the main thread only. HTTP, uploads, downloads, polling in worker threads pushing results to a `queue.Queue`; one `bpy.app.timers` pump (0.25 s active, 1 s idle, persistent, exception-safe) applies results and tags regions for redraw. Timers do not fire in `--background`: headless paths use a blocking loop from a CLI command.
- **Auth v1**: API key + secret (HTTP Basic) entered in add-on preferences (`subtype='PASSWORD'`), optional env override `SCENARIO_API_KEY` / `SCENARIO_API_SECRET` for dev and CI. Project resolved from `GET /v1/teams` (a project key returns exactly its project). "Create a key" button opens the portal. OAuth (v2): `mcp.scenario.com` advertises OAuth 2.1 with dynamic client registration, PKCE S256, public clients and loopback redirects (validated 2026-08-28: HTTP 201 on `/oauth/register`); the token drives the MCP JSON-RPC surface. Transport layer is written so a Bearer/MCP transport slots in beside REST/Basic.
- **Cost before commit**: every parameter change debounces (0.7 s) a `POST /v1/generate/custom/{modelId}?dryRun=true` and shows "Generate · N CU" (query param only: `dryRun` in the body is ignored and runs a paid job, verified).
- **Storage**: never write inside the add-on folder. State, caches, job registry under `bpy.utils.extension_path_user(__package__, create=True)`. Downloads under a preference `output_dir` (default `~/Downloads/Scenario/`), subfolders `images/ videos/ 3d/ materials/`, filenames `<date>_<model>_<jobid>.<ext>`.

## 3. Architecture

```
Blender UI (N-panel tabs, popover, gpu/blf composer)     MCP clients (Claude Code, Cursor, Claude Desktop via stdio shim)
        |  operators / properties                                 |  JSON-RPC over localhost HTTP (or stdio shim)
        v                                                         v
  ui/props.py  <-- one Scene PropertyGroup, single source of truth -->  mcp/server.py (http.server thread)
        |                                                         |
        v                                                         v
  core/jobs/manager.py  (JobRecord state machine, worker threads, queue, timers pump, persisted registry)
        |
        v
  core/api/*  (REST client: catalog, generate, dryRun, jobs, uploads, assets)   ---->  api.cloud.scenario.com/v1
        |
        v
  core/scene/*  (import GLB/FBX/OBJ, images, Patina material builder, capture stills/playblasts, video playback)
```

### 3.1 Package layout (`scenario/`, extension id `scenario`, name "Scenario")

- `blender_manifest.toml`, `__init__.py` (register/unregister, CLI command `scenario-mcp` for headless), `prefs.py`.
- `core/api/`: `client.py` (Basic auth, JSON, retries with backoff on 429/5xx, `ScenarioError` with reason and trace id, User-Agent `ScenarioBlender/<version>`), `catalog.py` (public + private models, per-model record cache to disk, lane filters by `capabilities` and `sc:` tags, curated default table + `deprecated:<id>` follow), `generate.py` (submit, dryRun), `jobs.py` (get, list), `uploads.py` (base64 `POST /assets` under 4 MB, multipart `POST /uploads` -> PUT parts -> `POST /uploads/{id}/action` -> asset id from `GET /jobs/{uploadJobId}.metadata.output.entityId`), `assets.py` (get, signed URL download following redirects, never altering the query string).
- `core/schema/`: `params.py` maps a model record's `parameters[]`/`inputs[]`/`uiConfig` to a dynamic `PropertyGroup` per model (enum with display labels, int/float with min/max/step, bool, string with max length, file/file_array reference slots, string_array as multi-toggle), keeps values across model switches when names match, validates `required` rules (`always`, `ifDefined`), builds the flat request body (arrays stay arrays, unset optionals omitted).
- `core/jobs/`: `manager.py` (submit -> poll every 2.5 s -> download -> apply; registry JSON survives restarts; cancel where the API allows; per-job progress and CU), `records.py` (JobRecord: id, lane, model, params, status, progress, cuCost, assetIds, local paths, error, createdAt).
- `core/scene/`: `import_3d.py` (glTF/FBX/OBJ importers, wrap in a "Scenario" collection, place at 3D cursor or origin, select result, optional studio thumbnail), `images.py` (load + pack image datablock, open in an Image Editor window, apply as Base Color texture on the active mesh, add as plane facing the view), `materials.py` (Patina: 6 assets by `metadata.type` -> Principled BSDF: albedo (sRGB) -> Base Color, smoothness (Non-Color) -> Invert -> Roughness, metallic (Non-Color) -> Metallic, normal (Non-Color) -> Normal Map -> Normal, height (Non-Color) -> Displacement (Bump fallback), UV mapping node with scale; assign to selected meshes; viewport to Material Preview), `capture.py` (viewport still via `render.opengl`, camera still, playblast animation 1280x720 H.264 with overlays hidden and stamps off, first frame PNG, frame range from scene or preview range, duration clamped to the model's limits), `video.py` (play with Blender's animation player or OS default), `world.py` (v2 skybox hook).
- `ui/`: `props.py` (Scene properties: active lane, prompt, model per lane, reference lists, capture source, estimate state, composer state), `panels.py` (N-panel "Scenario" tab: account strip with project name, tabs Image / Video / 3D / Materials / Render-to-real / MCP, running-jobs box, Generations list), `operators.py` (generate, estimate, cancel, add/remove reference, capture, import to scene, apply as texture, apply material, play video, open folder, refresh catalog, copy MCP config), `previews.py` (thumbnail collection from cached downloads), `composer/` (gpu/blf floating pill: collapsed pill with placeholder + Generate, expanded card with lane tabs, prompt line, reference chips, cost on Generate; modal operator only while hovered or focused; circuit breaker removes the handler after repeated failures; toggle in preferences).
- `mcp/`: `protocol.py` (JSON-RPC 2.0, MCP `initialize`, `tools/list`, `tools/call`, streamable HTTP POST returning JSON), `server.py` (stdlib `http.server` on 127.0.0.1:<port>, background thread, per-request future resolved by the main-thread pump, 10 MiB cap, per-session random bearer token shown in the panel and embedded in the copied config), `tools.py` (Blender tools: `scene_summary`, `object_detail`, `execute_python` (consent toggle, default on, weak guard on quit/factory-reset operators), `screenshot_viewport`, `render_still`; Scenario tools: `list_models`, `estimate_cost`, `generate` (lane, model, params, returns job id and CU), `job_status`, `import_result` (at cursor), `apply_material`, `capture_viewport_as_reference`), `stdio_shim.py` (stdio <-> local HTTP proxy for clients without HTTP transport, run with Blender's Python).
- `tests/`: `unit/` (pure Python, no bpy: client with a fake transport, schema mapping, body building, job state machine, material graph plan from the Patina fixture manifest, upload flow), `blender/` (headless `blender --background --python`: register/unregister, import fixture GLB, build Patina material from fixtures and assert node links, image load; run via `make test-blender`), `smoke/` (opt-in, spends CU: env `SCENARIO_SMOKE=1`, cap logged).
- `tools/`: `build.sh` (validate + build zip via Blender CLI), `install_dev.sh` (install-file into user_default, restart hint), `repo/` (server-generate for the hosted index).

### 3.2 Data flow: one generation

1. User picks a lane and model; the schema-driven panel renders; edits debounce an estimate worker (`dryRun=true`, placeholder asset ids for unset file fields) whose result updates "Generate · N CU".
2. Generate: references are resolved (file -> upload; viewport -> capture then upload; render result -> save then upload), body built flat from the schema, `POST /generate/custom/{model}` submitted; a JobRecord is created and persisted; the panel shows the job in "Running".
3. Poll worker fetches `GET /jobs/{id}` every 2.5 s until success/failure/canceled, then `GET /assets/{id}` for each asset and downloads files to `output_dir`.
4. Main-thread pump applies: image -> datablock + Image Editor window; 3D -> import at cursor in the "Scenario" collection; Patina -> material on the selection; video -> ready to play; record moves to Generations with thumbnail.

### 3.3 Error handling

- API errors surface the server `reason` (plus `trace_id` when present) in the panel row and the status bar; 401/403 point to Preferences; 402/plan errors name the plan; 429 shows the cooldown seconds; network failures retry with backoff (3 tries) then fail the job without losing the record.
- Every job is persisted before submit and after each transition; on Blender restart, unfinished jobs resume polling.
- Main-thread safety: the pump wraps each applied result in try/except and reports; the composer draw handler is guarded by a breaker (5 consecutive failures or one call over 2 s removes it and shows "Composer disabled, re-enable in Preferences").
- `bpy.app.online_access` false: every network action is disabled with a tooltip explaining why.

## 4. Lanes (v1 scope, parity mapping)

| Lane | Scenario models (defaults first, rest schema-driven) | Output in Blender |
|---|---|---|
| Image | `model_openai-gpt-image-2`, `model_google-gemini-3-1-flash`, Seedream 5.0, Z-Image and any `txt2img`/`img2img` | image datablock, Image Editor window, apply as texture, add as plane |
| Video | `model_bytedance-seedance-2-0` (+2.5), Kling, Veo, Wan (`txt2video`/`img2video`/`video2video`) with Blender input viewport or camera playblast, match-timeline duration, `@image1`/`@video1` tagging for Seedance | MP4 in output_dir, play in Blender's player |
| 3D | text: `model_meshy-7-txt23d`, `model_rodin-hyper3d-v2-5-text-to-3d`(+fast); image: `model_tripo-v3-1-image-to-3d`, `model_meshy-7-img23d`, `model_hunyuan-3d-pro-3-1-i23d`, `model_rodin-hyper3d-v2-5`; multi-view: Meshy 7 multi, Tripo 3.1 multi, Hunyuan 3.1 multi | GLB imported at 3D cursor, "Scenario" collection, selected |
| Materials (Patina) | `model_patina-material` (text, variation, inpaint), `model_patina` (image to maps), `model_patina-material-extract` | Principled BSDF material on selected meshes, maps packed, tiling scale control |
| Render-to-real | Concept: Image lane models with viewport/camera still as reference and optional style refs; Video: Seedance 2.0 with playblast + concept, prompt prefix ("grayscale playblast, use the reference as style") and cinematic suffix presets, force grey-clay shading option, ground-plane tip | concept image + final MP4, one panel, two steps |
| MCP | local server, tools above, copy-config for Claude Code (`claude mcp add --transport http`), Cursor (mcp.json), Claude Desktop (stdio shim) | agents build and generate in the open scene |
| Generations | `GET /jobs` history + local registry, filters by kind, thumbnails, actions per kind | import, apply, play, open folder |

Features intentionally moved to v2 with their Scenario equivalents: HDRI/skybox to World (`model_scenario-skybox-flux`, `model_scenario-skybox-gpt`, `model_hunyuan-world-image-to-skybox`), Remesh (`model_meshy-remesh`), UV unwrap (`model_meshy-uv-unwrap`, `model_tencent-uv-unwrapping`), Retexture (`model_meshy-7-retexture`, `model_tripo-v3-0-texturing`), Extract object (`model_meta-sam-3d-objects`), Body to 3D (`model_meta-sam-3d-body`), Auto-rig (`model_tripo-rigging-v1`, `model_meshy-rigging`), Character animation (`model_cartwheel-text-to-motion` with Blender FBX axes, `model_meshy-animation`, `model_uthana-video-to-motion-2.1` from a playblast), Scene Builder chat (agent backend needed), phone camera, realtime prerender, custom LoRAs (`runs_as: lora`), Workflows (`PUT /workflows/{id}/run`), OAuth sign-in.

## 5. UI

- N-panel tab "Scenario" in the 3D viewport sidebar. Top strip: project name, CU estimate of the current form, Preferences button, Refresh models. Lane tabs as an expanded enum row. Each lane: model dropdown (curated first, "All models" search field), prompt (single-line field plus an "Expand" operator opening a multi-line dialog), reference slots ("+ Add" menu: File, Viewport capture, Render result, Generations), schema parameters grouped as the record's `group`, Generate button with cost. Running jobs box with progress and Cancel. Generations list (12 per page) with thumbnail, model, status, actions.
- Viewport header button "Scenario" opening a popover with the same prompt + model + Generate (native floating equivalent, P0).
- Floating composer (P4): gpu/blf pill bottom-centre; hover expands; click pins; Esc collapses; single-line editor with caret, selection, clipboard; lane tabs; cost on Generate; shares the Scene properties.
- Preferences: credentials, project (read-only, resolved), output folder, composer on/off, MCP port and consent, log level, "Open log folder".

## 6. Testing and verification

- Unit tests run with system Python 3.13 (`pytest`), no bpy import: fake transport records requests and replays fixtures (`research/fixtures/patina-copper-512/*.json`, recorded job/asset/model records).
- Blender headless tests via `blender --background --python-exit-code 1 --python tests/blender/run.py`: register, catalog cache from fixtures, GLB import, Patina material graph, image apply, job registry persistence.
- Smoke (opt-in): one dryRun per lane, one tiny Patina run, budget logged; total dev spend cap about $30 (spent so far about $0.15).
- UI proof before "delivered": Blender GUI launched with the add-on, screenshots taken through the add-on's own MCP `screenshot_viewport` tool for each lane and the composer, saved under `~/Developer/scratch/playwright-screenshots/scenario-blender/`, and looked at.
- `blender --command extension validate` and `build` pass; install-file into `user_default` works on 5.1.1.

## 7. Delivery phases

- **P0 Skeleton + Image lane**: manifest, prefs, client, catalog cache, dryRun estimate, job manager, N-panel Image lane, image import, popover, build/install scripts, unit + headless tests.
- **P1 Materials + 3D + Generations**: Patina lanes and material builder, text/image/multi-view to 3D with cursor import, cloud history with thumbnails and actions.
- **P2 Render-to-real + Video**: capture (still + playblast), Video lane with Blender input and match-timeline, the two-step render-to-real panel, video playback.
- **P3 MCP server**: HTTP JSON-RPC server, Blender + Scenario tools, consent, copy-config UX, stdio shim, headless CLI command.
- **P4 Composer + distribution**: gpu/blf floating composer with breaker, extension repository index, README, CHANGELOG, help article draft.

Each phase ends with: tests green, headless checks, GUI screenshots reviewed, docs updated, one commit on main (merge --no-ff from the phase branch).

## 8. Open questions (not blocking v1)

- Whether the REST gateway accepts the MCP OAuth Bearer (unknown); matters only for v2 OAuth.
- No remaining-credit-balance endpoint found; the account strip shows month-to-date CU from `/usages` when the key has the scope, otherwise hides it.
- Patina `texture-smoothness` semantics inferred from pixels (dark = rough); confirm with Patina docs before final material defaults.
- Normal map convention (OpenGL vs DirectX) for Patina and each 3D provider: default OpenGL, expose a flip toggle.
