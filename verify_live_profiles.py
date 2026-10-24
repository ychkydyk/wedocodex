"""Verify live settings on a disposable thread, without starting a model turn."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
from skill.scripts import wedocodex as w

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--home',type=Path,required=True);p.add_argument('--thread',required=True);p.add_argument('--workspace',type=Path,required=True)
    opts=p.parse_args()
    stamp=datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d_%H-%M-%S-%f')
    root=Path(__file__).resolve().parent/'qa'/(stamp+'-live-profile-control')
    root.mkdir(parents=True);home=opts.home;cwd=opts.workspace.resolve()
    # Do not pin model/effort on the app-server command line: those overrides
    # would be reapplied by thread/resume and mask the live thread settings.
    config={'agents.enabled':False}
    results=[]
    with w.runtime.Rpc(w.resolve_executable(),home,cwd,config=config) as rpc:
        # Only an explicit, already-completed benchmark thread may be used.
        tid=opts.thread
        rpc.request('thread/resume',{'threadId':tid,'excludeTurns':True})
        rpc.request('thread/settings/update',{'threadId':tid,'model':'gpt-6.1-sol','effort':'medium'})
        before=w.runtime.snapshot(rpc,tid,cwd)
        for mode in ('token-saver','fast-flow','max-quality','guarded','autopilot'):
            plan=w.runtime.live_apply(rpc,home,tid,cwd,mode,w.settings(mode),dry_run=True)
            assert w.runtime.snapshot(rpc,tid,cwd)==before
            applied=w.runtime.live_apply(rpc,home,tid,cwd,mode,w.settings(mode))
            after=w.runtime.snapshot(rpc,tid,cwd)
            assert after['model']==w.settings(mode)['model'] and after['effort']==w.settings(mode)['model_reasoning_effort']
            if applied['live_changes']:
                undone=w.runtime.live_undo(rpc,home,tid,cwd)
                assert undone['verified'] and w.runtime.snapshot(rpc,tid,cwd)==before
            results.append({'mode':mode,'preview_no_change':True,'model_effort_verified':True,'undo_verified':True,'permission_fields_skipped':applied.get('blocked',[])})
        # No turn/start is ever sent by this verifier.
    with (root/'results.json').open('x',encoding='utf-8') as f:json.dump(results,f,indent=2)
    print(json.dumps({'checks':results,'report':str(root/'results.json')},indent=2))

if __name__=='__main__':main()
