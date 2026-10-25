"""WEDOCODEX: additive profile installer and shell-free Codex launcher. Python 3.11+."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
import re
try:
    from . import managed_install as lifecycle
    from . import runtime_profiles as runtime
except ImportError:
    import managed_install as lifecycle
    import runtime_profiles as runtime

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.3.0-beta.2'
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

def settings(name, model=None, effort=None, autopilot=False):
    if autopilot and name != 'token-saver':
        raise ValueError('The Autopilot overlay is supported with Token Saver only')
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
    result['tui.auto_recap'] = name == 'autopilot' or autopilot
    # Native runtime controls, not a request to the model to be economical.
    result['skills.max_context_tokens'] = {
        'token-saver': 2000, 'fast-flow': 4000, 'max-quality': 10000,
        'guarded': 6000, 'autopilot': 4000}[name]
    result['tool_output_token_limit'] = {
        'token-saver': 6000, 'fast-flow': 8000, 'max-quality': 16000,
        'guarded': 8000, 'autopilot': 8000}[name]
    # Keep the stable tool prefix for caching. Delegation remains governed by
    # workspace instructions; do not force-enable tools disabled by the owner.
    if name == 'guarded':result['agents.enabled'] = False
    if model in {entry[0] for entry in PROFILES.values()}:
        result['model_verbosity'] = 'medium' if name == 'max-quality' else 'low'
    if name == 'autopilot' or autopilot:
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
    for relative in ('SKILL.md', 'LICENSE', 'agents/openai.yaml', 'references/ultra-config-map.md', 'scripts/wedocodex.py', 'scripts/managed_install.py', 'scripts/runtime_profiles.py'):
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

def command(name, workspace, resume=None, prompt=None, executable='codex', model=None, effort=None, autopilot=False):
    args = [executable]
    if resume:
        if resume.startswith('-') or any(ord(c) < 32 for c in resume):
            raise ValueError('Resume requires a literal session ID/name, not a CLI option')
        args += ['resume', resume]
    # CLI overrides take precedence over project config and stale saved settings.
    args += ['--cd', str(Path(workspace).resolve())]
    for key, value in settings(name, model, effort, autopilot).items():
        args += ['-c', f'{key}={toml_value(value)}']
    instruction = f'Use WEDOCODEX mode {name}. {MODES[name]} Follow applicable workspace instructions. '
    if autopilot:
        instruction += 'Also enable the Autopilot workflow. ' + MODES['autopilot'] + ' '
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

def vscode_executables():
    """Find registered official VS Code bundles; never search arbitrary executables."""
    architecture = platform.machine().lower()
    folder = {'amd64': 'windows-x86_64', 'x86_64': 'windows-x86_64',
              'arm64': 'windows-aarch64', 'aarch64': 'windows-aarch64'}.get(architecture)
    if folder is None:
        return []
    result = []
    for editor in ('.vscode', '.vscode-insiders'):
        root = Path.home() / editor / 'extensions'
        try:
            entries = json.loads((root / 'extensions.json').read_text(encoding='utf-8'))
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict) or entry.get('identifier', {}).get('id') != 'openai.chatgpt':
                    continue
                relative = entry.get('relativeLocation', '')
                if not isinstance(relative, str) or not re.fullmatch(r'openai\.chatgpt-[A-Za-z0-9._-]+', relative):
                    continue
                bundle = root / relative
                package = json.loads((bundle / 'package.json').read_text(encoding='utf-8'))
                if package.get('publisher') != 'openai' or package.get('name') != 'chatgpt':
                    continue
                executable = bundle / 'bin' / folder / 'codex.exe'
                if executable.is_file():
                    result.append(str(executable.resolve()))
        except (OSError, ValueError, TypeError, AttributeError):
            continue
    return result


def resolve_executable():
    explicit = os.environ.get('WEDOCODEX_CODEX_EXE')
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_absolute() or not path.is_file() or path.suffix.lower() in ('.cmd', '.bat') or (os.name == 'nt' and path.suffix.lower() != '.exe'):
            raise RuntimeError('WEDOCODEX_CODEX_EXE must be an absolute path to the native Codex executable.')
        return str(path.resolve())
    # Windows npm shims are batch files: shell=False cannot make them injection-safe.
    executable = shutil.which('codex.exe') if os.name == 'nt' else shutil.which('codex')
    if not executable:
        executable = shutil.which('codex')
    if executable and Path(executable).suffix.lower() not in ('.cmd', '.bat'):
        return executable
    if os.name == 'nt':
        candidates = vscode_executables()
        if candidates:
            return candidates[0]
    raise RuntimeError('Native Codex was not found on PATH or in registered VS Code extensions. '
                       'Set WEDOCODEX_CODEX_EXE to the full native executable path. Batch shims are not executed.')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    parser.add_argument('action', choices=['menu', 'list', 'show', 'run', 'preview', 'live-preview', 'live-apply', 'live-undo', 'install', 'update', 'uninstall', 'recover'], nargs='?', default='menu')
    aliases={'saver':'token-saver','flow':'fast-flow','quality':'max-quality'}
    parser.add_argument('mode', choices=[*PROFILES,*aliases], nargs='?')
    parser.add_argument('--workspace', default=os.getcwd())
    parser.add_argument('--resume', help='Explicit session ID/name; stop its previous writer first')
    parser.add_argument('--prompt')
    parser.add_argument('--home', type=Path, help='Codex home for install or runtime control')
    parser.add_argument('--thread', help='Explicit existing thread UUID for live profile control')
    parser.add_argument('--skills-dir', type=Path, help='Install skill under this directory')
    parser.add_argument('--dry-run', action='store_true', help='Preview install/update/uninstall without changing installed files')
    parser.add_argument('--model', help='Explicit model override, checked against the local catalog')
    parser.add_argument('--effort', choices=['none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'])
    parser.add_argument('--autopilot', action='store_true', help='Combine Saver limits with Autopilot checkpoints, recap and terminal notifications')
    options = parser.parse_args()
    options.mode=aliases.get(options.mode,options.mode)
    if options.autopilot and (options.mode != 'token-saver' or options.action not in ('run','show','preview')):
        parser.error('--autopilot is supported with run/show/preview saver')
    maintenance = options.action in ('install', 'update', 'uninstall', 'recover')
    control=options.action in ('preview','live-preview','live-apply','live-undo')
    if not maintenance and not control and (options.home or options.skills_dir or options.dry_run):
        parser.error('--home, --skills-dir and --dry-run apply only to installation management')
    if control and options.skills_dir:parser.error('--skills-dir is installation-only')
    if options.thread and not options.action.startswith('live-'):parser.error('--thread applies only to live control')
    if maintenance and options.mode:
        parser.error('Installation management does not take a working mode')
    if options.action == 'recover' and options.dry_run:
        parser.error('recover has no dry-run; recovery checks for external edits before restoring')
    if options.action not in ('menu', 'run', 'show','preview','live-preview','live-apply') and any((options.resume, options.prompt, options.model, options.effort)):
        parser.error('resume/prompt/model/effort apply only to menu, run or show')
    if control:
        if options.resume or options.prompt:parser.error('Control actions do not submit a model prompt or select the last session')
        if options.action!='live-undo' and not options.mode:parser.error('Select a mode')
        if options.action.startswith('live-') and not options.thread:parser.error('Explicit --thread UUID required')
        home=(options.home or codex_home()).resolve();workspace=Path(options.workspace).resolve()
        wanted=settings(options.mode,options.model,options.effort,options.autopilot) if options.mode else None
        with runtime.Rpc(resolve_executable(),home,workspace,proxy=options.action.startswith('live-')) as rpc:
            if options.action=='preview':result={'scope':'configuration, not proof of an active chat', 'rows':runtime.preview_config(rpc,wanted,workspace)}
            elif options.action=='live-undo':result=runtime.live_undo(rpc,home,options.thread,workspace)
            else:
                check_catalog(home,options.mode,options.model,options.effort)
                result=runtime.live_apply(rpc,home,options.thread,workspace,options.mode,wanted,
                                         dry_run=options.action=='live-preview' or options.dry_run)
        print(json.dumps(result,ensure_ascii=False,indent=2));return
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
        workspace=Path(options.workspace).resolve()
        with runtime.Rpc(resolve_executable(),codex_home(),workspace) as rpc:
            rows=runtime.preview_config(rpc,settings(options.mode,options.model,options.effort),workspace)
        print('Configured values -> requested values (not the current chat state):')
        for row in rows:
            print(f"  {row['status']:6} {row['key']}: {row['from']} -> {row['to']}")
        if input('Enter to launch; any other input cancels: ').strip():return
    if not options.mode:
        parser.error('mode is required for show/run')
    args = command(options.mode, options.workspace, options.resume, options.prompt,
                   model=options.model, effort=options.effort, autopilot=options.autopilot)
    if options.action == 'show':
        print(json.dumps({'settings': settings(options.mode, options.model, options.effort,options.autopilot), 'argv': args}, ensure_ascii=False, indent=2))
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
