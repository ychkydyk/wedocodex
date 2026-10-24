"""Explicit A/B of launcher behavior, fixed model/effort. No inference without --run."""
import argparse
from datetime import datetime,timedelta,timezone
import hashlib,json,os
from pathlib import Path
import statistics
import subprocess,tempfile,time
from bench_live import TASK,EXPECTED
from probe_quota import quota
from skill.scripts import wedocodex as w

ROOT=Path(__file__).resolve().parent
MODEL='gpt-6.1-sol'
EFFORT='medium'
ORDER=['A','B','B','A','A','B']

def budget_guard(current,baseline,ceiling):
    for bucket,windows in baseline.items():
        for window,initial in windows.items():
            observed=current[bucket][window]
            if observed['resetsAt']!=initial['resetsAt']:
                raise RuntimeError('Quota window changed; do not silently rebaseline')
            if observed['usedPercent']>=ceiling-1:
                raise RuntimeError('One-point reserve reached; no further inference')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--home',type=Path)
    parser.add_argument('--baseline',type=Path)
    parser.add_argument('--ceiling',type=int,default=19)
    opts=parser.parse_args()
    plan={'model':MODEL,'effort':EFFORT,'order':ORDER,'task_sha256':hashlib.sha256(TASK.encode()).hexdigest(),
          'A':'same Codex runtime, task only, no WEDOCODEX mode instruction',
          'B':'same runtime, Token Saver launcher behavior plus identical task',
          'scope':'behavior prompt effect on one short data task; not a general skill benchmark',
          'ceiling_used_percent':opts.ceiling,'reserve_percentage_points':1}
    if not opts.run: print(json.dumps(plan,indent=2));return
    if not opts.home or not opts.baseline:parser.error('--home and --baseline are required for live runs')
    baseline=json.loads(opts.baseline.read_text(encoding='utf-8'))
    budget_guard(quota(opts.home,ROOT),baseline,opts.ceiling)
    stamp=datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d_%H-%M-%S-%f')
    folder=ROOT/'qa'/(stamp+'-same-model-ab');folder.mkdir(parents=True)
    with (folder/'plan.json').open('x',encoding='utf-8') as f:json.dump(plan,f,indent=2)
    results=[];stop_reason=None
    with tempfile.TemporaryDirectory(prefix='wedocodex-ab-') as directory:
        workspace=Path(directory)
        for index,condition in enumerate(ORDER,1):
            try:
                before=quota(opts.home,ROOT);budget_guard(before,baseline,opts.ceiling)
            except Exception as exc:
                stop_reason=str(exc);break
            run=folder/(f'{index:02d}-'+condition);run.mkdir()
            args=w.command('token-saver',workspace,prompt=TASK,executable=w.resolve_executable(),model=MODEL,effort=EFFORT)
            args[1:1]=['exec','--ignore-user-config','--ephemeral','--json','--skip-git-repo-check']
            args[-1:-1]=['-c','web_search="disabled"','-c','approval_policy="never"','-c','notify=[]']
            if condition=='A':args[-1]=TASK
            # Prompt and runtime fingerprints are recorded separately.
            prompt_hash=hashlib.sha256(args[-1].encode()).hexdigest()
            runtime_hash=hashlib.sha256(json.dumps(args[:-1]).encode()).hexdigest()
            start=time.monotonic();timeout=False
            with (run/'events.jsonl').open('xb') as out,(run/'stderr.log').open('xb') as err:
                with subprocess.Popen(args,cwd=workspace,env=dict(os.environ,CODEX_HOME=str(opts.home)),
                                      stdin=subprocess.DEVNULL,stdout=out,stderr=err) as proc:
                    try:code=proc.wait(timeout=120)
                    except subprocess.TimeoutExpired:
                        timeout=True;proc.terminate();code=proc.wait(timeout=10)
            elapsed=time.monotonic()-start
            events=[]
            for line in (run/'events.jsonl').read_text(encoding='utf-8',errors='replace').splitlines():
                try:events.append(json.loads(line))
                except ValueError:pass
            completed=[e for e in events if e.get('type')=='turn.completed']
            messages=[e['item'].get('text','') for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message']
            try:answer=json.loads(messages[-1]) if messages else None
            except ValueError:answer=None
            usage=completed[-1].get('usage') if completed else None
            after=None
            try:after=quota(opts.home,ROOT)
            except Exception as exc:stop_reason='Post-run quota unavailable: '+str(exc)
            row={'index':index,'condition':condition,'elapsed_seconds':round(elapsed,3),
                 'requested_model':MODEL,'requested_effort':EFFORT,'runtime_sha256':runtime_hash,
                 'prompt_sha256':prompt_hash,'usage':usage,'correct':answer==EXPECTED,
                 'exit_code':code,'timeout':timeout,'quota_before':before,'quota_after':after,
                 'tool_events':[e.get('item',{}).get('type') for e in events if e.get('type')=='item.started' and e.get('item',{}).get('type') not in ('agent_message','reasoning')]}
            if usage:row['total_tokens']=usage['input_tokens']+usage['output_tokens']
            with (run/'result.json').open('x',encoding='utf-8') as f:json.dump(row,f,indent=2)
            results.append(row)
            print(json.dumps({k:row.get(k) for k in ('index','condition','correct','total_tokens','elapsed_seconds','usage')}),flush=True)
            if not row['correct'] or code or timeout or row['tool_events']:
                stop_reason='Unexpected model behavior; no retries';break
            if stop_reason:break
    grouped={}
    for condition in ('A','B'):
        rows=[x for x in results if x['condition']==condition and x.get('usage')]
        if rows:
            grouped[condition]={'n':len(rows),'correct':sum(x['correct'] for x in rows),
                'mean_total_tokens':statistics.mean(x['total_tokens'] for x in rows),
                'median_seconds':statistics.median(x['elapsed_seconds'] for x in rows),
                'mean_input_tokens':statistics.mean(x['usage']['input_tokens'] for x in rows),
                'mean_cached_input_tokens':statistics.mean(x['usage']['cached_input_tokens'] for x in rows),
                'mean_output_tokens':statistics.mean(x['usage']['output_tokens'] for x in rows)}
    report={'created_at':datetime.now(timezone(timedelta(hours=3))).isoformat(),'timezone':'Europe/Moscow',
            'plan':plan,'results':results,'summary':grouped,'stop_reason':stop_reason,
            'runtime_identical':len({x['runtime_sha256'] for x in results})==1,
            'limitations':['one short deterministic data task','three samples maximum per condition',
                           'cold/warm cache and startup/network variance remain','requested model ID, independent served ID unavailable']}
    if set(grouped)=={'A','B'}:
        report['total_token_reduction_percent']=(1-grouped['B']['mean_total_tokens']/grouped['A']['mean_total_tokens'])*100
        report['median_time_reduction_percent']=(1-grouped['B']['median_seconds']/grouped['A']['median_seconds'])*100
    with (folder/'summary.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps({'folder':str(folder),'summary':grouped,'stop_reason':stop_reason,'runtime_identical':report['runtime_identical'],
                      'total_token_reduction_percent':report.get('total_token_reduction_percent'),
                      'median_time_reduction_percent':report.get('median_time_reduction_percent')},indent=2),flush=True)

if __name__=='__main__':main()
