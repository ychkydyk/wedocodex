"""Owned-file transactions with backups, conflict refusal and crash recovery."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import uuid

STATE = 'wedocodex-install.json'
ALLOWED = {'profile:' + name for name in ('token-saver','fast-flow','max-quality','guarded','autopilot')} | {
    'skill:SKILL.md','skill:LICENSE','skill:agents/openai.yaml','skill:references/ultra-config-map.md','skill:scripts/wedocodex.py','skill:scripts/managed_install.py','skill:scripts/runtime_profiles.py'}

def digest(data): return hashlib.sha256(data).hexdigest()
def stamp(): return datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d_%H-%M-%S-%f')
def encode(data): return json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')

def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(stamp() + '-' + uuid.uuid4().hex[:8] + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists(): temporary.unlink()

def target(home, skill_root, key):
    if key not in ALLOWED: raise RuntimeError('Unknown manifest key: ' + key)
    if key.startswith('profile:'):
        path = home / ('wedocodex-' + key.split(':',1)[1] + '.config.toml')
    else:
        path = skill_root / key.split(':',1)[1]
    if path.resolve() != path.absolute():
        raise RuntimeError('Symlink/junction target refused: ' + str(path))
    return path

@contextmanager
def locked(home):
    home.mkdir(parents=True, exist_ok=True)
    lock = home / 'wedocodex.lock'
    try:
        with lock.open('xb') as stream: stream.write(str(os.getpid()).encode('ascii'))
    except FileExistsError:
        raise RuntimeError('WEDOCODEX lock exists. Check for a live installer; do not remove it blindly.')
    try: yield
    finally: lock.unlink()

def load(home):
    path = home / STATE
    if path.resolve() != path.absolute(): raise RuntimeError('Manifest link refused')
    if not path.exists(): raise RuntimeError('No ownership manifest. Preserve the old installation before migrating it.')
    state = json.loads(path.read_text(encoding='utf-8'))
    if state.get('schema') != 1 or state.get('home') != str(home):
        raise RuntimeError('Invalid ownership manifest')
    skill_root = Path(state['skill_root'])
    if not skill_root.is_absolute() or skill_root.name != 'wedocodex' or skill_root.resolve() != skill_root:
        raise RuntimeError('Invalid skill root')
    for key, value in state['files'].items():
        target(home, skill_root, key)
        if not isinstance(value,str) or len(value)!=64: raise RuntimeError('Invalid file digest')
    return state, skill_root

def pending(home):
    for path in (home / 'wedocodex-history').glob('*/journal.json'):
        if not (path.parent/'completed.json').exists():
            raise RuntimeError('Unfinished transaction. Run recover before modifying installation: ' + path.parent.name)

def transaction(home, skill_root, changes, next_state, action):
    # Preflight and backup ALL affected content before the first mutation.
    before = {key: path.read_bytes() if path.exists() else None
              for key in changes for path in [target(home, skill_root, key)]}
    state_path = home / STATE
    state_before = state_path.read_bytes() if state_path.exists() else None
    folder = home / 'wedocodex-history' / (stamp() + '-' + action)
    folder.mkdir(parents=True)
    snapshots = dict(before, **{'state': state_before})
    journal = {'schema':1, 'home':str(home), 'skill_root':str(skill_root), 'action':action,
               'before':{}, 'after': {key: digest(data) if data is not None else None for key,data in changes.items()}}
    for index,(key,data) in enumerate(snapshots.items()):
        filename = str(index) + '.backup'
        if data is not None:
            with (folder/filename).open('xb') as stream:
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
            if (folder/filename).read_bytes()!=data: raise RuntimeError('Backup verification failed')
        journal['before'][key] = {'file':filename, 'sha256':digest(data) if data is not None else None}
    journal['after']['state'] = digest(encode(next_state))
    with (folder/'journal.json').open('xb') as stream:
        stream.write(encode(journal)); stream.flush(); os.fsync(stream.fileno())
    try:
        for key,data in changes.items():
            path = target(home, skill_root, key)
            if (path.read_bytes() if path.exists() else None) != before[key]:
                raise RuntimeError('Concurrent edit detected: ' + str(path))
            if data is None:
                if path.exists(): path.unlink()
            else: atomic(path, data)
        atomic(state_path, encode(next_state))
        for key,data in changes.items():
            path=target(home,skill_root,key)
            if (path.read_bytes() if path.exists() else None)!=data: raise RuntimeError('Readback mismatch')
    except Exception:
        rollback(home, folder)
        raise
    with (folder/'completed.json').open('xb') as stream: stream.write(encode({'result':'committed'}))
    return folder

def rollback(home, folder):
    journal=json.loads((folder/'journal.json').read_text(encoding='utf-8'))
    if journal['home']!=str(home): raise RuntimeError('Recovery home mismatch')
    skill_root=Path(journal['skill_root'])
    if not skill_root.is_absolute() or skill_root.name!='wedocodex' or skill_root.resolve()!=skill_root:
        raise RuntimeError('Recovery root mismatch')
    restore=[]
    for key,record in journal['before'].items():
        path=home/STATE if key=='state' else target(home,skill_root,key)
        if path.resolve()!=path.absolute(): raise RuntimeError('Recovery link refused')
        current=path.read_bytes() if path.exists() else None
        current_hash=digest(current) if current is not None else None
        if current_hash not in (record['sha256'],journal['after'].get(key)):
            raise RuntimeError('Recovery found external changes; preserved: '+str(path))
        backup=folder/record['file']
        if backup.resolve().parent!=folder.resolve(): raise RuntimeError('Invalid backup path')
        data=backup.read_bytes() if record['sha256'] is not None else None
        if data is not None and digest(data)!=record['sha256']: raise RuntimeError('Backup checksum mismatch')
        restore.append((path,data))
    for path,data in restore:
        if data is None:
            if path.exists(): path.unlink()
        else: atomic(path,data)
    with (folder/'completed.json').open('xb') as stream: stream.write(encode({'result':'rolled-back'}))

def manage(action, home, files=None, skills_dir=None, version=None, dry_run=False):
    home=Path(home).resolve()
    if action=='recover':
        with locked(home):
            for path in (home/'wedocodex-history').glob('*/journal.json'):
                if not (path.parent/'completed.json').exists(): rollback(home,path.parent)
        return {'action':'recover'}
    with locked(home):
        pending(home)
        state_exists=(home/STATE).exists()
        old,skill_root=load(home) if state_exists else ({'files':{}},None)
        if action!='install' and not state_exists: raise RuntimeError('No ownership manifest; nothing changed')
        proposed=(Path(skills_dir).resolve()/'wedocodex') if skills_dir else skill_root
        if proposed is None: raise RuntimeError('Skill directory required for first install')
        if skill_root and proposed!=skill_root: raise RuntimeError('Installed skill directory differs; no implicit relocation')
        skill_root=proposed
        data={}
        if files is not None:
            for path,content in files.items():
                path=Path(path).absolute()
                if path.parent==home and path.name.startswith('wedocodex-') and path.name.endswith('.config.toml'):
                    key='profile:'+path.name[len('wedocodex-'):-len('.config.toml')]
                elif path.is_relative_to(skill_root): key='skill:'+path.relative_to(skill_root).as_posix()
                else: raise RuntimeError('Unexpected installation path: '+str(path))
                if target(home,skill_root,key)!=path: raise RuntimeError('Noncanonical path')
                data[key]=content
        conflicts=[]
        for key,expected in old['files'].items():
            path=target(home,skill_root,key)
            if path.exists() and digest(path.read_bytes())!=expected: conflicts.append(str(path))
            if action=='update' and not path.exists(): conflicts.append(str(path)+' (missing)')
        if conflicts: raise RuntimeError('User-modified files preserved: '+', '.join(conflicts))
        if action=='install':
            for key,content in data.items():
                path=target(home,skill_root,key)
                if path.exists() and path.read_bytes()!=content:
                    raise RuntimeError('Existing files differ; use update only with an ownership manifest')
        elif action=='update':
            for key,content in data.items():
                path=target(home,skill_root,key)
                if key not in old['files'] and path.exists() and path.read_bytes()!=content:
                    raise RuntimeError('New target already belongs to the user: '+str(path))
        if action=='uninstall': changes={key:None for key in old['files']}
        else:
            changes={key:content for key,content in data.items()
                     if not target(home,skill_root,key).exists() or target(home,skill_root,key).read_bytes()!=content}
            changes.update({key:None for key in old['files'] if key not in data})
        next_state={'schema':1,'home':str(home),'skill_root':str(skill_root),'version':version or old.get('version'),
                    'status':'uninstalled' if action=='uninstall' else 'installed',
                    'files':{} if action=='uninstall' else {key:digest(content) for key,content in data.items()}}
        summary={'action':action,'dry_run':dry_run,'changed_files':len(changes),'version':next_state['version']}
        if dry_run: return summary
        if not changes and state_exists and next_state==old: return summary
        summary['backup']=str(transaction(home,skill_root,changes,next_state,action))
        return summary
