import copy,json,tempfile,unittest
from pathlib import Path
from skill.scripts import wedocodex as w

ID='01234567-89ab-cdef-0123-456789abcdef'

class FakeRpc:
    def __init__(self,cwd):
        self.cwd=str(cwd);self.calls=[];self.busy=False;self.fail_once=False
        self.state={'model':'gpt-6.1-sol','effort':'medium','approvalPolicy':'on-request',
                    'sandboxPolicy':{'type':'workspaceWrite','writableRoots':[],'networkAccess':False,'excludeTmpdirEnvVar':False,'excludeSlashTmp':False},
                    'serviceTier':'default','activePermissionProfile':None}
    def request(self,method,params):
        self.calls.append(method)
        if method=='thread/read':return {'thread':{'id':ID,'cwd':self.cwd,'status':{'type':'inProgress' if self.busy else 'idle'}}}
        if method=='thread/resume':return {'thread':{'id':ID},'model':self.state['model'],'reasoningEffort':self.state['effort'],
            'approvalPolicy':self.state['approvalPolicy'],'sandbox':copy.deepcopy(self.state['sandboxPolicy']),
            'serviceTier':self.state['serviceTier'],'activePermissionProfile':self.state['activePermissionProfile']}
        if method=='thread/settings/update':
            for k,v in params.items():
                if k!='threadId':self.state[k]=copy.deepcopy(v)
                if self.fail_once and k=='model':self.fail_once=False;raise RuntimeError('partial failure')
            return {}
        if method=='config/read':return {'config':{'model':'existing','secrets':'never expose'}}
        raise AssertionError(method)

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.rpc=FakeRpc(self.root)

    def test_preview_exposes_only_requested_keys(self):
        rows=w.runtime.preview_config(self.rpc,{'model':'new','skills.max_context_tokens':2000},self.root)
        self.assertEqual(len(rows),2);self.assertNotIn('secrets',json.dumps(rows))

    def test_apply_undo_all_profiles_and_preview(self):
        for mode in w.PROFILES:
            with self.subTest(mode=mode):
                before=copy.deepcopy(self.rpc.state)
                w.runtime.live_apply(self.rpc,self.root,ID,self.root,mode,w.settings(mode),True)
                self.assertEqual(self.rpc.state,before)
                result=w.runtime.live_apply(self.rpc,self.root,ID,self.root,mode,w.settings(mode))
                self.assertFalse(result['complete_profile_active'])
                if result['live_changes']:
                    self.assertTrue(result['verified']);w.runtime.live_undo(self.rpc,self.root,ID,self.root)
                self.assertEqual(self.rpc.state,before)
        self.assertNotIn('turn/start',self.rpc.calls)

    def test_named_permissions_are_preserved_and_marked_blocked(self):
        self.rpc.state['activePermissionProfile']='managed'
        before=copy.deepcopy(self.rpc.state['sandboxPolicy'])
        result=w.runtime.live_apply(self.rpc,self.root,ID,self.root,'guarded',w.settings('guarded'))
        self.assertIn('sandbox_mode',result['blocked']);self.assertEqual(before,self.rpc.state['sandboxPolicy'])

    def test_undo_preserves_user_changes(self):
        w.runtime.live_apply(self.rpc,self.root,ID,self.root,'token-saver',w.settings('token-saver'))
        self.rpc.state['effort']='high'
        with self.assertRaises(RuntimeError):w.runtime.live_undo(self.rpc,self.root,ID,self.root)
        self.assertEqual(self.rpc.state['effort'],'high')

    def test_wrong_workspace_and_running_thread_refused(self):
        with self.assertRaises(RuntimeError):w.runtime.snapshot(self.rpc,ID,self.root/'different')
        self.rpc.busy=True
        with self.assertRaises(RuntimeError):w.runtime.snapshot(self.rpc,ID,self.root)
        self.assertNotIn('thread/settings/update',self.rpc.calls)

    def test_partial_apply_rolls_back(self):
        before=copy.deepcopy(self.rpc.state);self.rpc.fail_once=True
        with self.assertRaises(RuntimeError):w.runtime.live_apply(self.rpc,self.root,ID,self.root,'token-saver',w.settings('token-saver'))
        self.assertEqual(self.rpc.state,before)

    def test_default_service_tier_normalization(self):
        self.assertTrue(w.runtime.equivalent('serviceTier','default',None))
        self.assertFalse(w.runtime.equivalent('serviceTier','priority',None))

    def test_saver_preserves_agent_catalog(self):
        self.assertNotIn('agents.enabled',w.settings('token-saver'))
        self.assertEqual(w.settings('token-saver')['skills.max_context_tokens'],2000)
        self.assertEqual(w.settings('token-saver')['tool_output_token_limit'],6000)

if __name__=='__main__':unittest.main()
