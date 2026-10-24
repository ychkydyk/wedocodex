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
        with patch.object(w.shutil, 'which', return_value='C:/tools/codex.cmd'), self.assertRaises(RuntimeError):
            w.resolve_executable()

if __name__ == '__main__':
    unittest.main()
