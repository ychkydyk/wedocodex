import tempfile
import unittest
from pathlib import Path
import tomllib
import wedocodex as w

class ProfileTests(unittest.TestCase):
    def test_profiles_and_sandbox(self):
        for name in w.PROFILES:
            data = tomllib.loads(w.profile_bytes(name).decode())
            self.assertNotEqual(data['sandbox_mode'], 'danger-full-access')
            self.assertFalse(data['sandbox_workspace_write']['network_access'])
        guarded = tomllib.loads(w.profile_bytes('guarded').decode())
        self.assertEqual((guarded['sandbox_mode'], guarded['approval_policy']), ('read-only', 'never'))

    def test_literal_arguments_and_explicit_resume(self):
        prompt = 'literal $(whoami); "quoted" & text'
        args = w.command('fast-flow', '.', 'session-123', prompt)
        self.assertEqual(args[1:3], ['resume', 'session-123'])
        self.assertTrue(args[-1].endswith(prompt))
        self.assertNotIn('--last', args)
        self.assertNotIn('resume', w.command('token-saver', '.'))

    def test_install_idempotent_and_preserves_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            base = home / 'config.toml'
            base.write_bytes(b'# existing settings\n')
            w.install(home)
            before = {p: p.read_bytes() for p in w.install_files(home)}
            w.install(home)
            self.assertEqual(before, {p: p.read_bytes() for p in w.install_files(home)})
            self.assertEqual(base.read_bytes(), b'# existing settings\n')
            target = home / 'wedocodex-guarded.config.toml'
            target.write_bytes(b'# owner custom setting\n')
            with self.assertRaises(RuntimeError):
                w.install(home)
            self.assertEqual(target.read_bytes(), b'# owner custom setting\n')

if __name__ == '__main__':
    unittest.main()
