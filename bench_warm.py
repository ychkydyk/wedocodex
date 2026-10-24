"""Two warm continuation pairs on already-created A/B benchmark threads."""
from datetime import datetime,timedelta,timezone
import argparse,json,os,subprocess,time
from pathlib import Path
from bench_mechanics import TASKS
from bench_ab import budget_guard
from probe_quota import quota
from skill.scripts import wedocodex as w

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--home',type=Path,required=True);p.add_argument('--source',type=Path,required=True)
    p.add_argument('--baseline',type=Path);p.add_argument('--ceiling',type=int,default=30);args=p.parse_args()
    if not args.run:print('No inference without --run');return
    if not args.baseline:p.error('Explicit quota baseline required for safety, independently of per-request token measurement')
    baseline=json.loads(args.baseline.read_text(encoding='utf-8'))
    source=json.loads(args.source.read_text(encoding='utf-8'))
    cases={row['condition']:row for row in source['rows'] if row['task']=='review'}
    cwd=Path(source['workspace']);task=TASKS[1][1];expected=TASKS[1][2]
    stamp=datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d_%H-%M-%S-%f')
    root=Path(__file__).resolve().parent/'qa'/(stamp+'-warm-continuations');root.mkdir(parents=True)
    rows=[]
    for index,condition in enumerate(['A','B','B','A'],1):
        budget_guard(quota(args.home,Path(__file__).resolve().parent),baseline,args.ceiling)
        case=cases[condition];run=root/(str(index)+'-'+condition);run.mkdir()
        cmd=[w.resolve_executable(),'exec','resume','--ignore-user-config','--json','--skip-git-repo-check']
        for key,val in case['config'].items():cmd+=['-c',key+'='+json.dumps(val)]
        # Same follow-up task; the mode instruction is already in B's history.
        cmd += [case['thread_id'],task]
        start=time.monotonic()
        with (run/'events.jsonl').open('xb') as out,(run/'stderr.log').open('xb') as err:
            r=subprocess.run(cmd,cwd=cwd,env=dict(os.environ,CODEX_HOME=str(args.home)),stdin=subprocess.DEVNULL,stdout=out,stderr=err,timeout=120)
        elapsed=round(time.monotonic()-start,3)
        events=[json.loads(line) for line in (run/'events.jsonl').read_text(encoding='utf-8').splitlines() if line.startswith('{')]
        message=next((x['item'].get('text','') for x in reversed(events) if x.get('type')=='item.completed' and x.get('item',{}).get('type')=='agent_message'),'')
        try:correct=json.loads(message)==expected
        except ValueError:correct=False
        # Read per-request last usage, not a potentially cumulative CLI total.
        with w.runtime.Rpc(w.resolve_executable(),args.home,cwd) as rpc:
            rpc.request('thread/resume',{'threadId':case['thread_id'],'excludeTurns':True})
            usage=rpc.notification('thread/tokenUsage/updated',case['thread_id'])['tokenUsage']
        row={'index':index,'condition':condition,'correct':correct,'seconds':elapsed,'exit_code':r.returncode,'token_usage':usage}
        with (run/'result.json').open('x',encoding='utf-8') as f:json.dump(row,f,indent=2)
        rows.append(row);print(json.dumps(row),flush=True)
        if not correct or r.returncode:break
    with (root/'summary.json').open('x',encoding='utf-8') as f:json.dump({'rows':rows,'scope':'two warm continuations per condition, same code-review task'},f,indent=2)
    print(root,flush=True)

if __name__=='__main__':main()
