"""Second-pass regression suite. No model calls or user's config mutations."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from skill.scripts import wedocodex as w

class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wedocodex-test-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)

    def test_resume_cannot_inject_cli_switches(self):
        for invalid in ('--last', '--dangerously-bypass-approvals-and-sandbox', '-m', 'a\nb'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                w.command('guarded', '.', resume=invalid)

    def test_child_receives_exact_unicode_arguments(self):
        # A real child process records argv; no command string is built or evaluated.
        recorder = self.home / 'record.py'
        recorder.write_text('import json,sys; print(json.dumps(sys.argv[1:], ensure_ascii=False))', encoding='utf-8')
        prompt = 'Проверка "кавычек" & $(echo NO) ; %PATH% !value!\nline two'
        args = w.command('token-saver', self.home / 'папка с пробелами', prompt=prompt)[1:]
        result = subprocess.run([sys.executable, str(recorder), *args], capture_output=True,
                                text=True, encoding='utf-8', env=dict(os.environ, PYTHONIOENCODING='utf-8'), check=True)
        self.assertEqual(json.loads(result.stdout), args)

    def test_explicit_model_override(self):
        values = w.settings('token-saver', 'available-model', 'high')
        self.assertEqual(values['model'], 'available-model')
        self.assertEqual(values['model_reasoning_effort'], 'high')
        self.assertEqual(values['sandbox_mode'], 'workspace-write')
        for effort in ('ultra', 'INVALID'):
            with self.assertRaises(ValueError):
                w.settings('token-saver', effort=effort)

    def test_saver_autopilot_keeps_limits_and_model(self):
        s=w.settings('token-saver',autopilot=True)
        self.assertEqual((s['model'],s['model_reasoning_effort']),('gpt-6-luna','low'))
        self.assertEqual((s['skills.max_context_tokens'],s['tool_output_token_limit']),(2000,6000))
        self.assertTrue(s['tui.auto_recap'])
        self.assertTrue(s['tui.notifications'])
        self.assertNotIn('agents.enabled',s)
        args=w.command('token-saver',self.home,autopilot=True)
        self.assertIn('milestones',args[-1])
        self.assertIn('targeted searches',args[-1])

    def test_autopilot_overlay_does_not_weaken_guarded(self):
        with self.assertRaises(ValueError):w.settings('guarded',autopilot=True)
        result=subprocess.run([sys.executable,str(w.ROOT/'scripts/wedocodex.py'),'show','guarded','--autopilot'],capture_output=True,text=True)
        self.assertEqual(result.returncode,2)

    def test_combined_cli_show_applies_overlay(self):
        result=subprocess.run([sys.executable,str(w.ROOT/'scripts/wedocodex.py'),'show','saver','--autopilot','--model','gpt-6.1-sol','--effort','medium'],capture_output=True,text=True,check=True)
        s=json.loads(result.stdout)['settings']
        self.assertEqual((s['model'],s['model_reasoning_effort']),('gpt-6.1-sol','medium'))
        self.assertTrue(s['tui.notifications'])

    def test_catalog_missing_corrupt_wrong_shape_and_unsupported(self):
        with self.assertRaises(RuntimeError):
            w.check_catalog(self.home, 'token-saver')
        path = self.home / 'models_cache.json'
        for content in ('broken', '[]', '{"models":null}', '{"models":[null]}', '{"models":[]}'):
            path.write_text(content, encoding='utf-8')
            with self.subTest(content=content), self.assertRaises((ValueError, RuntimeError)):
                w.check_catalog(self.home, 'token-saver')
        path.write_text(json.dumps({'models': [{'slug': 'explicit', 'supported_reasoning_levels': [{'effort': 'low'}]}]}))
        with contextlib.redirect_stdout(io.StringIO()):
            w.check_catalog(self.home, 'token-saver', 'explicit', 'low')
        with self.assertRaises(RuntimeError):
            w.check_catalog(self.home, 'token-saver', 'explicit', 'max')

    def test_conflict_is_detected_before_any_write(self):
        conflict = self.home / 'skills/wedocodex/SKILL.md'
        conflict.parent.mkdir(parents=True)
        conflict.write_text('user-owned')
        with self.assertRaises(RuntimeError):
            w.install(self.home)
        self.assertEqual(conflict.read_text(), 'user-owned')
        self.assertEqual(list(self.home.glob('*.config.toml')), [])

    def test_rollback_on_late_write_failure(self):
        base = self.home / 'config.toml'; base.write_text('# user config')
        original = w.lifecycle.atomic
        failed = False
        def failing_write(path, data):
            nonlocal failed
            if path.name == 'wedocodex.py' and not failed:
                failed = True
                raise PermissionError('simulated filesystem denial')
            return original(path, data)
        with patch.object(w.lifecycle, 'atomic', failing_write), self.assertRaises(PermissionError):
            w.install(self.home)
        self.assertFalse(any(p.exists() for p in w.install_files(self.home)))
        self.assertEqual(base.read_text(), '# user config')

    def test_installed_skill_runs_without_source_checkout(self):
        skills = self.home / 'arbitrary portable skills'
        with contextlib.redirect_stdout(io.StringIO()):
            w.install(self.home / 'codex', skills)
        script = skills / 'wedocodex/scripts/wedocodex.py'
        result = subprocess.run([sys.executable, str(script), 'show', 'guarded'], cwd=self.home,
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)['settings']['sandbox_mode'], 'read-only')
        # Self-contained install also works from this copy, not the source checkout.
        child_home = self.home / 'another-home'
        subprocess.run([sys.executable, str(script), 'install', '--home', str(child_home)],
                       cwd=self.home, capture_output=True, text=True, check=True)
        self.assertEqual(script.read_bytes(), (child_home / 'skills/wedocodex/scripts/wedocodex.py').read_bytes())

    def test_install_excludes_unlisted_payload(self):
        files = w.install_files(self.home)
        self.assertEqual(len(files), 12)
        self.assertFalse(any('reports' in str(path) or '__pycache__' in str(path) for path in files))

    def test_noninteractive_menu_returns_actionable_error(self):
        result = subprocess.run([sys.executable, str(w.ROOT / 'scripts/wedocodex.py')],
                                input='', capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn('requires a terminal', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_install_only_flags_not_silently_ignored(self):
        result = subprocess.run([sys.executable, str(w.ROOT / 'scripts/wedocodex.py'),
                                 'show', 'guarded', '--home', str(self.home)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)

    def test_batch_shim_not_executed(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(w.shutil, 'which', return_value='C:/tools/codex.cmd'), patch.object(w, 'vscode_executables', return_value=[]), self.assertRaises(RuntimeError):
            w.resolve_executable()

    @unittest.skipUnless(os.name == 'nt', 'Windows bundle fallback')
    def test_missing_path_uses_registered_official_bundle(self):
        root = self.home / '.vscode/extensions'
        relative = 'openai.chatgpt-26.1007.21434-win32-x64'
        bundle = root / relative
        native = bundle / 'bin/windows-x86_64/codex.exe'
        native.parent.mkdir(parents=True)
        native.write_bytes(b'test fixture; never executed')
        (bundle / 'package.json').write_text(json.dumps({'publisher': 'openai', 'name': 'chatgpt'}))
        (root / 'extensions.json').write_text(json.dumps([
            {'identifier': {'id': 'openai.chatgpt'}, 'relativeLocation': relative}]))
        with patch.dict(os.environ, {}, clear=True), patch.object(w.shutil, 'which', return_value=None), patch.object(w.Path, 'home', return_value=self.home), patch.object(w.platform, 'machine', return_value='AMD64'):
            self.assertEqual(w.resolve_executable(), str(native.resolve()))
            # A bundle with the wrong publisher must never be selected.
            (bundle / 'package.json').write_text(json.dumps({'publisher': 'someone-else', 'name': 'chatgpt'}))
            with self.assertRaises(RuntimeError):
                w.resolve_executable()

    def test_invalid_explicit_executable_does_not_fall_back(self):
        with patch.dict(os.environ, {'WEDOCODEX_CODEX_EXE': str(self.home / 'missing.exe')}), patch.object(w.shutil, 'which', return_value='valid-codex'), self.assertRaises(RuntimeError):
            w.resolve_executable()

    @unittest.skipUnless(os.name == 'nt', 'Windows bundle discovery')
    def test_unregistered_or_malformed_extension_is_not_selected(self):
        root = self.home / '.vscode/extensions'
        native = root / 'openai.chatgpt-999.0.0/bin/windows-x86_64/codex.exe'
        native.parent.mkdir(parents=True)
        native.write_bytes(b'not registered; never executed')
        with patch.object(w.Path, 'home', return_value=self.home), patch.object(w.platform, 'machine', return_value='AMD64'):
            self.assertEqual(w.vscode_executables(), [])
            (root / 'extensions.json').write_text('broken')
            self.assertEqual(w.vscode_executables(), [])

if __name__ == '__main__':
    unittest.main()
