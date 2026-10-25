# macOS: experimental setup

The same WEDOCODEX Python package can be used for an experimental macOS setup. **No real Mac has been tested: neither Apple Silicon nor Intel.** Windows measurements, including the 23.1% result, do not establish savings or speed on macOS.

## Prerequisites

- Python **3.11+** (the launcher uses `tomllib`). Check `python3 --version`; use a newer interpreter consistently if needed.
- Codex **CLI** installed and available as `codex` on PATH. Follow the [official CLI installation guide](https://learn.chatgpt.com/docs/cli). The desktop app alone is not this setup path.
- Run `codex` normally, sign in and let its model catalog load, then exit before launching a WEDOCODEX profile. No model task is required just to install the skill.

Use the official Codex installer for your architecture. WEDOCODEX does not bundle Codex, download models or switch architectures.

## Install and inspect

Clone the repository, or extract the existing standalone release ZIP and open its `wedocodex` folder in Terminal:

```bash
git clone https://github.com/ychkydyk/wedocodex.git
cd wedocodex
python3 --version
command -v codex
codex --version
python3 wedocodex.py install --dry-run
python3 wedocodex.py install
python3 wedocodex.py show saver --autopilot
```

Skip clone if you already extracted the ZIP. `install` manages owned profiles under `CODEX_HOME` (normally `~/.codex`) and the skill under `~/.agents/skills/wedocodex`. The base `config.toml` is not rewritten. Conflicting installations are reported. Avoid enabling a duplicate standalone skill and plugin.

`show` prints requested settings without starting Codex. For a no-inference configuration readback through a separate local App Server:

```bash
python3 wedocodex.py preview saver --autopilot --workspace "$HOME/Projects/My Project"
```

Replace the path with an existing project. A preview does not prove that an existing IDE chat changed or the account has model access. Stop on errors or unsupported fields rather than treating a partial preview as success.

## Start a session

```bash
python3 wedocodex.py run saver --autopilot --workspace "$HOME/Projects/My Project"
```

Keep quotes around paths with spaces. This opens a new terminal Codex session and sends the mode instruction; model usage can begin. Check `/status`. Autopilot works while the session remains open, not as a daemon or scheduled job.

If the catalog does not advertise the preset model/effort, the launcher stops. Explicit `--model` and `--effort` overrides can select an available model; no automatic substitution occurs.

## Codex not found

First make `command -v codex` and `codex --version` work in the same Terminal. Restart Terminal if an installer changed PATH. macOS app and VS Code bundle discovery are not implemented. After `command -v codex` succeeds, an explicit installation can use:

```bash
export WEDOCODEX_CODEX_EXE="$(command -v codex)"
```

The target must exist, be executable and belong to your intended Codex installation. Do not disable Gatekeeper or sandbox protections to work around errors.

## Updates and removal

Run update from the new extracted package:

```bash
python3 wedocodex.py update --dry-run
python3 wedocodex.py update
python3 wedocodex.py uninstall --dry-run
```

Use `python3 wedocodex.py uninstall` only to remove WEDOCODEX. Owned-file hashes protect manual edits; transaction history is retained. Symlinked installation targets may be refused; do not bypass that guard.

## Still unverified on a real Mac

Installation/update/removal end to end, model access, workspace-write/read-only enforcement, macOS paths and permissions, terminal notifications, session resume and workload measurements. Windows regression tests and mocked POSIX resolver checks do not replace these tests. Report macOS version, `uname -m`, Python/Codex versions and sanitized errors, excluding credentials and private prompts.
