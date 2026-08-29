# Scenario for Blender: UI style guide

The N-panel is drawn with Blender's `UILayout`, so it wears the user's Blender theme (colours, corner radius, fonts). We cannot change those; what we control is structure, spacing, wording and icons. This guide keeps the whole plugin coherent. The floating composer is custom gpu/blf drawing and mirrors the same language.

## Tabs and segmented choices

A row of mutually exclusive choices (lane tabs, picker modality tabs and category chips, Edit 3D tasks) is a **continuous segmented control**: cells touch (no gaps), each takes an equal share of the full width, and the icon sits next to its label with the pair centred in the cell.

- Use `panels.equal_segments(row, struct, prop, values)` (or `panels.draw_enum_tabs(layout, struct, prop, rows)` for multiple rows). It draws each value with `prop_enum` inside an `align=True` row (Blender merges the borders) and forces equal widths with a chain of even `split()`s.
- Never use `prop(..., expand=True)` for these (it pins the icon to the left edge) or `grid_flow` (it leaves gaps).

## Sections

Each group of controls is a `layout.box()` with a one-line header: `box.label(text="Title", icon=...)`. Order inside a lane: Model, Prompt, References, Settings, then the Generate button. Put `layout.separator(factor=0.5)` between the tabs and the form, and above the Generate button.

## Buttons

- The **Generate** button is the one primary action: `row.scale_y = 1.5`, icon `PLAY`, and it always shows the live price (`Generate (15 CU)` / `Generate (from N CU)` / `Generate (estimating...)`).
- Icon-only buttons keep Blender's fixed size; a button that must fill a row carries a short label (Blender never stretches an icon-only button). The three prompt tools are `New`, `Rewrite`, `Translate`.
- Destructive actions (`Delete`, `Clear path`) ask for confirmation (`invoke_confirm`).

## The model chooser

`Model:` then a wide button (icon + model name, centred in the bar via a split) opening the picker, with the native dropdown as a small fallback on the right. Its one-line description belongs in the picker, not the panel.

## Wording

- Verbs on buttons say exactly what happens: `Generate`, `Add to scene`, `Use as reference`, `Refresh cloud`, `Download and open`.
- Singular/plural is correct: `1 Job` / `3 Jobs`, `Applies to 1 selected mesh`.
- Costs are stated where credits are spent: a tooltip or an inline note (`Prompt Spark, up to 3.75 CU`).
- No internal names in user text (a person sees `Reference Images`, not `referenceImages`).

## Tooltips

Every operator sets `bl_description`: one sentence, action first, the cost when it spends credits. Blender adds the trailing period.

## Icons

Modality icons (image, video, audio, 3d) are Scenario's own PNGs (`scenario/icons/`, loaded by `blender/icons.py`, `icons.kwargs(name)` with a built-in fallback for headless). Section and action icons are Blender built-ins chosen to read at a glance.

## Status messages

`runtime.set_message(...)` lines are transient: `runtime.message_visible()` hides them after 8 s so a stale line never reads as current.

## What Blender cannot do (so we do not fake it)

- Text is left, centre or right aligned, never justified.
- A panel text field is single line; a taller prompt box grows the field, it does not wrap for editing.
- Dialogs and the sidebar cannot take the composer's custom colours; their layout follows this guide, their palette is the Blender theme's.
