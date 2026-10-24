"""Read subscription counters without creating a thread or making inference requests."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from skill.scripts import wedocodex as w

def quota(home, cwd):
    env = dict(os.environ, CODEX_HOME=str(home))
    args = [w.resolve_executable(), 'app-server', '--listen', 'stdio://']
    with subprocess.Popen(args, cwd=cwd, env=env, stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, encoding='utf-8', errors='replace') as proc:
        messages = queue.Queue()
        def drain(stream, output):
            for line in stream:
                if output:
                    try: messages.put(json.loads(line))
                    except ValueError: pass
            if output: messages.put(None)
        threads = [threading.Thread(target=drain, args=(proc.stdout, True), daemon=True),
                   threading.Thread(target=drain, args=(proc.stderr, False), daemon=True)]
        for thread in threads: thread.start()
        def send(data):
            proc.stdin.write(json.dumps(data) + '\n'); proc.stdin.flush()
        def response(identifier):
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                item = messages.get(timeout=max(.1, deadline-time.monotonic()))
                if item is None: raise RuntimeError('App server exited before quota response')
                if item.get('id') == identifier:
                    if 'error' in item: raise RuntimeError(json.dumps(item['error']))
                    return item['result']
            raise RuntimeError('Quota request timed out')
        try:
            send({'id':1,'method':'initialize','params':{'clientInfo':{'name':'wedocodex_budget_test','version':w.VERSION}}})
            response(1); send({'method':'initialized','params':{}})
            send({'id':2,'method':'account/rateLimits/read','params':{}})
            result = response(2)
            # Never persist account IDs, credentials, credit identifiers or raw config.
            buckets = result.get('rateLimitsByLimitId') or {'default':result.get('rateLimits')}
            safe = {}
            for key, bucket in buckets.items():
                if not bucket: continue
                safe[key] = {window: {field: bucket[window].get(field) for field in
                                     ('usedPercent','windowDurationMins','resetsAt')}
                             for window in ('primary','secondary') if bucket.get(window)}
            if not safe or not any(safe.values()): raise RuntimeError('No measurable quota counters returned')
            return safe
        finally:
            proc.stdin.close()
            try: proc.wait(timeout=3)
            except subprocess.TimeoutExpired: proc.terminate(); proc.wait(timeout=3)
            for thread in threads: thread.join(timeout=2)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--home',type=Path,required=True)
    opts=parser.parse_args()
    try:
        data=quota(opts.home, Path(__file__).resolve().parent)
        print(json.dumps(data,indent=2))
        print(w.save_report('quota-before',data))
    except Exception as exc:
        print('Quota unavailable: '+str(exc)); raise SystemExit(1)
