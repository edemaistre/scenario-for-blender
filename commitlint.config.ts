// Single source of truth for commit headers and PR titles.
// Types come from @commitlint/config-conventional; the scope list below is the
// one the contributor guide mirrors. Node is never part of the checkout: CI
// installs commitlint ad hoc (see .github/workflows/pr-name.yml and
// .github/workflows/commitlint.yml). To run the same check locally:
//
//   npm install --no-save --no-package-lock --no-audit --no-fund @commitlint/cli@21 @commitlint/config-conventional@21 @commitlint/types@21
//   printf '%s\n' "feat(ui): my title" | npx --no-install commitlint --config commitlint.config.ts --verbose

import type { Plugin, UserConfig } from "@commitlint/types";

// U+2014 written as a code point so that this file contains no em dash itself.
const EM_DASH = String.fromCharCode(0x2014);

const houseRules: Plugin = {
  rules: {
    // House style: no em dashes anywhere, commit messages and PR titles included.
    "no-em-dash": ({ raw }) => [
      !(raw ?? "").includes(EM_DASH),
      "no em dashes in commit messages or PR titles (house style, see CONTRIBUTING.md)",
    ],
  },
};

const config: UserConfig = {
  extends: ["@commitlint/config-conventional"],
  plugins: [houseRules],
  rules: {
    // Allow longer headers than the 100-character default (same as the sibling repos).
    "header-max-length": [2, "always", 120],
    // Off: long URLs and Co-Authored-By trailers exceed the 100-character default.
    "body-max-line-length": [0, "always", 200],
    "footer-max-line-length": [0, "always", 200],
    // Off: Blender, Rodin, Patina, MCP and GLB start many subjects.
    "subject-case": [0],
    // Warn, never fail: the release-please PR is "chore: release X.Y.Z" with no scope.
    "scope-empty": [1, "never"],
    "scope-enum": [
      2,
      "always",
      [
        "core", // scenario/core cross-cutting: config.py, history.py
        "api", // scenario/core/api: REST client, catalog, generate, jobs endpoints, llm, spark
        "jobs", // scenario/core/jobs: manager, records
        "scene", // scenario/core/scene: blockout, capture plan, material plan, placement, render prompt, shot plan, spz
        "schema", // scenario/core/schema
        "blender", // scenario/blender bpy glue: operators, props, apply_*, handlers, pump, registry, runtime, prefs
        "ui", // panels, params_ui, popover, model picker, prompt tools, icons, docs/UI_STYLE.md
        "composer", // scenario/blender/composer and scenario/core/ui/composer_layout.py
        "mcp", // scenario/mcp and scenario/blender/mcp_service.py
        "tests", // test harness only; a test for a product area keeps the product scope
        "tools", // tools/ and the Makefile
        "docs", // README.md, docs/, the user guide source
        "ci", // .github/workflows, rulesets, hooks
        "deps", // pins: Blender versions in CI, action versions
        "release", // release-please config and manifest, version fields, CHANGELOG plumbing
        "agents", // AGENTS.md, CLAUDE.md, .claude/
        "repo", // LICENSE, CODE_OF_CONDUCT, SECURITY, templates, CODEOWNERS
      ],
    ],
    "no-em-dash": [2, "always"],
  },
};

export default config;
