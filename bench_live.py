"""Opt-in bounded smoke test. Requires an existing login; never copies credentials."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from skill.scripts import wedocodex as w
from probe_quota import quota

ROOT = Path(__file__).resolve().parent
TASK = '''Do not use tools, delegate, read files or change anything. Complete only this data task.
Keep rows with state exactly "paid". Normalize client by trimming whitespace and lowercasing.
Sum amount_cents per normalized client, including negative refunds. Return only a JSON object
with totals (keys alphabetically sorted), grand_total_cents and paid_rows.
Records: [{"client":" Alice ","amount_cents":1200,"state":"paid"},
{"client":"BOB","amount_cents":500,"state":"paid"},
{"client":"alice","amount_cents":-200,"state":"paid"},
{"client":"alice","amount_cents":9000,"state":"pending"},
{"client":" bob ","amount_cents":250,"state":"paid"},
{"client":"Carol","amount_cents":0,"state":"paid"},
{"client":" carol ","amount_cents":-50,"state":"paid"},
{"client":"dave","amount_cents":10000,"state":"failed"}].'''
EXPECTED = {'totals': {'alice':1000,'bob':750,'carol':-50},'grand_total_cents':1700,'paid_rows':6}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['token-saver','fast-flow'])
    parser.add_argument('--home',type=Path,required=True)
    parser.add_argument('--baseline',type=Path,required=True)
    opts=parser.parse_args()
    baseline=json.loads(opts.baseline.read_text(encoding='utf-8'))
    before=quota(opts.home, ROOT)
    for bucket,windows in baseline.items():
        for window,initial in windows.items():
            current=before[bucket][window]
            if current['resetsAt']!=initial['resetsAt']:
                raise RuntimeError('Quota window changed; stop and rebaseline explicitly')
            # Integer counters are coarse. Keep one percentage point as headroom.
            if current['usedPercent']>=initial['usedPercent']+3:
                raise RuntimeError('Budget headroom exhausted; no new inference allowed')
    stamp=datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d_%H-%M-%S-%f')
    run=ROOT/'qa'/(stamp+'-live-'+opts.mode); run.mkdir(parents=True)
    recorder=run/'notify_probe.py'
    recorder.write_text('import json,sys\nfrom pathlib import Path\np=json.loads(sys.argv[1])\n'
                        'with Path(__file__).with_name("notification.json").open("x",encoding="utf-8") as f:\n'
                        ' json.dump({"type":p.get("type")},f)\n',encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='wedocodex-live-') as directory:
        workspace=Path(directory)
        args=w.command(opts.mode,workspace,prompt=TASK,executable=w.resolve_executable())
        args[1:1]=['exec','--ignore-user-config','--ephemeral','--json','--skip-git-repo-check']
        args[-1:-1]=['-c','notify='+json.dumps([os.fspath(Path(os.sys.executable)),str(recorder)]),
                    '-c','web_search="disabled"']
        started=time.monotonic(); timed_out=False
        env=dict(os.environ,CODEX_HOME=str(opts.home))
        with (run/'events.jsonl').open('xb') as stdout, (run/'stderr.log').open('xb') as stderr:
            with subprocess.Popen(args,cwd=workspace,env=env,stdout=stdout,stderr=stderr,stdin=subprocess.DEVNULL) as proc:
                try: returncode=proc.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    timed_out=True; proc.terminate(); returncode=proc.wait(timeout=10)
    elapsed=time.monotonic()-started
    events=[]
    for line in (run/'events.jsonl').read_text(encoding='utf-8',errors='replace').splitlines():
        try: events.append(json.loads(line))
        except ValueError: pass
    messages=[event['item'].get('text','') for event in events
              if event.get('type')=='item.completed' and event.get('item',{}).get('type')=='agent_message']
    usage=[event.get('usage') for event in events if event.get('type')=='turn.completed']
    try: answer=json.loads(messages[-1]) if messages else None
    except ValueError: answer=None
    after=quota(opts.home,ROOT)
    report={'created_at':datetime.now(timezone(timedelta(hours=3))).isoformat(),'timezone':'Europe/Moscow',
            'mode':opts.mode,'requested_model':w.PROFILES[opts.mode][0],
            'requested_effort':w.PROFILES[opts.mode][1],'elapsed_seconds':round(elapsed,3),
            'exit_code':returncode,'timeout':timed_out,'correct':answer==EXPECTED,
            'usage':usage,'quota_before':before,'quota_after':after,
            'notification_hook_observed':(run/'notification.json').exists(),
            'notification_display_verified':False,
            'errors':[e.get('message') or e.get('error') for e in events if e.get('type') in ('error','turn.failed')]}
    with (run/'result.json').open('x',encoding='utf-8') as f: json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2)); print(run)
    if not report['correct']: raise SystemExit(1)

if __name__=='__main__': main()
