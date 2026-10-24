"""Adopt an exact beta.1 installation using its verified release ZIP, then update."""
import argparse
import hashlib
from pathlib import Path
import zipfile
from skill.scripts import wedocodex as w

def migrate(home, skills_dir, archive, expected_sha256):
    home=Path(home).resolve(); skills_dir=Path(skills_dir).resolve()
    if hashlib.sha256(Path(archive).read_bytes()).hexdigest()!=expected_sha256:
        raise RuntimeError('Legacy archive SHA-256 mismatch')
    if (home/w.lifecycle.STATE).exists():
        raise RuntimeError('Ownership manifest already exists; use regular update')
    legacy={home/f'wedocodex-{name}.config.toml':w.profile_bytes(name) for name in w.PROFILES}
    with zipfile.ZipFile(archive) as z:
        for relative in ('SKILL.md','agents/openai.yaml','scripts/wedocodex.py'):
            legacy[skills_dir/'wedocodex'/relative]=z.read('wedocodex/skill/'+relative)
    for path,data in legacy.items():
        if not path.exists() or path.read_bytes()!=data:
            raise RuntimeError('Legacy file does not match baseline; preserved: '+str(path))
    w.lifecycle.manage('install',home,legacy,skills_dir,'0.2.0-beta.1')
    return w.lifecycle.manage('update',home,w.install_files(home,skills_dir),skills_dir,w.VERSION)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=Path,required=True)
    parser.add_argument('--skills-dir',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--sha256',required=True)
    opts=parser.parse_args()
    print(migrate(opts.home,opts.skills_dir,opts.baseline,opts.sha256))
