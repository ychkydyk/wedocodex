import contextlib
import io
import json
from pathlib import Path
import tempfile
import zipfile
import unittest
from unittest.mock import patch
from skill.scripts import wedocodex as w

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='wedocodex-owned-')
        self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name)
        self.skills=self.home/'skills'
        self.files=w.install_files(self.home,self.skills)
        with contextlib.redirect_stdout(io.StringIO()): w.install(self.home,self.skills)
        self.state=self.home/w.lifecycle.STATE

    def changed(self):
        files=dict(self.files)
        for path in files:
            if path.suffix=='.toml': files[path]+=b'# new version\n'
        return files

    def test_update_and_backup(self):
        prior=self.state.read_bytes()
        result=w.lifecycle.manage('update',self.home,self.changed(),version='next')
        self.assertEqual(json.loads(self.state.read_text())['version'],'next')
        for path,data in self.changed().items(): self.assertEqual(path.read_bytes(),data)
        backups=[p.read_bytes() for p in Path(result['backup']).glob('*.backup')]
        self.assertIn(prior,backups)

    def test_modified_file_blocks_update_and_uninstall(self):
        path=next(iter(self.files)); path.write_bytes(b'# user edit')
        before={p:p.read_bytes() for p in self.files}; state=self.state.read_bytes()
        for action in ('update','uninstall'):
            with self.assertRaises(RuntimeError):
                w.lifecycle.manage(action,self.home,self.changed() if action=='update' else None,version='next')
        self.assertEqual(state,self.state.read_bytes())
        self.assertEqual(before,{p:p.read_bytes() for p in self.files})

    def test_uninstall_preserves_unknown_files_and_base(self):
        extra=self.skills/'wedocodex'/'personal-note.txt'; extra.write_text('mine')
        base=self.home/'config.toml'; base.write_text('existing')
        result=w.lifecycle.manage('uninstall',self.home)
        self.assertFalse(any(path.exists() for path in self.files))
        self.assertEqual(extra.read_text(),'mine'); self.assertEqual(base.read_text(),'existing')
        self.assertEqual(json.loads(self.state.read_text())['status'],'uninstalled')
        self.assertTrue(Path(result['backup']).is_dir())

    def test_dry_run_leaves_payload_and_state_unchanged(self):
        before={p:p.read_bytes() for p in [*self.files,self.state]}
        result=w.lifecycle.manage('uninstall',self.home,dry_run=True)
        self.assertTrue(result['dry_run'])
        self.assertEqual(before,{p:p.read_bytes() for p in before})

    def test_rollback_after_update_write_failure(self):
        before={p:p.read_bytes() for p in [*self.files,self.state]}
        original=w.lifecycle.atomic; counter=0
        def fail_once(path,data):
            nonlocal counter
            counter+=1
            if counter==2: raise PermissionError('simulated late failure')
            original(path,data)
        with patch.object(w.lifecycle,'atomic',fail_once),self.assertRaises(PermissionError):
            w.lifecycle.manage('update',self.home,self.changed(),version='next')
        self.assertEqual(before,{p:p.read_bytes() for p in before})

    def test_recover_interrupted_transaction(self):
        before={p:p.read_bytes() for p in [*self.files,self.state]}
        original=w.lifecycle.atomic; counter=0
        def interrupt(path,data):
            nonlocal counter
            counter+=1
            if counter==2: raise KeyboardInterrupt()
            original(path,data)
        with patch.object(w.lifecycle,'atomic',interrupt),self.assertRaises(KeyboardInterrupt):
            w.lifecycle.manage('update',self.home,self.changed(),version='next')
        with self.assertRaises(RuntimeError): w.lifecycle.manage('uninstall',self.home)
        w.lifecycle.manage('recover',self.home)
        self.assertEqual(before,{p:p.read_bytes() for p in before})

    def test_tampered_manifest_cannot_target_arbitrary_file(self):
        outside=self.home/'keep.txt'; outside.write_text('do not delete')
        state=json.loads(self.state.read_text()); state['files']['skill:../../keep.txt']='0'*64
        self.state.write_text(json.dumps(state))
        with self.assertRaises(RuntimeError): w.lifecycle.manage('uninstall',self.home)
        self.assertEqual(outside.read_text(),'do not delete')

    def test_reinstall_after_uninstall(self):
        w.lifecycle.manage('uninstall',self.home)
        with contextlib.redirect_stdout(io.StringIO()): w.install(self.home,self.skills)
        self.assertEqual(json.loads(self.state.read_text())['status'],'installed')
        for path,data in self.files.items(): self.assertEqual(path.read_bytes(),data)

    def test_lock_refuses_concurrent_operation(self):
        lock=self.home/'wedocodex.lock'; lock.write_text('123')
        with self.assertRaises(RuntimeError): w.lifecycle.manage('uninstall',self.home)
        self.assertTrue(lock.exists())

    def test_missing_file_blocks_update_but_allows_uninstall(self):
        next(iter(self.files)).unlink()
        with self.assertRaises(RuntimeError): w.lifecycle.manage('update',self.home,self.changed(),version='next')
        w.lifecycle.manage('uninstall',self.home)
        self.assertFalse(any(path.exists() for path in self.files))

    def legacy_archive(self):
        archive=self.home/'baseline.zip'
        with zipfile.ZipFile(archive,'x') as z:
            for relative in ('SKILL.md','agents/openai.yaml','scripts/wedocodex.py'):
                z.write(self.skills/'wedocodex'/relative,'wedocodex/skill/'+relative)
        self.state.unlink()
        (self.skills/'wedocodex/scripts/managed_install.py').unlink()
        return archive

    def test_legacy_migration_requires_matching_baseline(self):
        from migrate_legacy import migrate
        archive=self.legacy_archive()
        with self.assertRaises(RuntimeError): migrate(self.home,self.skills,archive,'0'*64)
        self.assertFalse(self.state.exists())
        result=migrate(self.home,self.skills,archive,w.lifecycle.digest(archive.read_bytes()))
        self.assertEqual(result['action'],'update')
        self.assertTrue((self.skills/'wedocodex/scripts/managed_install.py').exists())

    def test_legacy_migration_preserves_user_changes(self):
        from migrate_legacy import migrate
        archive=self.legacy_archive()
        changed=self.skills/'wedocodex/SKILL.md'; changed.write_text('my edits')
        with self.assertRaises(RuntimeError):
            migrate(self.home,self.skills,archive,w.lifecycle.digest(archive.read_bytes()))
        self.assertEqual(changed.read_text(),'my edits')
        self.assertFalse(self.state.exists())

if __name__=='__main__': unittest.main()
