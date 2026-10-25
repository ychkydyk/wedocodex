# Alternatives and positioning

Research checked on 25 October 2026. This is a capability comparison based on primary documentation, not a competitive performance benchmark.

| Tool | Main mechanism | Relationship to WEDOCODEX |
|---|---|---|
| [Native Codex profiles](https://learn.chatgpt.com/docs/config-file/config-advanced#profiles) | Named TOML layers and CLI overrides | The underlying mechanism already exists. WEDOCODEX adds packaged task presets, workflow instructions, previews, safe installation management and measurements. |
| [Ultra Config, Daniel (San) Ávila](https://dev.to/dani_avila7/ultra-config-switches-your-whole-claude-code-setup-between-five-profiles-mid-session-4199) | Five Claude Code profiles, an interactive pane, settings apply and undo | The direct inspiration. Its Claude integration and pane are more integrated than our tested Codex IDE path. We adapted supported settings to a different host; this is not a claim of outperforming the original. |
| [RTK](https://github.com/rtk-ai/rtk) | Filters, groups, truncates and deduplicates shell-command output | A more focused solution for verbose command output. WEDOCODEX does not implement equivalent command-aware compression. It could be complementary, but integration has not been tested. |
| [context-mode](https://github.com/mksglu/context-mode) | Executes work outside the prompt, indexes raw output and restores session context through MCP and hooks | More extensive retrieval and continuity infrastructure. WEDOCODEX has no such index or output sandbox. Our setup needs no extra MCP service or routing hooks. |
| [Claude Code Router](https://github.com/musistudio/claude-code-router) | A local provider/model gateway with routes, fallbacks, credentials and usage logs, including Codex support | Useful for multiple providers and routing. WEDOCODEX keeps the existing Codex connection and does not add a gateway or manage provider credentials. |
| [Ralph Wiggum plugin](https://github.com/anthropics/claude-code/tree/main/plugins/ralph-wiggum) | A stop-hook-driven iterative loop with completion conditions and iteration limits | An actual loop mechanism. WEDOCODEX Autopilot is a workflow preset inside an open Codex session, not a replacement loop engine or daemon. |

## What is demonstrated here

- A same-requested-model file benchmark: four pairs, eight fresh sessions, all expected answers correct, 23.1% fewer total tokens.
- Independent accounting of input, cached input, output and reasoning; no claim that a subscription counter changed because of one chat.
- Local Windows CLI discovery without PATH, plus verified installation conflict detection, backup, rollback and extracted-package checks.
- Explicit separation of behavioral activation, startup settings and partial live settings control.
- Saver and Autopilot can be combined without selecting a different model silently. A live smoke test checked both its result and checkpoint output.

These are properties of the tested build, not proof that every alternative lacks them. Native Codex profiles alone may be sufficient for experienced users who prefer to maintain their own configuration.

## What we have not demonstrated

We have not run RTK, context-mode, Ultra Config or other tools on the same fixtures. Therefore we cannot claim better savings, quality or speed than those projects. RTK's headline savings and context-mode's payload-reduction benchmarks use different workloads and denominators from our total model-token accounting. Their percentages should not be compared numerically with our 23.1% result.

WEDOCODEX has not been verified on macOS/Linux, on large production repositories, or through a public plugin-directory installation. Its tested IDE did not expose the proxy needed for live attachment. Guarded is not secret isolation. Autopilot does not send external messages or keep running after Codex closes.

## Practical next evaluation

Use the same repository snapshot, model, effort, task, cache treatment and correctness checks across default Codex, WEDOCODEX, RTK, context-mode and selected combinations. Include verbose build/test logs and long multi-turn work. Report failed runs and output-quality regressions, not only token totals. That is the test needed before making a superiority claim.
