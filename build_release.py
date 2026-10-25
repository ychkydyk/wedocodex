"""Build a timestamped, allowlisted beta archive after offline tests pass."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

from skill.scripts import wedocodex as w
from verify_runtime import run_suite

ROOT = Path(__file__).resolve().parent
FILES = ['README.md', 'README.ru.md', 'MACOS.md', 'LICENSE', '.gitignore', 'wedocodex.py', 'wedocodex.cmd',
         'test_wedocodex.py', 'test_release.py', 'test_lifecycle.py', 'test_runtime_profiles.py', 'verify_runtime.py', 'verify_live_profiles.py', 'build_release.py',
         'migrate_legacy.py', 'bench_live.py', 'bench_ab.py', 'bench_mechanics.py', 'bench_warm.py', 'bench_installed.py', 'bench_file_suite.py', 'preflight_tools.py', 'build_plugin.py', 'probe_context.py', 'probe_quota.py',
         'skill/SKILL.md', 'skill/LICENSE', 'skill/agents/openai.yaml', 'skill/references/ultra-config-map.md',
         'skill/scripts/wedocodex.py', 'skill/scripts/managed_install.py', 'skill/scripts/runtime_profiles.py']

def main():
    stamp = datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d_%H-%M-%S-%f')
    report_dir = ROOT / 'reports'; report_dir.mkdir(exist_ok=True)
    test = subprocess.run([sys.executable, '-m', 'unittest', '-v', 'test_wedocodex', 'test_release', 'test_lifecycle', 'test_runtime_profiles'],
                          cwd=ROOT, capture_output=True, text=True)
    with (report_dir / (stamp + '-second-test.log')).open('x', encoding='utf-8') as f:
        f.write(test.stdout + test.stderr)
    if test.returncode:
        raise RuntimeError(test.stderr)
    runtime = run_suite()
    test_count = int(re.search(r'Ran (\d+) tests?', test.stdout + test.stderr).group(1))
    cli_version = subprocess.run([w.resolve_executable(), '--version'], capture_output=True, text=True, check=True).stdout.strip()
    qa = f'''# WEDOCODEX release verification - {w.VERSION}

Date: {datetime.now(timezone(timedelta(hours=3))).isoformat()}. Time zone: Europe/Moscow.
Platform: Windows. CLI: {cli_version}. Python: {sys.version.split()[0]}.

{test_count} regression tests passed. {len(runtime['results'])} local App Server config checks passed.

Verified: self-contained installed skill; conflict preflight; rollback on a simulated late write failure; literal Unicode/quoted arguments in a real child process; refusal of batch shims and option-shaped session IDs; invalid catalog handling; explicit model overrides; noninteractive menu errors; all five effective presets; launcher overrides beat a loaded trusted-project conflict; malformed TOML is rejected.

Manual skill review: bare invocation offers choices; explicit activation changes behavior only; a review request does not activate a mode; mode switching preserves the task and approvals; no inferred session IDs; no automatic agents or publishing; checkpoints are milestone-based. This review is not an independent model evaluation.

Fixed since v1: absolute workstation paths and missing launcher in installed skill; incomplete argument validation; nonportable Windows argument forwarding; partial install on write failure; misleading catalog/access wording; profile discussion could unintentionally activate behavior.

This build command performs no inference. Version 0.3 uses real catalog/output limits. A fixed-model paired test across 3 short tasks yielded mean total tokens 18179.33 -> 13980.67 and uncached input 8149 -> 3947; cached input was 9984 in both conditions. All six answers were correct. Median elapsed time 7.968 -> 8.078 seconds does not establish a speed gain. This is a bounded workload result, not an account-quota or billing guarantee. The independent served model ID was not exposed; requested model/effort was Sol 6.1 / medium.

Preview/apply/undo of model and effort was verified for all five modes through the native API on a separate completed thread, without inference. Named permission profiles were preserved and skipped fields were reported. A proxy to the current desktop session was unavailable, so attachment to that client is not claimed. Startup catalog/output budgets still need a new launch.

Update/uninstall/recover use owned-file hashes, verified timestamped backups and per-file atomic writes. User edits block changes. Interrupted transactions are recoverable; stale locks after hard process termination require checking that the installer has stopped. Two additional tests cover exact-baseline migration and refusal of a modified legacy installation.

The corrected Windows file benchmark covers four paired tasks and eight fresh sessions, all correct, one successful tool call per session: 208392 -> 160275 total tokens (-23.1%). Uncached input 61153 -> 36738 (-39.9%). Cached input differs: 146560 -> 122496. Aggregate elapsed time 70.922 -> 73.235 seconds: no speed claim. Test consumption 368667 tokens; the three additional pairs consumed 275993. The earlier failed sandbox run cost 92364 tokens and is excluded from savings. Native CLI discovery was verified with an empty PATH through the registered official VS Code extension.

macOS/Linux remain untested by owner decision. Windows sandbox file access was verified; resume end-to-end remains unverified. Beta only. Source and skill carry MIT. This build performs no external publication.
'''
    qa_name = stamp + '-second-test.md'
    with (report_dir / qa_name).open('x', encoding='utf-8') as f:
        f.write(qa)
    evidence=[p.relative_to(ROOT).as_posix() for p in (ROOT/'evidence').glob('*.json')]
    payload = {relative: (ROOT / relative).read_bytes() for relative in [*FILES,*evidence]}
    assert payload['LICENSE'] == payload['skill/LICENSE'], 'Installed skill must carry the same MIT license'
    payload[qa_name] = qa.encode('utf-8')
    # Check UTF-8 docs and reject damaged text before packaging.
    assert 'Five task profiles' in payload['README.md'].decode('utf-8')
    assert 'Пять режимов' in payload['README.ru.md'].decode('utf-8')
    for relative, data in payload.items():
        if re.search(rb'[A-Za-z]:[/\\]Users[/\\]', data):
            raise RuntimeError('Absolute user-directory path in release: ' + relative)
        for forbidden in (b'auth.json', b'BEGIN PRIVATE KEY'):
            if forbidden in data and relative not in ('build_release.py', 'build_plugin.py'):
                raise RuntimeError('Local/private marker in release: ' + relative)
    manifest = {'version': w.VERSION, 'license': 'MIT', 'timezone': 'Europe/Moscow',
                'created_at': datetime.now(timezone(timedelta(hours=3))).isoformat(),
                'files': {name: {'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()} for name, data in payload.items()}}
    payload[stamp + '-manifest.json'] = json.dumps(manifest, indent=2).encode('utf-8')
    dist = ROOT / 'dist'; dist.mkdir(exist_ok=True)
    archive = dist / (stamp + '-wedocodex-' + w.VERSION + '.zip')
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for relative, data in payload.items():
            z.writestr('wedocodex/' + relative, data)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert set(z.namelist()) == {'wedocodex/' + name for name in payload}
        for name, data in payload.items():
            assert hashlib.sha256(z.read('wedocodex/' + name)).digest() == hashlib.sha256(data).digest()
        extracted = ROOT / 'qa' / (stamp + '-extracted-package')
        z.extractall(extracted)
    smoke = subprocess.run([sys.executable, '-m', 'unittest', 'test_wedocodex', 'test_release', 'test_lifecycle', 'test_runtime_profiles'],
                           cwd=extracted / 'wedocodex', capture_output=True, text=True)
    if smoke.returncode:
        raise RuntimeError('Extracted package failed: ' + smoke.stderr)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with archive.with_suffix('.sha256').open('x', encoding='utf-8') as f:
        f.write(digest + '  ' + archive.name + '\n')
    print(json.dumps({'archive': str(archive), 'sha256': digest, 'qa_report': str(report_dir / qa_name),
                      'unit_tests': test_count, 'runtime_checks': len(runtime['results']),
                      'extracted_package_tests': test_count}, indent=2))

if __name__ == '__main__':
    main()
