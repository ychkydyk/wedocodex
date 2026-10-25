"""Opt-in: three additional paired file tasks, same model/effort, no retries."""
import argparse, hashlib, json, os, random, subprocess, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from bench_installed import w, HOME
from preflight_tools import check
from probe_quota import quota

ROOT=Path(__file__).resolve().parent
COMMON={'model':'gpt-6.1-sol','model_reasoning_effort':'medium','sandbox_mode':'workspace-write',
        'approval_policy':'never','sandbox_workspace_write.network_access':False,
        'tui.auto_recap':False,'web_search':'disabled','notify':[]}
POLICY=('Use one local tool call if possible. Do not edit files, delegate, browse, or read unrelated files. '
        'If a tool is denied, stop immediately without retrying. Return only the requested JSON. ')
CASES=[
 ('assets','assets.json',json.dumps({'required':['giant.png','water.exr','crowd.exr','dust.exr','font.woff2','giant.png'],
    'available':[{'path':'giant.png','bytes':2048},{'path':'water.exr','bytes':8192},
                 {'path':'crowd.exr','bytes':4096},{'path':'dust.exr','bytes':1024},{'path':'unused.png','bytes':512}]},indent=2),
  'Read assets.json. Return missing (sorted unique required paths absent from available), '
  'duplicate_required (sorted paths repeated in required), unused (sorted available paths not required), '
  'and required_available_bytes (sum bytes once per available required path).',
  {'missing':['font.woff2'],'duplicate_required':['giant.png'],'unused':['unused.png'],'required_available_bytes':15360}),
 ('timeline','timeline.json',json.dumps({'fps':30,'scenes':[{'id':'notice','hold_s':20,'transition_s':4},
    {'id':'approach','hold_s':24,'transition_s':6},{'id':'wave','hold_s':32,'transition_s':8},
    {'id':'settle','hold_s':20,'transition_s':6}],'loop':True},indent=2),
  'Read timeline.json. Each scene consists of hold_s then transition_s, sequentially without overlap. '
  'Include the last transition back to the first scene. Return total_seconds, total_frames, '
  'scene_start_frames (map of scene id to zero-based start), and scene_at_frame_1710 '
  '(a scene owns both its hold and following transition; start included, end excluded).',
  {'total_seconds':120,'total_frames':3600,'scene_start_frames':{'notice':0,'approach':720,'wave':1620,'settle':2820},'scene_at_frame_1710':'wave'}),
 ('review','smooth.py','def smooth(current, target, dt, rate):\n    alpha = min(1.0, max(0.0, dt * rate))\n    return current + (target - current) * dt\n',
  'Read smooth.py as text. The function intends to use its clamped alpha when interpolating. '
  'Do not modify or import the module. Return bug_line (1-based), replacement_line (strip indentation), '
  'current_result and corrected_result for current=0, target=1, dt=0.25, rate=2, '
  'and corrected_large_dt_result for current=0, target=1, dt=10, rate=2.',
  {'bug_line':3,'replacement_line':'return current + (target - current) * alpha',
   'current_result':0.25,'corrected_result':0.5,'corrected_large_dt_result':1.0})]

def save(path,data):
    with path.open('x',encoding='utf-8') as f:json.dump(data,f,indent=2)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='store_true');parser.add_argument('--all-four',action='store_true');parser.add_argument('--combined-smoke',action='store_true');opts=parser.parse_args()
    if opts.all_four and opts.combined_smoke:parser.error('Choose the four-pair suite or the combined smoke test')
    selected=list(CASES)
    if opts.all_four:
        rng=random.Random(241026)
        records=[dict(client=rng.choice([' Alice ','BOB','alice',' bob ','Carol']),amount_cents=rng.randint(-500,5000),state=rng.choice(['paid','paid','pending','failed'])) for _ in range(80)]
        totals={};count=0
        for row in records:
            if row['state']=='paid':
                key=row['client'].strip().lower();totals[key]=totals.get(key,0)+row['amount_cents'];count+=1
        selected.insert(0,('aggregate','orders.json',json.dumps(records,indent=2),
          'Read orders.json. Keep state exactly paid, trim and lowercase client, sum amount_cents including refunds. Return totals (sorted client keys), grand_total_cents and paid_rows.',
          dict(totals=dict(sorted(totals.items())),grand_total_cents=sum(totals.values()),paid_rows=count)))
    if opts.combined_smoke:selected=selected[:1]
    if not opts.run:print('Plan: '+('one Saver+Autopilot smoke task' if opts.combined_smoke else str(len(selected))+' paired file tasks')+', Sol 6.1 medium; add --run to spend tokens.');return
    stamp=datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d_%H-%M-%S-%f')
    folder=ROOT/'qa'/(stamp+('-saver-autopilot-smoke' if opts.combined_smoke else '-three-more-file-pairs'));folder.mkdir(parents=True)
    save(folder/'plan.json',{'tasks':[c[0] for c in selected],'requested_model':COMMON['model'],
      'effort':'medium','order':['B'] if opts.combined_smoke else ['AB','BA','AB','BA'] if opts.all_four else ['BA','AB','BA'],'sessions':1 if opts.combined_smoke else 2*len(selected),'timezone':'Europe/Moscow',
      'scope':'Small reproducible fixtures for asset validation, scenario timing and Python review; not a full production-project benchmark.',
      'token_budget_note':'Per-session telemetry; fixed requested session count. No account percentage attributed to the test.'})
    rows=[];stopped=None
    for n,(name,filename,content,task,expected) in enumerate(selected):
        for condition in (['B'] if opts.combined_smoke else ['A','B'] if (n%2==0)==opts.all_four else ['B','A']):
            available=quota(HOME,folder)
            if any(v['usedPercent']>=98 for bucket in available.values() for v in bucket.values()):
                stopped='Account safety reserve reached';break
            case=folder/(name+'-'+condition);cwd=case/'workspace';cwd.mkdir(parents=True)
            fixture=cwd/filename
            with fixture.open('x',encoding='utf-8',newline='\n') as f:f.write(content)
            digest=hashlib.sha256(fixture.read_bytes()).hexdigest()
            config=dict(COMMON)
            if condition=='B':config.update(w.settings('token-saver',COMMON['model'],'medium',autopilot=opts.combined_smoke));config['approval_policy']='never'
            try:preflight=check(HOME,cwd,config)
            except Exception as exc:stopped='Preflight failed before inference: '+str(exc);break
            save(case/'preflight.json',preflight)
            prompt=POLICY+task
            if opts.combined_smoke:
                prompt=POLICY.replace('Do not edit files,','Do not modify the input file;')+task+' After calculating, create checkpoint.json with status=complete, task=assets, next=done. This is the only file you may create. Then return only the requested result JSON.'
            if condition=='B':prompt=w.command('token-saver',cwd,prompt=prompt,model=COMMON['model'],effort='medium',autopilot=opts.combined_smoke)[-1]
            args=[w.resolve_executable(),'exec','--sandbox','workspace-write','--json','--skip-git-repo-check','--cd',str(cwd)]
            for key,val in config.items():args+=['-c',key+'='+json.dumps(val)]
            args+=[prompt];start=time.monotonic();timeout=False
            with (case/'events.jsonl').open('xb') as out,(case/'stderr.log').open('xb') as err:
                with subprocess.Popen(args,cwd=cwd,env=dict(os.environ,CODEX_HOME=str(HOME)),stdin=subprocess.DEVNULL,stdout=out,stderr=err) as process:
                    try:code=process.wait(timeout=120)
                    except subprocess.TimeoutExpired:timeout=True;process.terminate();code=process.wait(timeout=10)
            elapsed=round(time.monotonic()-start,3);events=[]
            for line in (case/'events.jsonl').read_text(encoding='utf-8',errors='replace').splitlines():
                try:events.append(json.loads(line))
                except ValueError:pass
            usage=next((e.get('usage') for e in reversed(events) if e.get('type')=='turn.completed'),None)
            answer_text=next((e['item'].get('text','') for e in reversed(events) if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='agent_message'),'')
            try:answer=json.loads(answer_text)
            except ValueError:answer=None
            row={'task':name,'condition':condition,'usage':usage,'correct':answer==expected,
                 'elapsed_seconds':elapsed,'exit_code':code,'timeout':timeout,
                 'fixture_sha256':digest,'input_unchanged':hashlib.sha256(fixture.read_bytes()).hexdigest()==digest,
                 'thread_id':next((e['thread_id'] for e in events if e.get('type')=='thread.started'),None),
                 'tool_calls':sum(e.get('type')=='item.completed' and e.get('item',{}).get('type') in ['command_execution','mcp_tool_call'] for e in events),
                 'total_tokens':usage['input_tokens']+usage['output_tokens'] if usage else None}
            if opts.combined_smoke:
                try:checkpoint=json.loads((cwd/'checkpoint.json').read_text(encoding='utf-8-sig'))
                except (OSError,ValueError):checkpoint={}
                row['checkpoint_verified']=all(checkpoint.get(k)==v for k,v in {'status':'complete','task':'assets','next':'done'}.items())
                row['correct']=row['correct'] and row['checkpoint_verified']
            save(case/'result.json',row);rows.append(row);print(json.dumps(row),flush=True)
            if not row['correct'] or code or timeout or not usage:
                stopped='Quality/runtime failure; no automatic retry';break
        if stopped:break
    save(folder/'summary.json',{'rows':rows,'stopped':stopped,'requested_model':COMMON['model'],'effort':'medium',
                               'test_total_tokens':sum(r['total_tokens'] or 0 for r in rows)})
    print(json.dumps({'folder':str(folder),'completed':len(rows),'stopped':stopped}),flush=True)

if __name__=='__main__':main()
