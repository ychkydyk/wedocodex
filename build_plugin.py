"""Build and locally validate a skills-only Codex plugin ZIP; no publication."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from skill.scripts import wedocodex as w

ROOT = Path(__file__).resolve().parent
SKILL_FILES = ['SKILL.md', 'LICENSE', 'agents/openai.yaml', 'references/ultra-config-map.md',
               'scripts/wedocodex.py', 'scripts/managed_install.py', 'scripts/runtime_profiles.py']


def main():
    stamp = datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d_%H-%M-%S-%f')
    identity = dict(name='wedocodex', version=w.VERSION,
                    description='Five explicit Codex modes with native context limits and safe profile management.',
                    author={'name': 'WEDOIT'}, repository='https://github.com/ychkydyk/wedocodex',
                    license='MIT', keywords=['codex', 'productivity', 'profiles'])
    interface = dict(displayName='WEDOCODEX', shortDescription='Choose a Codex mode for your task',
                     longDescription='Token Saver, Fast Flow, Max Quality, Guarded and Autopilot. '
                     'Native startup context limits require the local Python launcher. '
                     'A text invocation does not change model, permissions or startup context. '
                     'Windows beta; macOS/Linux untested.',
                     developerName='WEDOIT', category='Productivity',
                     defaultPrompt=['Use WEDOCODEX to show the five modes without activating one.'])
    portable = dict(identity, **{'$schema': 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json',
                                'extensions': {'com.openai': {'interface': interface}}})
    compatibility = dict(identity, skills='./skills/', interface=interface)
    encode = lambda x: (json.dumps(x, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    payload = {'plugin.json': encode(portable), '.codex-plugin/plugin.json': encode(compatibility),
               'LICENSE': (ROOT/'LICENSE').read_bytes()}
    for relative in SKILL_FILES:
        payload['skills/wedocodex/'+relative] = (ROOT/'skill'/relative).read_bytes()
    payload['README.md'] = ('''# WEDOCODEX plugin

Local Codex beta; Python 3.11+ and Codex CLI are required for runtime controls.
Install this ZIP through a client that accepts local plugins, then invoke the
bundled wedocodex skill. Avoid enabling a duplicate standalone skill at the same time.

For full startup settings, run the bundled skills/wedocodex/scripts/wedocodex.py:
    python <plugin-folder>/skills/wedocodex/scripts/wedocodex.py run saver --workspace <project>
This creates a new terminal session. It does not reconfigure an existing IDE chat.
The launcher finds native Codex on PATH or in registered official VS Code extensions.

Autopilot uses Sol 6.1/medium, recap, terminal notifications and milestone checkpoints.
Combine Saver and Autopilot with run saver --autopilot. The combination retains
Saver's model and context limits. A separate live test verified its result and checkpoint.
It does not create scheduled jobs, mobile push or Telegram delivery, and cannot
continue after Codex is closed. Spending and sending require task authorization.

Four paired file tasks / eight sessions: 208392 -> 160275 total tokens (-23.1%),
all correct, one tool call per session. Uncached input 61153 -> 36738 (-39.9%),
cache differs. Total elapsed time 70.922 -> 73.235 seconds. Small fixtures,
not a production-project evaluation or a general cost or speed promise.
Previous three no-tool task pairs: -23.1% total tokens. Do not combine the two
experiments into a universal savings percentage.

Inspired by Ultra Config by Daniel (San) Avila / davila7, independently adapted
to supported native Codex settings. Original author:
https://dev.to/dani_avila7/ultra-config-switches-your-whole-claude-code-setup-between-five-profiles-mid-session-4199

No credentials, account data, telemetry collector, MCP server or automatic hooks
are included. The skill and launcher use the permissions and connections of the host.
macOS/Linux and installation through the public directory remain unverified.
This archive is prepared for upload, not already published or approved.

Packaging references:
https://developers.openai.com/plugins/build/plugins
https://developers.openai.com/plugins/deploy/submission-errors
''').encode('utf-8')
    manifest = {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                for name, data in payload.items()}
    payload['package-integrity.json'] = encode({'version': w.VERSION, 'timezone': 'Europe/Moscow',
                                               'created_at': stamp, 'files': manifest})
    archive = ROOT/'dist'/(stamp+'-wedocodex-plugin-'+w.VERSION+'.zip')
    archive.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED) as z:
        for name, data in payload.items():
            assert '..' not in Path(name).parts and not Path(name).is_absolute()
            assert b'BEGIN PRIVATE KEY' not in data
            z.writestr('wedocodex/'+name, data)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and len(z.infolist()) < 5000
        assert sum(i.file_size for i in z.infolist()) < 512*1024**2
        for name, data in payload.items():
            assert z.read('wedocodex/'+name) == data
        folder = ROOT/'qa'/(stamp+'-plugin-extracted')
        z.extractall(folder)
    assert archive.stat().st_size < 100*1024**2
    script = folder/'wedocodex/skills/wedocodex/scripts/wedocodex.py'
    result = subprocess.run([sys.executable, str(script), 'show', 'saver'],
                            cwd=folder, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['settings']['skills.max_context_tokens'] == 2000
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with archive.with_suffix('.sha256').open('x', encoding='utf-8') as f:
        f.write(digest+'  '+archive.name+'\n')
    print(json.dumps({'archive': str(archive), 'sha256': digest, 'entries': len(payload),
                      'extracted_launcher_verified': True, 'model_requests': 0,
                      'directory_upload_verified': False}, indent=2))


if __name__ == '__main__':
    main()
