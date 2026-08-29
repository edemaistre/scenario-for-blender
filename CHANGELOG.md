# Changelog

All notable changes to Scenario for Blender. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow semantic versioning and match `scenario/blender_manifest.toml`. Each version has a zip on the [releases page](https://github.com/edemaistre/scenario-for-blender/releases).

## [Unreleased]

Planned (see the spec, section 4, and `BUGS.md`): skyboxes applied to the World, remesh, UV unwrap, retexture, part segmentation, auto-rig, text-to-motion with Blender-axis FBX, custom LoRAs, Scenario Workflows, sign in with Scenario (OAuth), an in-Blender agent chat, drag and drop from Generations, a project switcher for team keys.

## [0.9.9] - 2026-08-29

### Fixed
- **Blockout from prompt no longer comes back empty.** The Scenario LLM's answer is read from the text asset, whose preview the API caps at ~1024 characters; a blockout plan is much longer, so it was cut off mid-element and failed to parse. The full content is now fetched from the asset URL when the preview is capped (`hasFullPreview` is false), and the parser also recovers the complete elements from a truncated array as a fallback. "room" now designs a full interior instead of failing.

## [0.9.8] - 2026-08-29

### Added
- **Prompt to Blockout is now its own tab** and a real scene-design system, not a box dropper. Describe a scene and the Scenario LLM designs a structured greybox: rich primitives (box, cylinder, plane, wedge/ramp, cone, sphere), rotation, and a semantic **category** per element (floor, wall, structure, prop, furniture, vegetation, vehicle, water, light) that sets its colour and its sub-collection. A scene-type and scale steer the layout. The flow is design -> review (a summary of element counts by category and group) -> build (grouped, colour-coded, in a "Blockout" collection) -> **refine** ("add a second floor", "taller tower") which re-designs from the current plan. Rebuild and Clear act on the stored plan without another LLM call. About 0.5 CU per design.

### Changed
- The old "Blockout from prompt" button in the 3D tab is replaced by the Blockout tab.

## [0.9.7] - 2026-08-29

### Added
- **Blockout from prompt** (3D tab): describe a scene and the Scenario LLM lays out a rough greybox as grey boxes in a "Blockout" collection, to refine by hand or replace with generated 3D assets one box at a time. About 0.5 CU. The layout is sanitised (sizes and coordinates clamped) so a bad answer never places a runaway cube.
- **Camera-path holds**: a shot can pause. Write "hold 2 s" (or "pause", "stay for 3 seconds") in the description and the camera holds on arrival; or select a Shot marker and set its "Hold (s)" field. The move steals the remaining time, so a held path still fits its duration.
- **Two MCP tools** for agents building scenes: `blender_api_help` (look up a bpy operator/type/collection's docstring and properties before writing Python) and `datablocks_summary` (counts of the objects, meshes, materials, etc. in the open file). Inspired by Blender's own blender_mcp project (GPL-3.0), written fresh.

## [0.9.6] - 2026-08-29

### Fixed
- **Enum settings no longer get stuck on "Loading..."** after opening a saved .blend. A parameter's choices (Minimax H3's Resolution and Aspect Ratio, and every other enum setting on every model) are kept in an in-memory cache that a saved file does not carry, so the dropdowns were empty until the model was re-synced. The dropdown now rebuilds its choices from the model schema on the spot when the cache is empty, so it is always populated.

## [0.9.5] - 2026-08-29

### Fixed
- **The selected scene mesh is now attached automatically** to a model's 3D character input (any lane), so a text-to-motion model like Uthana Text to Motion uses your mesh without hunting for a button. A selected mesh shows pinned as "Selected mesh: <name>"; deselect for a text-only generation, or Upload a model file to override. (Before, you had to click a button that was easy to miss, so generations ran without the mesh.)
- **Reload parameters** now restores the sub-selector that gates the model list: reloading a Meshy 7 Retexture (or any Edit-lane model) switches to the right Edit task, and a Generate-lane model switches to the right input mode, so the model, prompt and settings actually come back. The Edit-lane mesh is no longer restored as a stale asset (it comes from the current selection).
- The camera-path **Plan** button is clearer: it reads keywords (one move + seconds + lens), not AI; when several moves are named ("dolly in and then orbit") the first one written wins, so the result is predictable. Placeholder and tooltip updated.

### Added
- A **trash button** on the prompt to delete its text (greyed out when empty).
- **Collapse all / Expand all** for the generation list.
- **Full error messages**: a failed generation shows a red error control whose tooltip is the whole message (with the Error ID), and clicking it opens the full text with a Copy button, instead of a line cut off at 70 characters.

## [0.9.4] - 2026-08-29

### Fixed
- **The selected scene mesh now reaches models that take a mesh in any lane, not just the 3D Edit lane.** Text-to-motion and other `txt23d`/`img23d` models can carry an optional 3D character input (Uthana Text to Motion's "Character 3D model", `characterFile`, kind 3d); the plugin only auto-attached the selection in the Edit lane, so those inputs were silently ignored. A file input of kind 3D now offers **Selected mesh** and **Upload** (never an image capture); attaching the selected mesh exports it as GLB at generate time, the same as the Edit lane.
- The reference "Add" options now match each input's kind: a 3D input offers the mesh or an upload, an image input offers stills, a video input offers clips. Before, every input offered the same list (a viewport still could be attached to a 3D character input).
- Either/or inputs expressed as `required: {ifNotDefined: {...}}` are now parsed (Cartwheel Text to Motion: a 3D character mesh **or** a reference image). Neither is forced; the plugin asks for one of them.

### Changed (tests)
- Render Video duration tests updated to the 0.9.2 contract (the model's duration is the source; the base Video lane keeps deriving it from the timeline). These headless tests had been passing against a stale install and were re-verified against the built extension.

## [0.9.3] - 2026-08-29

### Fixed
- **Rodin Hyper3D Bang** (Retexture / Parts) no longer demands a reference image when a texture prompt is written. Its schema marks the reference image `required: true`, but the description makes it an alternative to the prompt ("... if no prompt is provided"). A required file whose own description reads conditional and which sits next to a prompt is now relaxed to optional, and the plugin requires at least one of the pair, showing one line ("Provide one of: Reference Image or Texture Prompt") only when neither is given. General and driven by the live schema, so it covers any future model phrased the same way.
- Three curated model ids that no longer resolve on the catalog (so they silently never appeared) were corrected: Seedream 5.0 (non-Pro) -> `model_bytedance-seedream-5-0-lite`, Veo 3.1 -> `model_veo3-1`, Kling -> `model_kling-v3-omni-video`.

### Added
- `tools/audit_payloads.py`: audits every surfaced model's live schema against the payload the plugin builds (required flags, either/or inputs, mesh detection, dropped params). Report in `docs/MODEL_PAYLOAD_AUDIT.md`. 68/68 models clean after the fixes, the one remaining note (Trellis 2 Retexture needs mesh + style image) is correct by design.

## [0.9.2] - 2026-08-29

### Changed (UI)
- **Model** is now a section like "Clip to render" and "Camera path": a boxed header with an icon, then the wide "Choose a model" button and the fallback dropdown.
- **Settings** header carries an icon, matching the other sections.
- **Rendering Style** is a plain section (an icon and the title): the chevron and the collapse are gone, it is always open.

### Changed (duration)
- The video model's **Duration (cost)** in Settings is the single source of the clip length for Render Video. With **Match timeline** on, the camera path's **Duration (s)** follows it automatically and is read-only, with a note under the planner ("The clip is captured at X s to match the video duration"). With Match timeline off, the two are edited separately.
- The base **Video** lane keeps the reverse direction (the model duration follows the scene frame range); only Render Video was flipped.
- Removed the now-backwards "Clip padded/trimmed for the model" note from the Render Video "Clip to render" box; the camera-path note states the captured length instead.

## [0.9.1] - 2026-08-29

### Changed (UI)
- Lane tabs and the picker tabs are continuous full-width segmented controls whose cells fill each row (a row of two cells is wider than a row of three); the icon and label are Blender's own for the enum.
- **Rendering Style** header now matches "Clip to render" and "Camera path" (an icon and the title on the left, the triangle collapses it).
- A boolean setting is a single checkbox (the enable + value pair read as two toggles); it is always sent.
- The look toggle is one line, "Write the look with Prompt Spark", with the 0.75 CU detail in its tooltip; the long inline sentences under the look and in the camera-path planner are gone (hover a control for its tooltip).
- The camera-path description field carries placeholder text; the reference lists in Rendering Style are drawn flat (no boxes nested inside the section).
- Match timeline no longer prints a redundant "Video duration, same as the clip" line; it only notes padding or trimming.
- **Clear path** asks "Clear the camera path?" with a Clear button, not Replace.

### Fixed
- **The audio reference input is back** in the render lanes (it was hidden with the other non-image inputs).

## [0.9.0] - 2026-08-29

First release-candidate pass: a coherent UI and a production-readiness sweep of the code.

### Changed (UI)
- Every row of choices (lane tabs, the model picker's modality tabs and category chips, the Edit 3D tasks) is one **continuous segmented control**: cells touch, each takes an equal share of the full width edge to edge, and the icon is glued to its label with the pair centred in the cell.
- Consistent spacing: a separator between the tabs and the form and above the Generate button, which is the single prominent action (larger, always priced).
- Clearer wording: the account strip reads "Connected" instead of a second "Scenario"; the video clip box is "Scene clip".
- A **UI style guide** (`docs/UI_STYLE.md`) codifies the tab, section, button, wording, tooltip and icon conventions so the plugin stays coherent.

### Fixed (robustness, from an audited review)
- **MCP `estimate_cost` and `wait_for_job` no longer run on the HTTP thread**: they read Blender data (preferences, paths, the job manager), so they now go through the main-thread executor. This also removes an off-thread mutation of the shared model cache.
- **A corrupt catalog cache no longer wedges the add-on** in a permanent retry loop: `load_list_cached` and `get` treat an unreadable cache as a miss and re-fetch.
- **The floating composer's circuit breaker** no longer removes its own draw handler or writes preferences from inside a draw callback; the teardown is deferred to a timer.
- The **Log Level** preference now actually sets the logging level.

### Security
- **The MCP "run Python" permission is off by default.** Connected agents keep the fifteen read and scene tools; running arbitrary `bpy` code is now a deliberate opt-in.

### Removed (dead code)
- The archived render-to-real prompt helper and its constants; the unused operators `scenario.set_lane` and `scenario.use_first_frame`; the unused helpers `is_render_lane`, `is_video_output`, `modality_icon`, `_sh_dim`, `order_image_inputs`; the unused `generate_audio` property; three stray imports; the "Edit prompt" dialog. The lane-to-kind map, previously copied in four places, now lives once in `core/api/catalog.py`.

## [0.8.3] - 2026-08-29

### Changed
- **Tabs and buttons fill the width, icon glued to the label, centred in each cell**: every tab row (the lane tabs, the model picker's modality tabs and category chips) is now justified full width, and inside each cell the icon sits right next to its word with the pair centred. The model button centres its icon and name in the bar. The three prompt tools ("New", "Rewrite", "Translate") fill the prompt box evenly.
- **Prompt box**: the prompt lives in the field (no duplicated wrapped copy underneath); drag the small size control in the header to make the box taller. The "Edit prompt" dialog is gone.
- **Rendering Style** section on Render Image and Render Video: one collapsible box that holds the look prompt, the Prompt Spark options, the video first frame and the style images, so the style images are easy to find. "Look" is now inside it.
- Render Video: "Last Frame" and the "No first frame..." hint are gone; the model's own first/last-frame inputs are handled by the Rendering Style section, only the reference frames (style images) are offered.
- The floating composer's minus button is a full tab-height cell aligned with the tab row.

### Fixed
- The Prompt Spark, Rewrite and Translate buttons were unresponsive after the 0.8.2 restyle (a centred, scaled row swallowed the clicks); they are plain buttons again.

## [0.8.2] - 2026-08-29

### Changed
- **Tabs with the icon glued to the text, centred**: the lane tabs (Image / Video / 3D, Audio / Materials, Render Image / Render Video) and the model picker's modality tabs and category chips are compact centred groups, like Scenario's web app, instead of full-width buttons that pin the icon to the left edge.
- **Prompt box**: the prompt is a box of its own (a "Prompt" header, the full-width field, the long prompt wrapped underneath so it stays readable, and the three tool buttons as a row of equal squares), in every lane and in the settings dialog.
- Prompt tool icons redrawn (one die with five dots, a clean sparkle, 文A) at a weight that reads at 16 px; the modality icons follow the same stroke.
- Model picker: breathing room under the title, tabs and chips centred, wider list.
- Generations: the header shows "Output folder" and "Refresh cloud" as two equal buttons and the cloud toggle is a labelled checkbox; a cloud entry that also exists locally is drawn like a session entry (same actions), so "Bring into scene again" is gone; image actions are View image, Use as reference (3D image to 3D, Image, Video, Render Image style, Render Video style), Remove background, Apply as texture, Add as plane.
- Jobs header reads "1 Job" / "3 Jobs".

## [0.8.1] - 2026-08-29

### Added
- **Gaussian splat worlds load into Blender**: Marble and HY World return `.spz` files (Niantic's compressed splat format, 2.3 million splats for a Marble world), which Blender cannot open. A pure-Python SPZ reader turns them into a coloured point cloud (a mesh of splat centres with a colour attribute and a Geometry Nodes "points" modifier sized from the splat scales), Y-up converted to Z-up, subsampled to one million points for interactivity. Worlds downloaded before this version as `.bin` are recognised by content, so "Add to scene" works on them too. `.ply` results go through Blender's PLY importer.
- **Image actions** in Generations: **View image** (was "Show") now shows the whole image instead of the editor's previous zoom; **Convert to 3D** opens the 3D tab in Image mode with the picture attached; **Use as reference** sends it to the Image, Video, 3D, Render Image or Render Video lane; **Remove background** runs a background removal model on it (Bria, 851 Labs, Photoroom, Ideogram...), the cut-out lands in Generations.
- **Reload parameters** (the refresh button on a generation): lane, model, prompt, every setting sent, and the references (local files, else asset ids) come back into the form.
- **Generation settings from the composer**: the Settings chip opens a dialog with the current lane's full form (model, prompt, references, parameters) right where the composer is, instead of only revealing the sidebar. Opening the sidebar tab also retries when Blender refuses the tab switch on the first draw.

### Changed
- Composer card: no empty band under the buttons (height fits the three rows); the corner grip is gone, the corner shows a resize cursor and a light mark only when the pointer reaches it.

## [0.8.0] - 2026-08-29

### Added
- **Movable, resizable composer**: drag the card (or the collapsed pill) anywhere in the viewport, resize the card from its corner grip, double-click the background to reset; the position is remembered in the preferences.
- **Camera path from editable markers**: a preset now places numbered `Shot` markers around the subject (Place markers), the path is always built from the markers, so a move from the library can be adjusted marker by marker. A `Closed loop` option (on for orbits and ellipses) brings the camera back exactly to its first marker. `Clear path` removes the camera, target and markers; placing or building over an existing path asks for confirmation first. Duration, focal length and start frame are labelled and the resulting frame range is shown.
- **Delete** next to Select on 3D results: the objects a generation created are stamped with its id on import, so Select and Delete find them after renames and re-imports.
- Prompt tools with Scenario's icons (dice, sparkles, translate) and their tooltips ("Generate a new prompt", "Rewrite your prompt", "Translate to English").

### Fixed
- **Camera clip captures were always grey clay**, whatever the viewport showed: rendering "through the camera" used the scene's Workbench settings. Captures now go through the viewport in camera view, so Material Preview and Rendered shading come along; Grey clay capture still forces flat shading when checked.
- **Video duration and clip length are synchronised** for models with a numeric duration range too (Minimax H3: 5 to 15 s). Match timeline sets the duration from the clip (rounded up, clamped), the duration field is locked while it drives, the clip box states "Video duration 6 s, same as the clip" or the padding/trimming applied, and the playblast is padded or cut to that exact duration.
- Rewrite / Spark could put an `asset_…` id in the prompt: Prompt Spark answers with asset references for some models. Real text assets are resolved to their text, unusable answers fall back to the Scenario LLM, and an `asset_` string never reaches the prompt field.
- "Edit prompt (undocumented operator)" and eleven other tooltips: every operator has a description.
- Status lines ("Submitted to Meshy 7") disappear after eight seconds instead of staying until the next one.

### Changed
- Lane tabs laid out as Image / Video / 3D, Audio / Materials, Render Image / Render Video. The model description line left the panel (the picker shows it).
- Generation details opens with the same header as a Generations entry (type icon, prompt, cost, model) and a copy button for the prompt.

## [0.7.0] - 2026-08-29

### Added
- **Audio lane**: speech, music and sound effects (ElevenLabs Music v2, Lyria 3, ACE-Step 1.5, Minimax Music 3.0, ElevenLabs 3, Gemini 3.1 Flash TTS, ElevenLabs Sound Effects 2, Sonilo, and every txt2audio / audio2audio / video2audio model). Results play from Generations or drop on the sequencer as a sound strip at the current frame.
- **Prompt tools** next to every prompt: Spark (Prompt Spark writes a prompt for the selected model, 3.75 CU), Rewrite (Prompt Spark improves the current prompt, 3.75 CU), Translate (to English with the Scenario LLM, 0.5 CU). Runs in the background, the prompt field updates when the answer arrives.
- **Camera movement library**: 20 moves in five groups. Orbits (orbit, orbit high, orbit low, spiral in), Ellipses (three variants), Dolly & truck (dolly in / out, truck left / right, pedestal up / down, zoom in), Crane & arcs (crane, arc left / right, top down), Other (pan, flyover). Every orbit and ellipse returns exactly to its starting point. The Plan field understands the new words (ellipse 2, dolly in, truck left, low angle, top down...).
- **Model picker with Scenario's taxonomy**: modality tabs (Image, Video, Audio, 3D) with Scenario's icons and the web app's category chips (Image: Generate, Edit, Expand, Upscale, Vectorize, Remove Background, Tools; Video: Generate, Edit, Lipsync, Upscale, Reframe, Remove Background, Tools; Audio: Speech, Music, SFX, Tools; 3D: Generate, Splat, Remesh, Retexture, UV Unwrap, Rigging, Animate, Parts). Picking a model of another modality switches to that lane. The same icons sit on the lane tabs.
- Generations entries are collapsible (arrow, then only the type icon and the start of the prompt), show the model, the asset id (one click copies it) and a failure marker; a Details dialog (the info button) lists the prompt, the settings sent, the references with their asset ids, the result assets and the files. The inputs strip is gone: only the output thumbnail is shown.
- Downloaded files carry the Scenario asset id in their name: `20260828_230353_hitem-3d-split_asset_ccpDR7Ga1…_00.glb`.

### Changed
- **No Scenario LoRAs in any list** (160 trained models: Flux LoRAs, compositions, Kontext LoRAs). The lists hold the third-party models and Scenario's tools.
- **Edit 3D moved under the 3D tab** as a fourth mode (Text, Image, Multi-view, Edit); the task tabs use Scenario's names (Remesh, Retexture, UV Unwrap, Rigging, Animate, Parts). Rodin Hyper3D Bang! sits in Parts and Retexture; Tripo Stylization and Hitem3D Multicolor in Retexture.
- GPT Image 2 is the default model of Render Image. Parameters that belong to an input the lane hides (Gemini's video frame rate) are hidden and not sent.
- Image lane also lists video-to-image models; Video lane also lists audio-to-video models (LTX Audio to Video).
- Composer: the collapsed pill uses the card's style (same fill, corners, field and button) with a centred Generate; tabs read "Render Image" / "Render Video"; the card is wider.
- MCP `generate` accepts the `audio` lane; `camera_path` accepts the new preset names (old `push_in` / `pull_back` still resolve).

### Still not reachable from Blender
- Video-to-motion (Cartwheel, Uthana), speech-to-text and the Scenario LLM as a standalone model (it powers Translate). Everything else in the public catalog (462 live non-LoRA models) appears in at least one lane.

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
