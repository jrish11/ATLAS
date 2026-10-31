import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

class WorkflowLocking(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.env=dict(os.environ, ATTICUS_DIR=str(self.root), PYTHONPYCACHEPREFIX='/tmp/atticus-test-cache', ATTICUS_POSTHOG_KEY='')
        self.env.pop('ATTICUS_ASK',None);self.env.pop('ATTICUS_AGENT',None)
    def children(self, code, args):
        children=[subprocess.Popen([sys.executable,'-c',code,arg],env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for arg in args]
        for p in children:
            out,err=p.communicate(timeout=15);self.assertEqual(p.returncode,0,err)
    def test_concurrent_shortcut_additions_and_demotions_are_serialized(self):
        code="import atticus,sys,time; atticus._save_shortcut(sys.argv[1], 'open -a Fixture')"
        names=['fixture '+str(i) for i in range(8)];self.children(code,names)
        rows=json.loads((self.root/'skills.json').read_text());self.assertEqual(set(rows),set(names))
        code="import atticus,sys; atticus.workflow_failed(sys.argv[1])"
        self.children(code,names)
        rows=json.loads((self.root/'skills.json').read_text())
        self.assertTrue(all(not row['evidence']['confirmed'] and row['evidence']['corrections'] for row in rows.values()))
    def test_symlinked_stores_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as external:
            target=Path(external)/'target.json';target.write_text('{}')
            (self.root/'skills.json').symlink_to(target)
            code="import atticus;\ntry: atticus._save_shortcut('new','open x')\nexcept ValueError: pass\nelse: raise AssertionError('accepted symlink')"
            self.children(code,['unused'])
            self.assertEqual(target.read_text(),'{}')
            self.assertTrue((self.root/'skills.json').is_symlink())
    def test_unlearn_preflights_both_stores_before_mutating(self):
        import time
        original={'x':{'reply':'Done','cmds':['open x'],'mine':True,'at':time.strftime('%Y-%m-%d')}}
        (self.root/'skills.json').write_text(json.dumps(original))
        (self.root/'workflows.json').write_text(json.dumps({'x':{'future':'preserve'}}))
        code="import atticus;\ntry: atticus.unlearn('x')\nexcept ValueError: pass\nelse: raise AssertionError('accepted unknown workflow')"
        self.children(code,['unused'])
        self.assertEqual(json.loads((self.root/'skills.json').read_text()),original)
    def test_unknown_shortcut_and_workflow_fields_are_not_overwritten(self):
        (self.root/'skills.json').write_text(json.dumps({'x':{'reply':'Done','cmds':['open x'],'future':'preserve'}}))
        (self.root/'workflows.json').write_text(json.dumps({'x':{'future':'preserve'}}))
        code="import atticus;\ntry: atticus._save_shortcut('new','open x')\nexcept ValueError: pass\nelse: raise AssertionError('accepted unknown shortcut')\ntry: atticus.workflows('new','steps')\nexcept ValueError: pass\nelse: raise AssertionError('accepted unknown workflow')"
        self.children(code,['unused'])
        self.assertEqual(json.loads((self.root/'skills.json').read_text())['x']['future'],'preserve')
        self.assertEqual(json.loads((self.root/'workflows.json').read_text())['x']['future'],'preserve')

if __name__=='__main__': unittest.main()
