# Known issues and deferred review findings

Source: 36-agent adversarial review of P0+P1 on 2026-08-28 (31 confirmed findings; 29 fixed in the 0.5.0 review passes). Open items:

- **Headless tests touch the user's real extension state** (tests/blender/test_history.py and friends use the installed extension's preferences and `jobs.json`). A GUI Blender with a generation in flight could see its record failed by a test run. Fix: pre-seed `runtime.state.manager` with a temp-dir JobManager in tests and never write preferences.
- **Environment credentials silently override the Preferences key** (`SCENARIO_API_KEY` / `SCENARIO_API_SECRET`). Intended for dev and CI, but the panel does not say which source is active. Fix: show "key from environment" in the account strip and require the full pair for the override.
- **Non-curated model records load in the background**: the parameter form shows "Loading the model description..." for a second after picking such a model; a very slow network leaves the form empty until the record arrives (no retry button yet).
- Composer text editing is single-line; long prompts scroll horizontally (the pencil button in the N-panel opens a wider editor).
- Playblast captures need the Blender GUI; the MCP `render_still` and `screenshot_viewport` tools report an error in `--background` mode.
- No project switcher for team-scoped API keys (a project key is assumed; team keys need `?projectId=`, not sent yet).
