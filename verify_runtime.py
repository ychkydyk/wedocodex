"""Offline config/read checks against a separate, credential-free app-server."""
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parent

def read_config(executable, home, workspace, overrides=()):
    args = [executable, 'app-server', '--listen', 'stdio://', '--strict-config']
    for key, value in overrides:
        args += ['-c', key + '=' + json.dumps(value)]
    env = {k: v for k, v in os.environ.items()
           if not any(secret in k.upper() for secret in ('TOKEN', 'SECRET', 'API_KEY'))}
    env['CODEX_HOME'] = str(home)
    # Only this new process is touched. No thread/start, turn/start or account calls.
    with subprocess.Popen(args, cwd=workspace, env=env, stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding='utf-8', errors='replace') as proc:
        messages = queue.Queue()
        errors = []
        def drain():
            for line in proc.stdout:
                try:
                    messages.put(json.loads(line))
                except ValueError:
                    pass
            messages.put(None)
        def drain_errors():
            errors.extend(proc.stderr.readlines())
        reader = threading.Thread(target=drain, daemon=True)
        err_reader = threading.Thread(target=drain_errors, daemon=True)
        reader.start(); err_reader.start()
        def send(data):
            proc.stdin.write(json.dumps(data) + '\n'); proc.stdin.flush()
        def response(identifier):
            for _ in range(100):
                item = messages.get(timeout=15)
                if item is None:
                    raise RuntimeError('Server exited: ' + ''.join(errors)[-1200:])
                if item.get('id') == identifier:
                    if 'error' in item:
                        raise RuntimeError(json.dumps(item['error']))
                    return item['result']
            raise RuntimeError('Too many unsolicited messages')
        try:
            send({'id': 1, 'method': 'initialize', 'params': {
                'clientInfo': {'name': 'wedocodex_qa', 'version': '0.2.0'},
                'capabilities': {'experimentalApi': True}}})
            response(1)
            send({'method': 'initialized', 'params': {}})
            send({'id': 2, 'method': 'config/read', 'params': {'cwd': str(workspace), 'includeLayers': True}})
            return response(2)
        finally:
            proc.stdin.close()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.terminate(); proc.wait(timeout=3)
            reader.join(timeout=2); err_reader.join(timeout=2)

def run_suite():
    from skill.scripts import wedocodex as w
    stamp = datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d_%H-%M-%S-%f')
    folder = ROOT / 'qa' / (stamp + '-runtime-test2')
    home = folder / 'home'; workspace = folder / 'workspace'
    home.mkdir(parents=True); workspace.mkdir()
    executable = shutil.which('codex')
    results = []
    def lookup(config, dotted):
        for key in dotted.split('.'):
            config = config[key]
        return config
    # Each case gets a new profile directory: preserve all diagnostic inputs.
    for name in w.PROFILES:
        case_home = home / name; case_home.mkdir()
        (case_home / 'config.toml').write_bytes(w.profile_bytes(name))
        data = read_config(executable, case_home, workspace)
        actual = {key: lookup(data['config'], key) for key in w.settings(name)}
        assert actual == w.settings(name), (name, actual)
        results.append({'case': 'profile-values-' + name, 'passed': True, 'actual': actual})
    # A trusted project deliberately conflicts with the launcher settings.
    override_home = home / 'precedence'; override_home.mkdir()
    (workspace / '.git').mkdir()
    config_dir = workspace / '.codex'; config_dir.mkdir()
    (config_dir / 'config.toml').write_text('model = "conflicting-project-model"\nmodel_reasoning_effort = "high"\nsandbox_mode = "workspace-write"\napproval_policy = "on-request"\n', encoding='utf-8')
    (override_home / 'config.toml').write_text(
        '[projects.' + json.dumps(str(workspace.resolve())) + ']\ntrust_level = "trusted"\n', encoding='utf-8')
    baseline = read_config(executable, override_home, workspace)
    assert baseline['config']['model'] == 'conflicting-project-model', 'Project conflict was not actually loaded'
    # Use exactly the overrides emitted by the launcher, not a separate test-only mapping.
    args = w.command('guarded', workspace)
    overrides = [args[i+1].split('=', 1) for i, value in enumerate(args) if value == '-c']
    overrides = [(key, json.loads(value)) for key, value in overrides]
    result = read_config(executable, override_home, workspace, overrides)
    actual = {key: lookup(result['config'], key) for key in w.settings('guarded')}
    assert actual == w.settings('guarded'), actual
    results.append({'case': 'launcher-beats-trusted-project-conflict', 'passed': True, 'actual': actual})
    # A deliberately broken TOML must fail; it guards against a no-op diagnostic.
    broken = home / 'broken'; broken.mkdir()
    (broken / 'config.toml').write_text('model = "unterminated\n', encoding='utf-8')
    try:
        read_config(executable, broken, workspace)
    except (RuntimeError, BrokenPipeError) as exc:
        results.append({'case': 'malformed-config-rejected', 'passed': True, 'error': str(exc)[:800]})
    else:
        raise AssertionError('Malformed config unexpectedly accepted')
    report = {'created_at': datetime.now(timezone(timedelta(hours=3))).isoformat(),
              'timezone': 'Europe/Moscow', 'version': w.VERSION,
              'scope': 'Local config resolution only; no thread, inference, sandbox execution or notification delivery.',
              'results': results}
    with (folder / 'runtime-results.json').open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2)
    print(f'{len(results)} runtime config checks passed; {folder / "runtime-results.json"}')
    return report

if __name__ == '__main__':
    run_suite()
