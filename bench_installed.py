"""Two opt-in fresh sessions; use installed launcher, never alter shared config."""
import argparse, hashlib, json, os, random, subprocess, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
installed_roots = [HOME / 'skills/wedocodex/scripts', Path.home() / '.agents/skills/wedocodex/scripts']
installed_root = next((p for p in installed_roots if (p / 'wedocodex.py').is_file()), None)
if installed_root is None:
    raise RuntimeError('Install WEDOCODEX locally before running the installed-skill benchmark.')
sys.path.insert(0, str(installed_root))
import wedocodex as w
from runtime_profiles import Rpc, value
sys.path.append(str(ROOT))
from probe_quota import quota
from preflight_tools import check as check_file_access

TASK = ('Read only orders.json in this workspace. Keep state exactly paid, normalize client '
        'by trimming whitespace and lowercasing, sum amount_cents including refunds. '
        'Use one local tool call for the data calculation if possible. Do not change files, '
        'delegate, browse or read unrelated files. If a tool is denied, stop immediately without retrying. Return only JSON with totals (client keys '
        'alphabetically sorted), grand_total_cents and paid_rows.')

def save(path, data):
    with path.open('x', encoding='utf-8') as f: json.dump(data, f, indent=2)

def main():
    global ROOT
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');a=p.parse_args()
    if not a.run: print('2 sessions, same Sol 6.1/medium, installed launcher B; no automatic retry.');return
    ROOT = ROOT / 'qa' / (datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d_%H-%M-%S-%f')+'-installed-profile-fixed-test')
    ROOT.mkdir(parents=True)
    rng=random.Random(241026)
    records=[dict(client=rng.choice([' Alice ','BOB','alice',' bob ','Carol']),
                  amount_cents=rng.randint(-500,5000),state=rng.choice(['paid','paid','pending','failed'])) for _ in range(80)]
    totals={};count=0
    for row in records:
        if row['state']=='paid':
            key=row['client'].strip().lower();totals[key]=totals.get(key,0)+row['amount_cents'];count+=1
    expected=dict(totals=dict(sorted(totals.items())),grand_total_cents=sum(totals.values()),paid_rows=count)
    common={'model':'gpt-6.1-sol','model_reasoning_effort':'medium','sandbox_mode':'workspace-write',
            'approval_policy':'never','sandbox_workspace_write.network_access':False,
            'tui.auto_recap':False,'web_search':'disabled','notify':[]}
    save(ROOT/'plan.json',dict(timezone='Europe/Moscow',sessions=2,task=TASK,model=common['model'],
        effort='medium',target_max_reported_tokens=100000,reserve_for_second_session=50000,
        scope='Installed-launcher A/B on one file aggregation task; no repeated samples.',
        limitation='Admission budget checked between sessions; an in-flight turn is not a strict token cap.'))
    rows=[];stopped=None
    for condition in ['A','B']:
        if sum(r['total_tokens'] or 0 for r in rows)>50000:stopped='Insufficient 50000-token admission reserve';break
        before=quota(HOME,ROOT)
        if any(v['usedPercent']>=98 for bucket in before.values() for v in bucket.values()):
            stopped='Account nearly exhausted; counter is not attributed to this test';break
        case=ROOT/condition;cwd=case/'workspace';cwd.mkdir(parents=True)
        save(cwd/'orders.json',records)
        initial_hash=hashlib.sha256((cwd/'orders.json').read_bytes()).hexdigest()
        config=dict(common)
        if condition=='B':config.update(w.settings('token-saver',common['model'],'medium'));config['approval_policy']='never'
        # Independent local server verifies accepted runtime values before inference.
        with Rpc(w.resolve_executable(),HOME,cwd,config=config) as rpc:
            effective=rpc.request('config/read',{'cwd':str(cwd),'includeLayers':False})['config']
            observed={k:value(effective,k) for k in config}
            if observed!=config:raise RuntimeError('Runtime readback differs from requested settings')
        preflight=check_file_access(HOME,cwd,config)
        save(case/'preflight.json',preflight)
        args=[w.resolve_executable(),'exec','--sandbox',config['sandbox_mode'],'--json','--skip-git-repo-check','--cd',str(cwd)]
        for k,v in config.items():args+=['-c',k+'='+json.dumps(v)]
        args+=[TASK if condition=='A' else w.command('token-saver',cwd,prompt=TASK,model=common['model'],effort='medium')[-1]]
        save(case/'runtime.json',observed)
        started=time.monotonic();timeout=False
        with (case/'events.jsonl').open('xb') as out,(case/'stderr.log').open('xb') as err:
            with subprocess.Popen(args,cwd=cwd,env=dict(os.environ,CODEX_HOME=str(HOME)),stdout=out,stderr=err,stdin=subprocess.DEVNULL) as proc:
                try:code=proc.wait(timeout=120)
                except subprocess.TimeoutExpired:timeout=True;proc.terminate();code=proc.wait(timeout=10)
        events=[]
        for line in (case/'events.jsonl').read_text(encoding='utf-8',errors='replace').splitlines():
            try:events.append(json.loads(line))
            except ValueError:pass
        usage=next((e.get('usage') for e in reversed(events) if e.get('type')=='turn.completed'),None)
        answer_text=next((e['item'].get('text','') for e in reversed(events) if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message'),'')
        try:answer=json.loads(answer_text)
        except ValueError:answer=None
        tool_items=[e['item'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type') in ('command_execution','mcp_tool_call')]
        row=dict(condition=condition,usage=usage,total_tokens=usage['input_tokens']+usage['output_tokens'] if usage else None,
                 elapsed_seconds=round(time.monotonic()-started,3),correct=answer==expected,
                 exit_code=code,timeout=timeout,tool_calls=len(tool_items),
                 input_unchanged=hashlib.sha256((cwd/'orders.json').read_bytes()).hexdigest()==initial_hash,
                 thread_id=next((e['thread_id'] for e in events if e.get('type')=='thread.started'),None))
        save(case/'result.json',row);rows.append(row);print(json.dumps(row),flush=True)
        if not row['correct'] or code or timeout or not usage:stopped='Quality/runtime failure; no automatic retry';break
    result=dict(version=w.VERSION,timezone='Europe/Moscow',rows=rows,stopped=stopped,
                test_total_tokens=sum(r['total_tokens'] or 0 for r in rows),requested_model=common['model'],effort='medium')
    if len(rows)==2:
        a,b=rows
        result['reduction_percent']=(1-b['total_tokens']/a['total_tokens'])*100
    save(ROOT/'summary.json',result);print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':main()
