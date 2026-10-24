---
name: wedocodex
description: "Configure WEDOCODEX modes in Codex: Token Saver, Fast Flow, Max Quality, Guarded and Autopilot. Use for explicit mode/configuration requests; discussing or reviewing a mode does not activate it."
license: MIT
---

# WEDOCODEX

Resolve `scripts/wedocodex.py` relative to this file. Python 3.11+; runtime verified with Codex 0.162.0-alpha.17.2. Do not read the implementation or every reference merely to select a mode.

| Mode | Default runtime | Working behavior |
|---|---|---|
| token-saver / saver | Luna / low; catalog 2000, output history 6000 | Concise, targeted reads; deterministic routines; no automatic agents |
| fast-flow / flow | Sol 6.1 / medium; workspace-write, never escalation | Finish authorized work with few interruptions; denied actions stay denied |
| max-quality / quality | Astra / max; catalog 10000 | Verify consequential assumptions; no automatic delegation |
| guarded | Sol 6.1 / medium; read-only | Audit only, including external tools; propose changes without applying |
| autopilot | Sol 6.1 / medium; recap and terminal notifications | Continue the authorized task; brief timestamped checkpoints at milestones |

For bare activation show these choices. For a named activation adopt its behavior and continue the user's task. State that behavior changed; never claim a model/effort/permission switch from text alone. Later activation replaces the mode, not the task or approvals.

Use the launcher only when the user requests runtime configuration or a CLI launch:
```
python <skill-dir>/scripts/wedocodex.py preview saver --workspace <project>
python <skill-dir>/scripts/wedocodex.py run saver --workspace <project>
```
No second session without a launch/resume request. Explicit `--model` and `--effort` overrides are supported; never silently substitute a model. Catalog presence is not account entitlement.

For an existing idle session, prefer native `/model`, `/permissions`, `/status`. Where a local Codex App Server proxy is available, `live-preview MODE --thread UUID`, `live-apply MODE --thread UUID`, and `live-undo --thread UUID` provide readback and conflict-aware undo. Use the exact user-selected/current verified UUID and matching workspace, never guess or choose the latest session. Report blocked and restart-required fields. A partial live update is not full profile activation; Guarded is not effective unless actual permissions confirm it.

Limits apply at startup. A smaller discovery catalog may omit skills from initial suggestions; explicit skills remain available. Guarded is not secret isolation, and shell restrictions do not technically block every connector mutation. Terminal notifications are not mobile push. Do not disable unrelated plugins, rewrite AGENTS.md, create schedules, or launch external agents as a mode side effect.

For installation management use `install`, `update`, `uninstall`, `recover`; preview changes with `--dry-run`. Update from the new unpacked package. User edits block replacement/removal; history stays in CODEX_HOME. Do not remove a stale lock before verifying its installer has stopped.

For exact upstream parity and unsupported settings, read [the mapping](references/ultra-config-map.md). For savings claims use per-request input, cached-input, output and reasoning metrics plus correctness. Total context reduction is not automatically a billing or speed guarantee.
