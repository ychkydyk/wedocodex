"""Explicit Codex profile previews and idle-thread apply/undo. No inference calls."""
from datetime import datetime,timedelta,timezone
import json,os,queue,re,subprocess,threading,time
from pathlib import Path

class Rpc:
    def __init__(self, executable, home, cwd, proxy=False, config=None):
        args=[executable,'app-server']+(['proxy'] if proxy else ['--listen','stdio://'])
        for key,value in (config or {}).items():args+=['-c',key+'='+json.dumps(value)]
        self.proc=subprocess.Popen(args,cwd=cwd,env=dict(os.environ,CODEX_HOME=str(home)),
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,encoding='utf-8',errors='replace')
        self.messages=queue.Queue();self.sequence=0;self.notifications=[]
        def read():
            for line in self.proc.stdout:
                try:self.messages.put(json.loads(line))
                except ValueError:pass
            self.messages.put(None)
        def discard_errors():
            for _ in self.proc.stderr:pass
        self.readers=[threading.Thread(target=read,daemon=True),threading.Thread(target=discard_errors,daemon=True)]
        for reader in self.readers:reader.start()
        try:
            self.request('initialize',{'clientInfo':{'name':'wedocodex_profiles','version':'0.3.0'},'capabilities':{'experimentalApi':True}})
            self.send({'method':'initialized','params':{}})
        except Exception:
            self.close()
            if proxy:raise RuntimeError('Local Codex App Server proxy is unavailable. Use native /model and /permissions or a compatible CLI session; no settings were changed.') from None
            raise

    def send(self,message):
        self.proc.stdin.write(json.dumps(message)+'\n');self.proc.stdin.flush()

    def request(self,method,params=None):
        self.sequence+=1;identifier=self.sequence
        self.send({'id':identifier,'method':method,'params':params or {}})
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            try:message=self.messages.get(timeout=max(.1,deadline-time.monotonic()))
            except queue.Empty:raise RuntimeError('Codex RPC timed out: '+method) from None
            if message is None:raise RuntimeError('Codex RPC closed: '+method)
            if message.get('id')==identifier and ('result' in message or 'error' in message):
                if 'error' in message:raise RuntimeError('Codex rejected '+method+': '+str(message['error'].get('message','unknown error')))
                return message['result']
            if 'method' in message and 'id' in message:
                self.send({'id':message['id'],'error':{'code':-32601,'message':'No interactive auth or approval in profile control'}})
            else:self.notifications.append(message)
        raise RuntimeError('Codex RPC deadline: '+method)

    def close(self):
        if self.proc.stdin and not self.proc.stdin.closed:self.proc.stdin.close()
        try:self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:self.proc.terminate();self.proc.wait(timeout=3)
        for reader in self.readers:reader.join(timeout=1)
    def __enter__(self):return self
    def __exit__(self,*_):self.close()

    def notification(self,method,thread_id):
        def matches(message):return message.get('method')==method and message.get('params',{}).get('threadId')==thread_id
        for index,message in enumerate(self.notifications):
            if matches(message):return self.notifications.pop(index)['params']
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            try:message=self.messages.get(timeout=max(.1,deadline-time.monotonic()))
            except queue.Empty:raise RuntimeError('No settings readback notification') from None
            if message is None:raise RuntimeError('RPC closed before settings readback')
            if matches(message):return message['params']
            self.notifications.append(message)
        raise RuntimeError('Settings readback timed out')

def value(config,path):
    for key in path.split('.'):
        if not isinstance(config,dict) or key not in config:return None
        config=config[key]
    return config

def preview_config(rpc,settings,cwd):
    current=rpc.request('config/read',{'cwd':str(cwd),'includeLayers':False})['config']
    return [{'key':key,'from':value(current,key),'to':wanted,
             'status':'same' if value(current,key)==wanted else 'change',
             'scope':'next launch / resume'} for key,wanted in settings.items()]

def snapshot(rpc,thread_id,cwd):
    if not re.fullmatch(r'[0-9a-fA-F-]{36}',thread_id):raise ValueError('Explicit thread UUID required')
    thread=rpc.request('thread/read',{'threadId':thread_id,'includeTurns':False})['thread']
    if Path(thread['cwd']).resolve()!=Path(cwd).resolve():raise RuntimeError('Thread workspace mismatch; no settings changed')
    if thread.get('status',{}).get('type')!='idle':raise RuntimeError('Wait for the turn to finish before switching profiles')
    # Reattach to the explicit persisted thread to obtain effective settings.
    # This starts no model turn. A never-used thread has no rollout to resume.
    result=rpc.request('thread/resume',{'threadId':thread_id,'excludeTurns':True})
    if result['thread']['id']!=thread_id:raise RuntimeError('Thread identity mismatch')
    return {'model':result['model'],'effort':result.get('reasoningEffort'),
            'approvalPolicy':result['approvalPolicy'],'sandboxPolicy':result['sandbox'],
            'serviceTier':result.get('serviceTier'),'activePermissionProfile':result.get('activePermissionProfile')}

def live_changes(mode,settings,before):
    target={'model':settings['model'],'effort':settings['model_reasoning_effort']}
    if before['effort'] is None:raise RuntimeError('Select an explicit reasoning effort in Codex first so undo is exact')
    if mode in ('fast-flow','guarded') and not before.get('activePermissionProfile'):
        target['approvalPolicy']=settings['approval_policy']
        target['sandboxPolicy']=({'type':'readOnly','networkAccess':False} if mode=='guarded' else
            {'type':'workspaceWrite','writableRoots':[],'networkAccess':False,'excludeTmpdirEnvVar':False,'excludeSlashTmp':False})
    if mode=='token-saver':target['serviceTier']=None
    return target

def equivalent(key,actual,wanted):
    if key=='serviceTier' and actual in (None,'default') and wanted in (None,'default'):return True
    if key=='sandboxPolicy':return all(actual.get(k)==v for k,v in wanted.items())
    return actual==wanted

def stamp():return datetime.now(timezone(timedelta(hours=3))).strftime('%Y-%m-%d_%H-%M-%S-%f')

def live_apply(rpc,home,thread_id,cwd,mode,settings,dry_run=False):
    before=snapshot(rpc,thread_id,cwd);target=live_changes(mode,settings,before)
    changed={key:val for key,val in target.items() if not equivalent(key,before[key],val)}
    blocked=['approval_policy','sandbox_mode'] if mode in ('fast-flow','guarded') and before.get('activePermissionProfile') else []
    result={'mode':mode,'thread':thread_id,'live_changes':changed,'blocked':blocked,
            'complete_profile_active':False,
            'restart_required':[key for key in settings if key not in ('model','model_reasoning_effort','sandbox_mode','approval_policy','sandbox_workspace_write.network_access')],
            'scope':'Live model/effort. Named permissions profiles are preserved; use native /permissions for blocked rows. Context/output limits need a new launch.',
            'dry_run':dry_run}
    if dry_run or not changed:return result
    history=Path(home)/'wedocodex-live-history';history.mkdir(parents=True,exist_ok=True)
    path=history/(stamp()+'-'+thread_id+'-apply.json')
    record={'thread':thread_id,'cwd':str(Path(cwd).resolve()),'mode':mode,
            'before':{key:before[key] for key in changed},'requested':changed}
    with path.open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2)
    try:
        rpc.request('thread/settings/update',{'threadId':thread_id,**changed})
        after=snapshot(rpc,thread_id,cwd)
        if not all(equivalent(key,after[key],val) for key,val in changed.items()):
            raise RuntimeError('Live readback mismatch')
    except Exception:
        # Restore only if every touched value is still ours or the prior value.
        # External concurrent edits are never blindly overwritten.
        current=snapshot(rpc,thread_id,cwd)
        if all(equivalent(key,current[key],val) or equivalent(key,current[key],before[key]) for key,val in changed.items()):
            rpc.request('thread/settings/update',{'threadId':thread_id,**record['before']})
            restored=snapshot(rpc,thread_id,cwd)
            if all(equivalent(key,restored[key],before[key]) for key in changed):
                with path.with_name(path.stem+'-rolled-back.json').open('x',encoding='utf-8') as stream:json.dump({'verified':True},stream)
        raise
    confirmed=path.with_name(path.stem+'-confirmed.json')
    with confirmed.open('x',encoding='utf-8') as stream:json.dump({'applied':{key:after[key] for key in changed}},stream,indent=2)
    result.update({'verified':True,'undo_record':str(path)})
    return result

def live_undo(rpc,home,thread_id,cwd):
    history=Path(home)/'wedocodex-live-history'
    records=sorted(history.glob('*-'+thread_id+'-apply.json'),reverse=True)
    path=next((p for p in records if p.with_name(p.stem+'-confirmed.json').exists() and not p.with_name(p.stem+'-undone.json').exists()),None)
    if path is None:raise RuntimeError('No confirmed profile activation to undo for this thread')
    record=json.loads(path.read_text(encoding='utf-8'))
    applied=json.loads(path.with_name(path.stem+'-confirmed.json').read_text(encoding='utf-8'))['applied']
    current=snapshot(rpc,thread_id,cwd)
    if not all(equivalent(key,current[key],val) for key,val in applied.items()):
        raise RuntimeError('Live settings changed after activation; preserved, no blind undo')
    rpc.request('thread/settings/update',{'threadId':thread_id,**record['before']})
    after=snapshot(rpc,thread_id,cwd)
    if not all(equivalent(key,after[key],val) for key,val in record['before'].items()):raise RuntimeError('Undo readback mismatch')
    with path.with_name(path.stem+'-undone.json').open('x',encoding='utf-8') as stream:json.dump({'verified':True},stream)
    return {'thread':thread_id,'undone':record['mode'],'verified':True}
