# Scenario for Blender P4 Implementation Plan (floating composer + distribution)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The [redacted]-style "type in the viewport and generate" feel: a gpu/blf floating composer pill at the bottom centre of every 3D viewport, sharing the lane state with the N-panel, with a circuit breaker so a drawing bug can never freeze Blender. Plus a Scenario-hosted extension repository build so updates flow through Blender's own updater.

**Architecture:** `scenario/core/ui/composer_layout.py` is pure Python (geometry, hit-testing, text editing with caret and selection, word wrap) and unit-tested. `scenario/blender/composer/draw.py` draws with `gpu` built-in shaders and `blf` in a `POST_PIXEL` handler using cached batches. `scenario/blender/composer/modal.py` is a modal operator that only runs while the pointer is inside the pill or the pill has focus, passing every other event through. `scenario/blender/composer/breaker.py` disables the surface after 5 consecutive failures or one draw over 2 s and shows a "re-enable" toggle in preferences. Distribution: `tools/build_repo.sh` runs `blender --command extension server-generate` into `dist/repo/` with `index.json` + zips.

**Spec:** `docs/superpowers/specs/2026-08-28-scenario-for-blender-design.md` (3.1 `ui/composer/`, 5 UI, 2 distribution)

## Global Constraints

Same as the P0 plan, plus:
- Never block the main thread in draw handlers: no network, no file IO, no schema parsing inside `draw()`. All state comes from `runtime.state` and the Scene properties.
- Every size is multiplied by `preferences.system.pixel_size * preferences.view.ui_scale`. Colours come from the current theme where possible (`context.preferences.themes[0].user_interface`), with a Scenario accent for the Generate chip.
- The handler is removed on unregister, on file load (`load_pre` handler) and when the breaker trips. The preference `composer_enabled` gates it.
- Branch `p4-composer-distribution`, merge `--no-ff` into `main` at the end.

---

### Task 28: Composer layout and text editing (pure Python)

**Files:** `scenario/core/ui/__init__.py`, `scenario/core/ui/composer_layout.py`, `tests/unit/test_composer_layout.py`

**Interfaces:**
- `TextField(text="", caret=None)` with `.insert(s)`, `.backspace()`, `.delete()`, `.move(delta)`, `.home()`, `.end()`, `.select_all()`, `.selection -> (a, b)|None`, `.replace_selection(s)`, `.visible_slice(width_chars) -> (start, end)` keeping the caret visible.
- `Layout(width, height, scale)` producing rectangles for the collapsed pill (`pill_rect`), expanded card (`card_rect`), lane tabs (`tab_rects: dict[lane, rect]`), prompt box, model chip, reference chips, Generate button; `hit(x, y) -> ("tab", lane) | ("prompt",) | ("generate",) | ("model",) | ("collapse",) | None`; `Rect(x, y, w, h).contains(px, py)`.
- `pill_placement(region_w, region_h, expanded, scale) -> Layout` anchored bottom centre with 24 px margin.

Tests cover caret movement and editing, visible slice, hit testing of every element, and that all rects stay inside the region.

### Task 29: gpu/blf drawing with cached batches and the circuit breaker

**Files:** `scenario/blender/composer/__init__.py`, `draw.py`, `breaker.py`, `tests/blender/test_composer_breaker.py`

- `breaker.Breaker(failures=5, stall=2.0, on_trip)`: `.guard(fn)` runs `fn`, times it, counts consecutive exceptions; trips once and calls `on_trip(reason)`; `.reset()`.
- `draw.draw_composer(context)`: reads `scene.scenario`, computes `Layout`, draws rounded rectangles (`UNIFORM_COLOR` shader, triangle fans per corner, batches cached per size), text with `blf` (font id 0, size from scale), the prompt text with caret when focused, the lane tabs, the model chip (model name), the Generate chip with the CU text from `panels.generate_button_text`, and the estimate/error line. Hover states come from `runtime.state.composer` (`hover`, `focused`, `expanded`, `mouse`).
- `draw.register()/unregister()` add/remove the `SpaceView3D.draw_handler_add(..., 'WINDOW', 'POST_PIXEL')` and a `load_pre` handler that removes it.
- Headless test: the breaker trips after 5 failures and after a 2.1 s call (fake clock), `on_trip` called once; `draw_composer` is importable and `Layout` math is exercised with a fake region size (drawing itself is GUI-only and is verified by screenshot).

### Task 30: Modal interaction and focus

**Files:** `scenario/blender/composer/modal.py`, `scenario/blender/composer/state.py`, `tests/blender/test_composer_state.py`

- `state.ComposerState` (in `runtime.state.composer`): `expanded`, `focused`, `hover`, `mouse`, `field: TextField` mirrored to `lane_state.prompt` on every edit (and refreshed from it when the lane changes), `last_click`.
- `SCENARIO_OT_composer_modal` starts from a `MOUSEMOVE` keymap entry in the 3D view (`keymaps.addon`, tolerant of `None` in background) when the pointer enters the pill; while running: hover updates and `tag_redraw`, `LEFTMOUSE` press resolves `layout.hit`: tab -> set lane, model -> open the N-panel Scenario tab (`space.show_region_ui = True`), prompt -> focus, generate -> `bpy.ops.scenario.generate(lane=...)`, collapse -> collapse; typing while focused edits the field (`event.unicode`, `BACK_SPACE`, `DEL`, `LEFT_ARROW`, `RIGHT_ARROW`, `HOME`, `END`, `ctrl+A/V` via `window_manager.clipboard`), `RET` generates, `ESC` blurs or collapses; leaving the pill without focus ends the modal (`FINISHED`) so other tools work; all other events `PASS_THROUGH`.
- Headless test: state mirrors prompt edits into `lane_state.prompt`; lane switch reloads the field; `TextField` and layout hit tests through the state helpers.

### Task 31: Preferences toggle, GUI proof, extension repository, docs, merge

- `prefs.composer_enabled` toggles the handler live (update callback); breaker trip flips it off with a message and the preference shows "Composer disabled after an error, re-enable".
- GUI proof: `tools/gui_screenshot.py` screenshots of the collapsed pill and of the expanded card with a typed prompt (add action `composer` that sets `runtime.state.composer.expanded = True` and the field text), reviewed.
- `tools/build_repo.sh`: builds the zip (`tools/build.sh`), then `blender --command extension server-generate --repo-dir dist/repo --html`, copies the zip into `dist/repo/`, prints the `index.json` URL to host (any static host; the user adds it once in Preferences > Get Extensions > Repositories with "Allow Online Access").
- README: "Install from the Scenario repository" section, composer usage, keyboard shortcuts; CHANGELOG `0.5.0 (P4)`; CLAUDE.md state. `make test && make test-blender`, merge `--no-ff` into main, tag `v0.5.0`.

## v2 backlog (from the spec, not in this plan)

Skyboxes to World, remesh, UV unwrap, retexture, segmentation, auto-rig, text-to-motion (Cartwheel FBX), custom LoRAs (`runs_as: lora`), Workflows runner, OAuth sign-in via mcp.scenario.com (dynamic registration validated), in-Blender agent chat, drag-and-drop from Generations via AssetShelf, project switcher for team keys, realtime prerender, phone camera.
