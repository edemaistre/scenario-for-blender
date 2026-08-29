# Model payload audit (2026-08-29)

Triggered by a real bug: **Rodin Hyper3D Bang** in the Retexture / Parts tasks refused to generate with
"Reference Image is required" even when a texture prompt was written, and the texture prompt looked missing.

## What was checked

`tools/audit_payloads.py` fetches the live schema (`GET /models/{id}`, free, no generation) for **every model the
plugin can put in front of a user**: the eight curated lane lists in `DEFAULT_MODELS`, every model in the six
`EDIT3D_TASKS`, and the Patina material models. It parses each one with the plugin's own `parse_schema` and checks:

- a file marked `required: true` whose own description reads conditional ("... if no prompt is provided");
- more than one required file input at once (the user would have to supply them all);
- a prompt that is really an alternative to a required file;
- edit3d / 3d models with no detectable mesh input (`kind: 3d`);
- required flags dropped by the parser;
- empty schemas.

Coverage: **68 surfaced models, 68 schemas fetched, 0 failures** after the id fixes below.

## Findings and fixes

### 1. Rodin Bang — conditional-required file (the reported bug) — FIXED

Bang's schema marks both `model` (the mesh) and `image` (the reference) as `required: true`, but the descriptions
make `image` and `prompt` mutually alternative:

- `image`: "Provide a reference image for generating model textures **if no prompt is provided**."
- `prompt` (label "Texture Prompt"): "Optional reference prompt to guide splitting **if no reference image is provided**."

The plugin was faithfully turning `required: true` into a hard requirement, so the valid prompt-only path was
blocked, and the block made the Texture Prompt look pointless.

Fix (general, self-maintaining from the schema, `core/schema/params.py`): a required file whose own description
reads conditional (`if no`, `if not`, `when no`, `unless`, `if none`) **and** which sits next to a prompt is relaxed
to optional, and the two are recorded as an either/or group (`Schema.one_of`). `validate` then requires **at least
one** of the group and, if neither is present, shows one friendly line: "Provide one of: Reference Image or Texture
Prompt". This affects exactly Bang today and will auto-handle any future model phrased the same way. Covered by
`tests/unit/test_params.py::test_conditional_required_file_becomes_either_or` and `::test_either_or_validation`.

### 2. Three curated ids that no longer resolve — FIXED

`DEFAULT_MODELS` named three models that 404 on the live catalog, so they silently never appeared. Replaced with the
current ids (verified against the catalog):

- `model_bytedance-seedream-5-0` -> `model_bytedance-seedream-5-0-lite` (the non-Pro tier; Pro was already listed)
- `model_google-veo-3-1` -> `model_veo3-1`
- `model_kling-3-0` -> `model_kling-v3-omni-video` (the current Kling V3 flagship, txt2video + img2video)

### 3. Correct by design (no change)

- **Trellis 2 Retexture** requires a mesh **and** a style image and has no text prompt: it is image-guided retexture,
  so requiring the style image is right. In the edit3d flow the mesh is auto-supplied and the user adds the image.
- **Meshy 7 Image-to-3D**'s required `image` is the source image ("Upload one image to convert into 3D"); its
  `texturePrompt` pairs with the optional `textureImage`, not with the required source. Correct as is.

## How to re-run

```
python3 tools/audit_payloads.py
```

Raw schemas cache under the system temp dir (override with `SCHEMA_CACHE`), so re-runs are offline. Delete a cached `<model_id>.json` to refetch it.
Run it whenever the curated lists or the catalog change; a new HIGH finding means a model's payload needs attention.
