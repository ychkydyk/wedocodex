---
name: wedocodex
description: Select WEDOCODEX working modes when asked to configure Codex for token savings, fast flow, max quality, guarded review, or autopilot. Separate working style from real model and permission settings. Reviewing this skill or asking about a mode does not activate it.
---

# WEDOCODEX

Resolve `scripts/wedocodex.py` relative to this SKILL.md; it travels with the skill. Use Python 3.11+. Run `python <skill-dir>/scripts/wedocodex.py list` only if current preset values are needed. Do not scan local history or the full model cache merely to select a behavior.

For a mode activation request with no mode, show the five choices below and ask which one to use. For an explicit named activation, adopt that behavior in this chat and carry on with the user's task. Reviewing, testing or explaining the skill is not activation. A later explicit mode replaces the previous behavior, not the user's task or approvals. Do not start a second session unless asked to launch or resume CLI. Never infer runtime changes from a text instruction.

| Mode | Intended runtime | Behavior |
| --- | --- | --- |
| token-saver | GPT-6 Luna / low | Concise answers, scoped searches, deterministic scripts, no automatic subagents. Escalate only when task difficulty warrants it. |
| fast-flow | GPT-6.1 Sol / medium, workspace-write, never approvals | Finish authorized work. A denied operation stays denied; no sandbox bypass. |
| max-quality | GPT-6 Astra / max | Verify consequential assumptions and relevant behavior thoroughly. No automatic delegation. |
| guarded | GPT-6.1 Sol / medium, read-only, never approvals | Read-only audit including external tools. Do not read secrets. Propose changes without executing. |
| autopilot | GPT-6.1 Sol / medium | Persist timestamped checkpoints at meaningful milestones, continue authorized work, respect budgets and stop conditions. |

In a running chat, model/effort changes require the client's actual controls: CLI `/model`, `/permissions`, then `/status`; in other clients use the available model and permission controls. Acknowledge behavior in one sentence and distinguish intended from verified runtime settings. If runtime state is unavailable, say so rather than reading config.toml as proof. Complete preset application uses the launcher for a new CLI session, or `run MODE --resume SESSION_ID` after the previous writer stops. Never guess a session ID or use the latest session implicitly. Invoke this skill as `$wedocodex MODE`; it does not register `/wedocodex`.

Launcher examples:
```
python <skill-dir>/scripts/wedocodex.py show token-saver
python <skill-dir>/scripts/wedocodex.py run token-saver --workspace <project>
```

Runtime profiles are installed additively as `$CODEX_HOME/wedocodex-MODE.config.toml` (default `~/.codex`). The launcher applies equivalent CLI overrides and adds the behavior prompt. Managed restrictions remain authoritative. Direct `codex --profile wedocodex-MODE` selects runtime settings only. Models are presets, not entitlement guarantees; the launcher allows explicit `--model MODEL --effort LEVEL` and never silently substitutes a different model. Do not enable ultra or subagents as a side effect of a profile.

Sandbox read-only protects shell filesystem writes; it does not isolate all secrets or prevent connector mutations. Guarded's connector constraint is behavioral. Autopilot terminal notifications depend on the terminal; they are not mobile push. No external notification service is configured. Compaction saves context, not subscription quota. Never claim a measured saving without before/after evidence. For unrelated tasks use a fresh chat; for the same long task preserve a checkpoint before `/compact`.

Workspace instructions still govern delegation, compute, artifact names, quotas and external agents. A mode grants no additional spending, messaging, scheduling or deployment authorization. Do not rewrite those instructions for token savings. Autopilot checkpoints should be brief, preserve objective/paths/verification/next step, and use a fresh timestamped filename under the workspace's existing checkpoint convention; do not write a checkpoint on every tool call.

For an explicit installation-management request, use `install`, `update`, `uninstall` or `recover` from the bundled launcher. Preview update/uninstall with `--dry-run`. Update from the new unpacked package, not an old installed script. Owned files are tracked in `$CODEX_HOME/wedocodex-install.json`; conflicts preserve user edits. Backups and interrupted-transaction journals stay under `$CODEX_HOME/wedocodex-history`. Uninstall leaves unknown files and history in place. Never delete a lock blindly after an abrupt process exit; verify that its installer is no longer running first.
