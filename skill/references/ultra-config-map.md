# Ultra Config to WEDOCODEX: verified mapping

Source: davila7/claude-code-templates, ultra-config 0.2.1, commit `88cee4945062501c7012d3fc3adf4f68d5f9c3b7`, examined 2026-10-24.
https://github.com/davila7/claude-code-templates/tree/88cee4945062501c7012d3fc3adf4f68d5f9c3b7/cli-tool/components/mods/productivity/ultra-config

The original is a Claude Code Mod using its host config/store/settings/pane APIs. It is not a Codex plugin. We do not execute its hooks or import Claude settings. Its source is MIT, copyright 2025 Daniel (San) Avila. WEDOCODEX is a separately implemented adaptation.

## Token Saver: all 11 original steps

| Ultra Config | Codex adaptation |
|---|---|
| Sonnet | GPT-6 Luna by default; explicit model override available |
| Low effort | model_reasoning_effort=low |
| Haiku subagents | Existing routing preserved; no automatic delegation or foreign-model runner |
| Fast off | Live serviceTier reset to normal when needed; startup service tier inherited, never silently set to premium |
| Concise | model_verbosity=low for the verified supported preset models |
| Prompt suggestions off | No verified equivalent in this client; not invented |
| Recap off | tui.auto_recap=false |
| Auto-compact on | Native automatic compaction retained; no experimental prompt or guessed threshold |
| Small workflow fan-outs | Workspace delegation policy retained; no automatic agents |
| ultracode keyword off | Claude-only keyword, not applicable |
| MCP output cap 10000 | tool_output_token_limit=6000; broader Codex history-output limit, not an identical per-MCP contract |

Extra supported control: skills.max_context_tokens=2000. This shrinks the discovery catalog, not the full contents of an explicitly invoked skill. Some skills may be omitted from initial discovery; use an explicit skill or Max Quality for broad work. Other plugins are not uninstalled or rewritten.

Keep the tool catalog stable: a variant that disabled agent tools cut total tokens but lost cache hits. The selected saver inherits agent availability and still prohibits automatic delegation in its behavior instructions.

## Fast Flow: all 8 original steps

| Ultra Config | Codex adaptation |
|---|---|
| Sonnet / medium | Sol 6.1 / medium |
| Accept edits | workspace-write + never approvals; denied operations fail, no sandbox bypass |
| Concise | low verbosity |
| Prompt suggestions on | No verified equivalent, skipped |
| Turn duration | Native CLI timing/event reporting; not a token-saving mechanism |
| Progress bar | Native client UI, no invented config flag |
| Medium workflows | Existing delegation rules preserved |

Added catalog/output budgets: 4000/8000 tokens.

## Max Quality: all 9 original steps

| Ultra Config | Codex adaptation |
|---|---|
| best model | Astra, validated against the local model catalog; no entitlement claim |
| xhigh | max, verified in this client's preset catalog; ultra excluded because it enables proactive delegation |
| Remove subagent override | Preserve owner routing |
| Default output | medium verbosity |
| Workflows on | Explicit authorization still required |
| ultracode on | Claude-only, skipped |
| Large fan-outs | Not enabled automatically |
| Checkpoints | Timestamped profile/install history; not a guarantee of undoing arbitrary project edits |
| Auto-compact | Native behavior retained |

Catalog/output budgets: 10000/16000 tokens.

## Guarded: all 7 original steps

| Ultra Config | Codex adaptation |
|---|---|
| Ask on every action | read-only + never shell escalation; cannot promise prompts for every connector action |
| No auto mode during plan | Native read-only restriction; no invented plan-auto toggle |
| Disable bypass mode | Launcher never emits bypass/full-access flags; it does not globally prevent the owner from launching another tool |
| Deny Read .env/secrets/SSH/AWS | Not ported as fake protection: read-only is not secret isolation, and connectors have separate permissions |
| Checkpoints | Profile/config history only |
| Verbose calls | Native client display; hiding/showing logs is not a token-saving claim |
| ultracode off | Not applicable |

Catalog/output budgets: 6000/8000 tokens. Agent tools disabled for this mode.

## Autopilot: all 8 original steps

| Ultra Config | Codex adaptation |
|---|---|
| Auto approval classifier | on-request; avoids silently adding approval-agent usage or broader permissions |
| Auto during plan | Not enabled; follows task authorization |
| High effort | medium as the local budget-conscious default |
| Workflows on | No automatic delegation |
| Recap on | tui.auto_recap=true |
| Agent push notification | Terminal notification only |
| Input-needed push | Terminal notification only, no external service or mobile push |
| Auto-compact | Native behavior retained |

Catalog/output budgets: 4000/8000 tokens. Checkpoints are milestone-based, not per tool call.

## Preview, activation and undo

- `preview MODE` reads effective config and prints old/new values. Config is not proof of an active chat.
- `run MODE` applies all supported startup settings through CLI overrides.
- `live-preview MODE --thread UUID` and `live-apply MODE --thread UUID` require an explicit idle thread in the specified workspace and a running local Codex App Server proxy. No session guessing and no model turn is submitted.
- Model/effort changes are read back. Named permission profiles are preserved; blocked rows require native /permissions or a full preset launch.
- Context/output/recap controls require a new launch; live output never claims the whole preset is active.
- `live-undo --thread UUID` restores only the recorded changed values and refuses if the user changed them afterwards.
- Existing sessions without a persisted rollout cannot be resumed for live inspection. Desktop/IDE connections that expose no local proxy must use native /model and /permissions controls.

Sources: https://learn.chatgpt.com/docs/config-file/config-reference ; https://learn.chatgpt.com/docs/build-skills ; locally generated Codex 0.162.0-alpha.17.2 app-server schema.
