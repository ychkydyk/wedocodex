"""WEDOCODEX: additive profile installer and shell-free Codex launcher. Python 3.11+."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import re
try:
    from . import managed_install as lifecycle
except ImportError:
    import managed_install as lifecycle

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.2.0-beta.3'
MSK = timezone(timedelta(hours=3), 'Europe/Moscow')
PROFILES = {
    'token-saver': ('gpt-6-luna', 'low', 'workspace-write', 'on-request'),
    'fast-flow': ('gpt-6.1-sol', 'medium', 'workspace-write', 'never'),
    'max-quality': ('gpt-6-astra', 'max', 'workspace-write', 'on-request'),
    'guarded': ('gpt-6.1-sol', 'medium', 'read-only', 'never'),
    'autopilot': ('gpt-6.1-sol', 'medium', 'workspace-write', 'on-request'),
}
MODES = {
    'token-saver': 'Use concise answers and targeted searches. Prefer deterministic scripts for routine data work. Do not launch subagents automatically. Escalate model choice only if task complexity warrants it, and explain before changing it.',
    'fast-flow': 'Complete the authorized task with minimal interruptions. Sandbox failures are blockers, not permission to bypass restrictions. Verify relevant behavior, then stop.',
    'max-quality': 'Prioritize correctness and evidence on difficult tasks. Check consequential assumptions and relevant tests. Do not expand scope or create agents automatically.',
    'guarded': 'Read-only audit. Do not mutate local files or external services, including through connectors. Avoid opening secrets. Report proposed changes without applying them. These behavioral constraints do not constitute technical secret isolation.',
    'autopilot': 'Continue the authorized task to completion. At meaningful milestones save a concise timestamped checkpoint containing objective, completed work, exact output paths, verification, blockers and next step. Respect budgets and stop conditions. Do not create schedules, launch external agents, or send external notifications without explicit authorization. Do not infer subscription quota from context usage.',
}

def codex_home():
    return Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')

def settings(name, model=None, effort=None):
    default_model, default_effort, sandbox, approval = PROFILES[name]
    model = model or default_model
    effort = effort or default_effort
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}', model):
        raise ValueError('Invalid model ID')
    if effort not in ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'):
        raise ValueError('Unsupported effort; automatic-delegation ultra is not a preset')
    result = dict(model=model, model_reasoning_effort=effort,
                  sandbox_mode=sandbox, approval_policy=approval)
    result['sandbox_workspace_write.network_access'] = False
    result['tui.auto_recap'] = name == 'autopilot'
    if name == 'autopilot':
        result['tui.notifications'] = True
        result['tui.notification_method'] = 'auto'
    return result

def toml_value(value):
    return json.dumps(value, ensure_ascii=False)

def profile_bytes(name):
    # Dotted keys must precede any table headers. JSON strings/bools are valid TOML here.
    content = '# WEDOCODEX profile; selected explicitly, never a global default.\n'
    content += '\n'.join(f'{key} = {toml_value(value)}' for key, value in settings(name).items())
    return (content + '\n').encode('utf-8')

def install_files(home, skills_dir=None):
    home = Path(home).resolve()
    skills_dir = Path(skills_dir).resolve() if skills_dir else home / 'skills'
    result = {home / f'wedocodex-{name}.config.toml': profile_bytes(name) for name in PROFILES}
    # Explicit allowlist: never ship logs, caches, credentials or local reports.
    for relative in ('SKILL.md', 'LICENSE', 'agents/openai.yaml', 'scripts/wedocodex.py', 'scripts/managed_install.py'):
        source = ROOT / relative
        result[skills_dir / 'wedocodex' / relative] = source.read_bytes()
    return result

def install(home, skills_dir=None):
    home = Path(home).resolve()
    destination = Path(skills_dir).resolve() if skills_dir else home / 'skills'
    result = lifecycle.manage('install', home, install_files(home, destination), destination, VERSION)
    print(json.dumps(result, indent=2))
    return result

def save_report(slug, content, directory=None):
    directory = Path(directory) if directory else ROOT.parent / 'reports'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (datetime.now(MSK).strftime('%Y-%m-%d_%H-%M-%S-%f') + f'-{slug}.json')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(content, stream, ensure_ascii=False, indent=2)
    return path

def command(name, workspace, resume=None, prompt=None, executable='codex', model=None, effort=None):
    args = [executable]
    if resume:
        if resume.startswith('-') or any(ord(c) < 32 for c in resume):
            raise ValueError('Resume requires a literal session ID/name, not a CLI option')
        args += ['resume', resume]
    # CLI overrides take precedence over project config and stale saved settings.
    args += ['--cd', str(Path(workspace).resolve())]
    for key, value in settings(name, model, effort).items():
        args += ['-c', f'{key}={toml_value(value)}']
    instruction = f'Use WEDOCODEX mode {name}. {MODES[name]} Follow applicable workspace instructions. '
    instruction += 'This mode does not authorize additional spending, delegation, publishing or access changes.'
    if prompt:
        instruction += '\nTask: ' + prompt
    args += [instruction]
    return args

def check_catalog(home, name, model=None, effort=None):
    path = home / 'models_cache.json'
    if not path.exists():
        raise RuntimeError('Model catalog unavailable. Open Codex normally to refresh it; no fallback model was selected.')
    raw = json.loads(path.read_text(encoding='utf-8'))
    models = raw.get('models') if isinstance(raw, dict) else None
    if not isinstance(models, list) or not all(isinstance(m, dict) for m in models):
        raise ValueError('Invalid model catalog structure; refresh it in Codex')
    config = settings(name, model, effort)
    model, effort = config['model'], config['model_reasoning_effort']
    found = next((m for m in models if m.get('slug') == model), None)
    levels = found.get('supported_reasoning_levels', []) if found else []
    if not isinstance(levels, list) or not found or effort not in [r.get('effort') for r in levels if isinstance(r, dict)]:
        raise RuntimeError(f'Catalog does not advertise {model}/{effort}; no silent substitution.')
    print(f'Local catalog: {model}/{effort}. Entitlement is unverified until a successful model response.')

def resolve_executable():
    # Windows npm shims are batch files: shell=False cannot make them injection-safe.
    executable = shutil.which('codex.exe') if os.name == 'nt' else shutil.which('codex')
    if not executable:
        executable = shutil.which('codex')
    if not executable:
        raise RuntimeError('codex is not on PATH')
    if Path(executable).suffix.lower() in ('.cmd', '.bat'):
        raise RuntimeError('A Windows batch shim was found. Put the native codex.exe on PATH; no shell fallback is used.')
    return executable

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('action', choices=['menu', 'list', 'show', 'run', 'install', 'update', 'uninstall', 'recover'], nargs='?', default='menu')
    parser.add_argument('mode', choices=PROFILES, nargs='?')
    parser.add_argument('--workspace', default=os.getcwd())
    parser.add_argument('--resume', help='Explicit session ID/name; stop its previous writer first')
    parser.add_argument('--prompt')
    parser.add_argument('--home', type=Path, help='Installation destination only')
    parser.add_argument('--skills-dir', type=Path, help='Install skill under this directory')
    parser.add_argument('--dry-run', action='store_true', help='Preview install/update/uninstall without changing installed files')
    parser.add_argument('--model', help='Explicit model override, checked against the local catalog')
    parser.add_argument('--effort', choices=['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'])
    options = parser.parse_args()
    maintenance = options.action in ('install', 'update', 'uninstall', 'recover')
    if not maintenance and (options.home or options.skills_dir or options.dry_run):
        parser.error('--home, --skills-dir and --dry-run apply only to installation management')
    if maintenance and options.mode:
        parser.error('Installation management does not take a working mode')
    if options.action == 'recover' and options.dry_run:
        parser.error('recover has no dry-run; recovery checks for external edits before restoring')
    if options.action not in ('menu', 'run', 'show') and any((options.resume, options.prompt, options.model, options.effort)):
        parser.error('resume/prompt/model/effort apply only to menu, run or show')
    if maintenance:
        home = (options.home or codex_home()).resolve()
        destination = options.skills_dir
        if destination is None and (home/lifecycle.STATE).exists():
            _, installed_root = lifecycle.load(home)
            destination = installed_root.parent
        if destination is None:
            destination = home/'skills' if options.home else Path.home()/'.agents'/'skills'
        files = install_files(home, destination) if options.action in ('install', 'update') else None
        result = lifecycle.manage(options.action, home, files, destination, VERSION, options.dry_run)
        print(json.dumps(result, indent=2))
        return
    if options.action == 'list':
        for name, values in PROFILES.items():
            print(f'{name:14} {values[0]:15} {values[1]:6} {values[2]:16} approval={values[3]}')
        return
    if options.action == 'menu':
        if not sys.stdin.isatty():
            parser.error('Interactive menu requires a terminal; use list, show or run MODE')
        names = list(PROFILES)
        for i, name in enumerate(names, 1):
            print(f'{i}. {name} ({PROFILES[name][0]} / {PROFILES[name][1]})')
        choice = input('Select 1-5, or Enter to cancel: ').strip()
        if not choice:
            return
        if choice not in [str(i) for i in range(1, 6)]:
            raise RuntimeError('Invalid selection; nothing launched.')
        options.mode = names[int(choice) - 1]
    if not options.mode:
        parser.error('mode is required for show/run')
    args = command(options.mode, options.workspace, options.resume, options.prompt,
                   model=options.model, effort=options.effort)
    if options.action == 'show':
        print(json.dumps({'settings': settings(options.mode, options.model, options.effort), 'argv': args}, ensure_ascii=False, indent=2))
        return
    if not Path(options.workspace).is_dir():
        raise RuntimeError('Workspace directory does not exist')
    check_catalog(codex_home(), options.mode, options.model, options.effort)
    executable = resolve_executable()
    args[0] = executable
    print(f'Starting {options.mode}; base config unchanged. Confirm effective settings with /status.')
    raise SystemExit(subprocess.call(args, shell=False))

if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f'WEDOCODEX: {exc}', file=sys.stderr)
        raise SystemExit(1)
