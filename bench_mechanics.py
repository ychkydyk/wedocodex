"""Opt-in fixed-model, paired-task test of real WEDOCODEX runtime settings."""
from datetime import datetime,timedelta,timezone
import argparse,hashlib,json,os,statistics,subprocess,time
from pathlib import Path
from bench_live import TASK,EXPECTED
from bench_ab import budget_guard
from probe_quota import quota
from skill.scripts import wedocodex as w

ROOT=Path(__file__).resolve().parent
MODEL='gpt-6.1-sol';EFFORT='medium'
TASKS=[('aggregate',TASK,EXPECTED),
 ('review','''Do not use tools or change files. Review this numbered Python code:
1 def sum_even(items):
2     total = 0
3     for value in items:
4         if value % 2 == 0:
5             total += value
6         return total
Return only JSON with bug_line (integer), fixed_result for input [1,2,4,6], and fix chosen from ["dedent return", "change modulo", "start at 1"].''',
  {'bug_line':6,'fixed_result':12,'fix':'dedent return'}),
 ('dependencies','''Do not use tools or change files. Nodes: fetch, lint, parse, validate, index, render, publish.
Dependencies: parse requires fetch; validate requires parse; index and render each require validate; publish requires both index and render; lint is independent.
Return only JSON with order (the lexicographically smallest valid topological order) and critical_path_nodes (number of nodes in the longest dependency path).''',
  {'order':['fetch','lint','parse','validate','index','render','publish'],'critical_path_nodes':5})]

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',action='store_true');p.add_argument('--home',type=Path)
    p.add_argument('--baseline',type=Path);p.add_argument('--ceiling',type=int,default=30)
    p.add_argument('--preserve-agent-catalog',action='store_true');opts=p.parse_args()
    if not opts.run:print('Plan: 3 paired tasks, A/B then B/A then A/B; fixed Sol 6.1 / medium. Add --run explicitly.');return
    if not opts.home or not opts.baseline:p.error('home/baseline required')
    baseline=json.loads(opts.baseline.read_text(encoding='utf-8'));budget_guard(quota(opts.home,ROOT),baseline,opts.ceiling)
    stamp=datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d_%H-%M-%S-%f')
    root=ROOT/'qa'/(stamp+'-native-controls-ab');cwd=root/'workspace';cwd.mkdir(parents=True)
    rows=[];stopped=None
    common={'model':MODEL,'model_reasoning_effort':EFFORT,'sandbox_mode':'workspace-write','approval_policy':'never',
            'sandbox_workspace_write.network_access':False,'tui.auto_recap':False,'web_search':'disabled','notify':[]}
    for task_index,(task_name,task,expected) in enumerate(TASKS):
        for condition in (['A','B'] if task_index%2==0 else ['B','A']):
            before=quota(opts.home,ROOT)
            try:budget_guard(before,baseline,opts.ceiling)
            except Exception as exc:stopped=str(exc);break
            case=root/(str(len(rows)+1)+'-'+task_name+'-'+condition);case.mkdir()
            config=dict(common)
            if condition=='B':
                config.update(w.settings('token-saver',MODEL,EFFORT));config['approval_policy']='never'
                if opts.preserve_agent_catalog:config.pop('agents.enabled',None)
            args=[w.resolve_executable(),'exec','--ignore-user-config','--json','--skip-git-repo-check','--cd',str(cwd)]
            for key,value in config.items():args+=['-c',key+'='+json.dumps(value)]
            prompt=task if condition=='A' else w.command('token-saver',cwd,prompt=task,model=MODEL,effort=EFFORT)[-1]
            args+=[prompt];start=time.monotonic();timed_out=False
            with (case/'events.jsonl').open('xb') as out,(case/'stderr.log').open('xb') as err:
                with subprocess.Popen(args,cwd=cwd,env=dict(os.environ,CODEX_HOME=str(opts.home)),stdin=subprocess.DEVNULL,stdout=out,stderr=err) as proc:
                    try:code=proc.wait(timeout=120)
                    except subprocess.TimeoutExpired:timed_out=True;proc.terminate();code=proc.wait(timeout=10)
            elapsed=round(time.monotonic()-start,3);events=[]
            for line in (case/'events.jsonl').read_text(encoding='utf-8',errors='replace').splitlines():
                try:events.append(json.loads(line))
                except ValueError:pass
            usage=next((e.get('usage') for e in reversed(events) if e.get('type')=='turn.completed'),None)
            message=next((e['item'].get('text','') for e in reversed(events) if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message'),'')
            try:answer=json.loads(message)
            except ValueError:answer=None
            thread=next((e['thread_id'] for e in events if e.get('type')=='thread.started'),None)
            row={'task':task_name,'condition':condition,'requested_model':MODEL,'effort':EFFORT,'config':config,
                 'task_sha256':hashlib.sha256(task.encode()).hexdigest(),'usage':usage,'correct':answer==expected,
                 'elapsed_seconds':elapsed,'exit_code':code,'timeout':timed_out,'thread_id':thread,
                 'quota_before':before,'quota_after':quota(opts.home,ROOT),
                 'total_tokens':usage['input_tokens']+usage['output_tokens'] if usage else None}
            with (case/'result.json').open('x',encoding='utf-8') as f:json.dump(row,f,indent=2)
            rows.append(row);print(json.dumps({k:row[k] for k in ('task','condition','correct','usage','elapsed_seconds')}),flush=True)
            if not row['correct'] or code or timed_out:stopped='Quality/runtime failure; no automatic retry';break
        if stopped:break
    summary={}
    for condition in ('A','B'):
        part=[r for r in rows if r['condition']==condition and r['usage']]
        if part:summary[condition]={'n':len(part),'correct':sum(r['correct'] for r in part),'mean_total_tokens':statistics.mean(r['total_tokens'] for r in part),'median_seconds':statistics.median(r['elapsed_seconds'] for r in part)}
    report={'version':w.VERSION,'timezone':'Europe/Moscow','rows':rows,'summary':summary,'stopped':stopped,'preserve_agent_catalog':opts.preserve_agent_catalog,
            'scope':'native settings + launcher behavior on 3 small paired tasks; no tool-output truncation workload',
            'workspace':str(cwd),'model':MODEL,'effort':EFFORT}
    if set(summary)=={'A','B'}:report['token_reduction_percent']=(1-summary['B']['mean_total_tokens']/summary['A']['mean_total_tokens'])*100
    with (root/'summary.json').open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps({'folder':str(root),'summary':summary,'stopped':stopped,'token_reduction_percent':report.get('token_reduction_percent')},indent=2),flush=True)

if __name__=='__main__':main()
