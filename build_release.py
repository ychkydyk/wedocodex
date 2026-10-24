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
FILES = ['assets/2026-10-24_22-15-51-wedocodex-projector-without-skill.png', 'README.md', 'LICENSE', '.gitignore', 'wedocodex.py', 'wedocodex.cmd',
         'test_wedocodex.py', 'test_release.py', 'test_lifecycle.py', 'verify_runtime.py', 'build_release.py',
         'migrate_legacy.py', 'bench_live.py', 'probe_quota.py',
         'skill/SKILL.md', 'skill/LICENSE', 'skill/agents/openai.yaml', 'skill/scripts/wedocodex.py', 'skill/scripts/managed_install.py']

def main():
    stamp = datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d_%H-%M-%S-%f')
    report_dir = ROOT / 'reports'; report_dir.mkdir(exist_ok=True)
    test = subprocess.run([sys.executable, '-m', 'unittest', '-v', 'test_wedocodex', 'test_release', 'test_lifecycle'],
                          cwd=ROOT, capture_output=True, text=True)
    with (report_dir / (stamp + '-second-test.log')).open('x', encoding='utf-8') as f:
        f.write(test.stdout + test.stderr)
    if test.returncode:
        raise RuntimeError(test.stderr)
    runtime = run_suite()
    cli_version = subprocess.run([shutil.which('codex'), '--version'], capture_output=True, text=True, check=True).stdout.strip()
    qa = f'''# WEDOCODEX release verification - {w.VERSION}

Date: {datetime.now(timezone(timedelta(hours=3))).isoformat()}. Time zone: Europe/Moscow.
Platform: Windows. CLI: {cli_version}. Python: {sys.version.split()[0]}.

26 regression tests passed. 7 local App Server config checks passed.

Verified: self-contained installed skill; conflict preflight; rollback on a simulated late write failure; literal Unicode/quoted arguments in a real child process; refusal of batch shims and option-shaped session IDs; invalid catalog handling; explicit model overrides; noninteractive menu errors; all five effective presets; launcher overrides beat a loaded trusted-project conflict; malformed TOML is rejected.

Manual skill review: bare invocation offers choices; explicit activation changes behavior only; a review request does not activate a mode; mode switching preserves the task and approvals; no inferred session IDs; no automatic agents or publishing; checkpoints are milestone-based. This review is not an independent model evaluation.

Fixed since v1: absolute workstation paths and missing launcher in installed skill; incomplete argument validation; nonportable Windows argument forwarding; partial install on write failure; misleading catalog/access wording; profile discussion could unintentionally activate behavior.

This build command performs no inference. A separate two-request smoke test produced correct answers: requested Luna/low used 15865 input + 36 output tokens in 7.1 seconds; requested Sol/medium used 18252 input + 62 output tokens in 8.4 seconds. Reasoning tokens 0/24 are subsets of output. One trial per profile; model/system context differs; not a general savings benchmark. The independent served model ID was not exposed in CLI events. The completion notify hook ran twice; visible terminal notification delivery is unverified. Account quota figures are omitted from the public report.

Update/uninstall/recover use owned-file hashes, verified timestamped backups and per-file atomic writes. User edits block changes. Interrupted transactions are recoverable; stale locks after hard process termination require checking that the installer has stopped. Two additional tests cover exact-baseline migration and refusal of a modified legacy installation.

macOS/Linux remain untested by owner decision. OS sandbox enforcement and resume end-to-end remain unverified. Beta only. The source and portable installed skill are licensed under MIT starting with beta.3. No external publication.
'''
    qa_name = stamp + '-second-test.md'
    with (report_dir / qa_name).open('x', encoding='utf-8') as f:
        f.write(qa)
    payload = {relative: (ROOT / relative).read_bytes() for relative in FILES}
    assert payload['LICENSE'] == payload['skill/LICENSE'], 'Installed skill must carry the same MIT license'
    payload[qa_name] = qa.encode('utf-8')
    # Check UTF-8 docs and reject damaged text before packaging.
    assert 'Пять режимов' in payload['README.md'].decode('utf-8')
    for relative, data in payload.items():
        if re.search(rb'[A-Za-z]:[/\\]Users[/\\]', data):
            raise RuntimeError('Absolute user-directory path in release: ' + relative)
        for forbidden in (b'auth.json', b'BEGIN PRIVATE KEY'):
            if forbidden in data and relative != 'build_release.py':
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
    smoke = subprocess.run([sys.executable, '-m', 'unittest', 'test_wedocodex', 'test_release', 'test_lifecycle'],
                           cwd=extracted / 'wedocodex', capture_output=True, text=True)
    if smoke.returncode:
        raise RuntimeError('Extracted package failed: ' + smoke.stderr)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with archive.with_suffix('.sha256').open('x', encoding='utf-8') as f:
        f.write(digest + '  ' + archive.name + '\n')
    print(json.dumps({'archive': str(archive), 'sha256': digest, 'qa_report': str(report_dir / qa_name),
                      'unit_tests': 26, 'runtime_checks': len(runtime['results']),
                      'extracted_package_tests': 26}, indent=2))

if __name__ == '__main__':
    main()
