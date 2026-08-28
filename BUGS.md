# Known issues and deferred review findings

Source: 36-agent adversarial review of P0+P1 on 2026-08-28 (31 confirmed findings; 29 fixed in the 0.5.0 review passes). Open items:

- **Headless tests touch the user's real extension state** (tests/blender/test_history.py and friends use the installed extension's preferences and `jobs.json`). A GUI Blender with a generation in flight could see its record failed by a test run. Fix: pre-seed `runtime.state.manager` with a temp-dir JobManager in tests and never write preferences.
- **Environment credentials silently override the Preferences key** (`SCENARIO_API_KEY` / `SCENARIO_API_SECRET`). Intended for dev and CI, but the panel does not say which source is active. Fix: show "key from environment" in the account strip and require the full pair for the override.
- **Non-curated model records load in the background**: the parameter form shows "Loading the model description..." for a second after picking such a model; a very slow network leaves the form empty until the record arrives (no retry button yet).
- Composer text editing is single-line; long prompts scroll horizontally (the pencil button in the N-panel opens a wider editor).
- Playblast captures need the Blender GUI; the MCP `render_still` and `screenshot_viewport` tools report an error in `--background` mode.
- No project switcher for team-scoped API keys (a project key is assumed; team keys need `?projectId=`, not sent yet).
- **Automated GUI checks steal keyboard focus**: `tools/gui_screenshot.py` opens a real Blender window for about 15 s; two accidental generations happened when keystrokes landed in it. The tool now sets `SCENARIO_GUI_PROBE=1`, which disables every Generate path; still, avoid running GUI checks while typing on the machine.

Added with 0.6.0 (2026-08-28):

- **MCP `generate` bypasses the render prompts**: an agent generating in `render_image` / `render_video` through MCP sends its own prompt and asset ids; the role-explicit prompt and Prompt Spark only run from the panel and the composer. Fix: a `render` MCP tool that reuses `render_lanes.decorate`.
- **Prompt Spark runs in generic mode** (0.75 CU, no `modelId`) with our own brief; the model-contextual mode (3.75 CU) is not exposed. A preference could offer it.
- **Model picker fallback**: a model found only through the full records list (not in the lane's enum) is stored as `model_key`, its schema requested, and the dropdown catches up when the enum contains it.
- **Shot markers are small cameras**, not cone empties: the camera frustum shows the direction and its lens is the zoom level. With Aim at subject on, marker orientations are ignored (Track To wins).
- **Edit 3D exports the whole selection as one GLB**; multi-object selections come back as one mesh from most providers.
- **Composer tabs stop at six lanes**: Edit 3D is sidebar-only (its input is the selection, not a prompt).

Added with 0.7.0 (2026-08-29):

- **Audio results have no waveform preview** in Generations (Play and Add to sequencer only); the sequencer strip carries the file name.
- **Prompt tools price**: Spark and Rewrite use Prompt Spark's model-contextual mode (3.75 CU per click); the Render lanes' empty-look path stays on the generic mode (0.75 CU). A preference could let the user pick.
- **Video-to-motion, speech-to-text and the standalone Scenario LLM have no lane** (Cartwheel / Uthana video to motion take a video and return FBX motion; a "Motion" mode under 3D is the natural home).
- **Model categories come from tags and names**; a third-party model with no category tag falls into Generate. The mapping lives in `core/api/model_filter.py` and should be checked when the catalog adds a category.

Added with 0.8.0 (2026-08-29):

- **Native dialogs and the sidebar cannot take the composer's look**: Blender draws them with the user's theme (colours, corner radius, fonts). The composer is custom gpu/blf drawing. Layouts were aligned (tabs, chips, header rows); colours will differ unless the user picks a matching Blender theme. A fully custom picker would mean re-implementing list scrolling, search and thumbnails in gpu/blf.
- **Prompt Spark for 3D models** answers with placeholder ids (`asset_cuteLowPolyRobot`) instead of text; the LLM fallback covers it, so Spark and Rewrite on Meshy-style models cost 0.75 + 0.5 CU.
- **Capture fps** is the scene fps; there is no separate capture frame rate yet (the box shows the fps used).
