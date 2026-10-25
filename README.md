# WEDOCODEX 0.3.0-beta.2

Five task profiles for Codex: **Token Saver, Fast Flow, Max Quality, Guarded and Autopilot**. Native startup settings, explicit activation, previews and recoverable installation updates. [Русская версия](README.ru.md).

Inspired by **[Ultra Config](https://github.com/davila7/claude-code-templates/tree/88cee4945062501c7012d3fc3adf4f68d5f9c3b7/cli-tool/components/mods/productivity/ultra-config)** by **Daniel (San) Ávila / davila7**. See [the author's explanation](https://dev.to/dani_avila7/ultra-config-switches-your-whole-claude-code-setup-between-five-profiles-mid-session-4199). We reviewed version 0.2.1 at the pinned commit. WEDOCODEX is an independent Codex adaptation, not a drop-in installation of the Claude Code mod. [Setting-by-setting mapping](skill/references/ultra-config-map.md).

## Measured result

**23.1% fewer total tokens across four small paired file tasks.** Both conditions requested Sol 6.1 / medium. Eight fresh sessions, all answers correct, one successful tool call per session; input files unchanged. Run order alternated A/B, B/A, A/B, B/A.

| Task | Default Codex | Token Saver |
|---|---:|---:|
| Aggregate 80 records | 52,277 | 40,397 |
| Check an asset manifest | 51,989 | 40,093 |
| Calculate scenario timing | 52,103 | 39,906 |
| Review a Python interpolation function | 52,023 | 39,879 |
| **Total** | **208,392** | **160,275** |

Savings: **48,117 tokens**. Uncached input fell from **61,153 to 36,738**, or **39.9%**. Cached input differed: 146,560 versus 122,496. Output was 679 versus 1,041 tokens; reasoning is included in output, not added again. Aggregate elapsed time was 70.922 versus 73.235 seconds. We make no speed or billing guarantee.

This is a small reproducible benchmark, not a production-repository evaluation or a head-to-head test against other optimizers. Total test consumption was 368,667 tokens, including cached input. Account-wide quota percentages were not used to attribute usage. Raw sanitized measurements are in [evidence](evidence/).

An earlier instruction-only version increased token use by about 0.35% on a same-model test. A failed Windows test consumed 92,364 tokens because its harness skipped platform configuration; it is excluded from the completed comparison and documented. These failures are not counted as savings.

## Quick install with npx

With Node.js 18+ (npm/npx), Git and Python 3.11+ installed:

```bash
npx --yes github:ychkydyk/wedocodex install
```

This fetches the package from our GitHub repository and runs the existing Python installer. It is **not** an npm-registry release named `wedocodex`; do not substitute `npx wedocodex`. Codex CLI is required to use the modes. The wrapper does not install prerequisites or submit a model request.

Preview installation with `npx --yes github:ychkydyk/wedocodex install --dry-run`. After installation, open a new Codex chat and invoke `$wedocodex`. To apply startup context limits, open a new terminal session for your current project:

```bash
npx --yes github:ychkydyk/wedocodex run saver --autopilot --workspace .
```

The `run` command starts a model session. `install` only installs files; it does not activate a profile or change an existing chat. Existing installations can use `update --dry-run`, then `update`; modified owned files block replacement. All Python launcher actions are forwarded with argument arrays, without shell evaluation inside the wrapper.

If you prefer not to use Node.js, use the standalone Python ZIP or Git instructions below. For reproducibility, append `#<commit SHA>` to the GitHub package specifier.

## Install and run

Python 3.11+ and Codex CLI are required. Windows was tested with Codex 0.162.0-alpha.17.2. **macOS is experimental: the Terminal setup is documented, but no real Mac has been tested.** Linux remains untested. See the [macOS guide](MACOS.md).

On macOS, install Codex CLI separately and make `codex` available on PATH; macOS app or VS Code bundle discovery is not implemented. After signing in through Codex, use the same Python package from Terminal:

```bash
python3 wedocodex.py install --dry-run
python3 wedocodex.py install
python3 wedocodex.py preview saver --autopilot --workspace "$HOME/Projects/My Project"
python3 wedocodex.py run saver --autopilot --workspace "$HOME/Projects/My Project"
```

Use an existing workspace. If `python3` is older than 3.11, use your newer Python executable consistently. The 23.1% benchmark was measured on Windows, not macOS.

```powershell
git clone https://github.com/ychkydyk/wedocodex.git
cd wedocodex
python wedocodex.py install
python wedocodex.py run saver --workspace C:/YourProject
```

For **Saver + Autopilot together**:

```powershell
python wedocodex.py preview saver --autopilot --workspace C:/YourProject
python wedocodex.py run saver --autopilot --workspace C:/YourProject
```

The combination keeps Saver's model/effort and context budgets, enables recap and terminal notifications, and adds brief milestone checkpoints. Its separate live smoke test completed the task and wrote the required checkpoint using 40,673 tokens. That functional test does not establish a savings percentage for the combination.

For fixed-model comparisons, add `--model gpt-6.1-sol --effort medium`. No model is silently substituted. A catalog entry does not prove account entitlement.

On Windows, the launcher finds native `codex.exe` on PATH or in registered official VS Code / VS Code Insiders extensions. A custom installation can set `WEDOCODEX_CODEX_EXE` to its absolute native executable path. Batch shims are never executed through a shell.

## What the modes do

| Mode | Default model / effort | Skill catalog budget | Tool-output history limit | Workflow |
|---|---|---:|---:|---|
| Token Saver | Luna / low | 2,000 | 6,000 | Targeted reads, concise output, deterministic routines |
| Fast Flow | Sol 6.1 / medium | 4,000 | 8,000 | Few interruptions within workspace permissions; denied actions stay denied |
| Max Quality | Astra / max | 10,000 | 16,000 | More reasoning and verification for difficult work |
| Guarded | Sol 6.1 / medium | 6,000 | 8,000 | Read-only shell and audit-oriented behavior |
| Autopilot | Sol 6.1 / medium | 4,000 | 8,000 | Continue the authorized task, checkpoints, verification and recap |

Autopilot is a workflow preset while Codex remains open. It is not a background daemon, scheduled agent, mobile push service or automatic Telegram reporter. It does not grant spending, delegation, publishing or broader access. Extra recaps and checkpoints can consume tokens.

Guarded does not isolate secrets and shell permissions do not technically block every connector mutation. The skill also instructs the agent to avoid mutations during an audit.

## What changes when

Calling `$wedocodex` in a chat selects behavior. It does not retroactively change that chat's startup context, model or permissions. Full startup limits require the launcher and a new session. Restarting VS Code alone does not select Saver.

The skill-list budget reduces discovery descriptions and may omit skills from initial suggestions. An explicitly selected skill still loads its full SKILL.md. No other skills or plugins are deleted or rewritten. Native automatic compaction is inherited rather than replaced.

For idle sessions, use native `/model`, `/permissions` and `/status`. Optional `live-preview`, `live-apply` and `live-undo` use a compatible local App Server proxy and require an exact thread UUID and workspace. Model/effort apply and undo were tested for all five modes on an isolated completed thread. Named permission profiles are preserved and blocked fields reported. The tested IDE did not expose the required proxy, so live attachment to that IDE is not claimed. Startup limits still require a new launch.

## Updates and removal

```powershell
python wedocodex.py update --dry-run
python wedocodex.py update
python wedocodex.py uninstall --dry-run
python wedocodex.py uninstall
```

Run update from the new unpacked package. Owned-file hashes detect conflicts before writes. Timestamped backups, per-file atomic replacement and a recovery journal preserve user changes. `recover` handles interrupted transactions; do not remove a stale lock until its installer is confirmed stopped. The base config.toml is not rewritten.

## Verification and distribution

The release build runs 40 automated regression tests, eight local effective-configuration checks and the extracted-package tests. These checks make no model requests. `preflight_tools.py` checks sandbox file access before paid tests. It does not prove every model-generated command will pass policy review.

Opt-in model tests:

```powershell
python bench_file_suite.py --all-four
python bench_file_suite.py --all-four --run
python bench_file_suite.py --combined-smoke --run
```

The first command only prints a plan. Commands with `--run` consume model tokens. Repeated measurements and larger workloads are still needed.

Two artifacts are provided: a standalone source/installer ZIP and a skills-only Codex plugin ZIP. The plugin includes portable `plugin.json` plus the Codex compatibility manifest and a self-contained skill. Local extraction and launcher execution are checked; public-directory approval is not claimed. Avoid enabling duplicate standalone and plugin copies of the skill.

## Positioning

WEDOCODEX packages native Codex settings and explicit workflow choices. It does not replace tool-output compressors such as RTK, indexed-context tools such as context-mode, provider gateways or iterative agent-loop engines. We have not demonstrated better savings than those tools. The practical focus is a small local setup, clear boundaries, safe updates and transparent same-model measurements.

Licensed under [MIT](LICENSE). Independent project; no affiliation with OpenAI, Anthropic or the Ultra Config author is implied.
