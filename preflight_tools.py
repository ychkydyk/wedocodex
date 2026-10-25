"""Check real sandbox file access without a model turn or shared config changes."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets

from skill.scripts import wedocodex as w
from skill.scripts.runtime_profiles import Rpc, value

ROOT = Path(__file__).resolve().parent


def check(home, workspace, settings):
    workspace = Path(workspace).resolve()
    marker = secrets.token_hex(12)
    probe = workspace / ('preflight-' + marker + '.txt')
    with probe.open('x', encoding='utf-8') as f:
        f.write(marker)
    try:
        # Preserve the same user/platform configuration used by normal launches.
        with Rpc(w.resolve_executable(), home, workspace, config=settings) as rpc:
            config = rpc.request('config/read', {'cwd': str(workspace), 'includeLayers': False})['config']
            for key, expected in settings.items():
                if value(config, key) != expected:
                    raise RuntimeError('Configuration mismatch: ' + key)
            # Thread creation is local; no turn/start or inference follows.
            result = rpc.request('thread/start', {
                'cwd': str(workspace), 'ephemeral': True,
                'model': settings['model'], 'sandbox': settings['sandbox_mode'],
                'approvalPolicy': settings['approval_policy']})
            sandbox = result['sandbox']
            expected_type = {'workspace-write': 'workspaceWrite', 'read-only': 'readOnly'}[settings['sandbox_mode']]
            if sandbox.get('type') != expected_type:
                raise RuntimeError('Actual sandbox differs from requested sandbox')
            command = [os.path.join(os.environ.get('SystemRoot', 'C:/Windows'),
                       'System32/WindowsPowerShell/v1.0/powershell.exe'),
                       '-NoProfile', '-NonInteractive', '-Command',
                       "Get-Content -LiteralPath '" + probe.name + "' -Raw"]
            read = rpc.request('command/exec', {'command': command, 'cwd': str(workspace),
                               'sandboxPolicy': sandbox, 'timeoutMs': 10000})
            if read.get('exitCode') != 0 or read.get('stdout', '').strip() != marker:
                raise RuntimeError('Sandbox read probe failed: ' + json.dumps(read))
            return {'passed': True, 'model_requests': 0, 'sandbox': sandbox,
                    'approval_policy': result.get('approvalPolicy'),
                    'windows_sandbox': value(config, 'windows.sandbox'),
                    'catalog_budget': value(config, 'skills.max_context_tokens'),
                    'tool_output_budget': value(config, 'tool_output_token_limit'),
                    'scope': 'App Server effective sandbox and standalone command; not model-generated execpolicy review'}
    finally:
        # Keep the probe as evidence; no cleanup or ownership changes.
        pass


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home', type=Path, default=w.codex_home())
    a = p.parse_args()
    stamp = datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d_%H-%M-%S-%f')
    folder = ROOT / 'qa' / (stamp + '-sandbox-preflight')
    folder.mkdir(parents=True)
    rows = []
    for condition in ['A', 'B']:
        workspace = folder / condition
        workspace.mkdir()
        settings = w.settings('token-saver', 'gpt-6.1-sol', 'medium')
        if condition == 'A':
            for key in ('skills.max_context_tokens', 'tool_output_token_limit', 'model_verbosity'):
                settings.pop(key)
        settings['approval_policy'] = 'never'
        try:
            row = dict(condition=condition, **check(a.home, workspace, settings))
        except Exception as exc:
            row = dict(condition=condition, passed=False, model_requests=0, error=str(exc))
        rows.append(row)
        if not row['passed']:
            break
    with (folder / 'results.json').open('x', encoding='utf-8') as f:
        json.dump({'rows': rows, 'timezone': 'Europe/Moscow'}, f, indent=2)
    print(json.dumps({'folder': str(folder), 'rows': rows}, indent=2))
    if len(rows) != 2 or not all(row['passed'] for row in rows):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
