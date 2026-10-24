"""Offline prompt-size probe; retains only counts, never raw user prompt/config."""
from datetime import datetime,timedelta,timezone
import hashlib,json,os
from pathlib import Path
import subprocess,tempfile
from skill.scripts import wedocodex as w

def probe(home):
    results=[]
    with tempfile.TemporaryDirectory(prefix='wedocodex-context-') as directory:
        for budget in (None,2000,1200):
            args=[w.resolve_executable(),'-c','model="gpt-6.1-sol"']
            if budget is not None:args+=['-c','skills.max_context_tokens='+str(budget)]
            args+=['debug','prompt-input','Return only the number 1. Do not use tools.']
            r=subprocess.run(args,cwd=directory,env=dict(os.environ,CODEX_HOME=str(home)),
                             capture_output=True,text=True,encoding='utf-8',timeout=25)
            if r.returncode:
                results.append({'budget':budget,'error':'Prompt probe failed','stderr_tail':r.stderr[-300:]});continue
            data=json.loads(r.stdout)
            def strings(node):
                if isinstance(node,str):yield node
                elif isinstance(node,dict):
                    for v in node.values():yield from strings(v)
                elif isinstance(node,list):
                    for v in node:yield from strings(v)
            values=list(strings(data))
            results.append({'budget':budget,'characters':sum(len(s) for s in values),
                            'utf8_bytes':sum(len(s.encode()) for s in values),
                            'strings':len(values),'catalog_strings':sum('Available skills' in s for s in values),
                            'warnings':len(r.stderr.splitlines()),
                            'sha256':hashlib.sha256(r.stdout.encode()).hexdigest()})
    return results

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);a=p.parse_args()
    rows=probe(a.home);print(json.dumps(rows,indent=2));print(w.save_report('context-probe',rows))
