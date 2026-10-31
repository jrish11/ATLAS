import json, os, subprocess, sys, tempfile, time, unittest
from pathlib import Path
import memory_inspector
import memory_workflows
import atticus

APP=Path(__file__).resolve().parents[1]/'atticus.py'
class WorkflowRecovery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.skill={'cmds':[atticus.SHOW+' Fixture'],'reply':'Done.','mine':True,'at':time.strftime('%Y-%m-%d'),'evidence':{'version':1,'source':'owner','confirmed':True,'successes':2,'confidence':0.9,'updated':1,'corrections':[]}}
        (self.root/'skills.json').write_text(json.dumps({'fixture':self.skill}))
        (self.root/'workflows.json').write_text(json.dumps({'plan':'old procedure'}))
    def row(self,kind):return next(r for r in memory_inspector.inspect(str(self.root)) if r.get('identifier','').startswith(kind+':'))
    def invoke(self, **request):
        env=dict(os.environ,ATTICUS_DIR=str(self.root),PYTHONPYCACHEPREFIX='/tmp/atticus-test-cache',ATTICUS_POSTHOG_KEY='');env.pop('ATTICUS_ASK',None);env.pop('ATTICUS_AGENT',None)
        p=subprocess.run([sys.executable,str(APP),'--memory-transaction'],input=json.dumps({'category':'workflows',**request}),text=True,capture_output=True,env=env,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr);return json.loads(p.stdout)
    def test_procedure_revision_edit_delete_restore_and_conflict(self):
        row=self.row('workflows');base={'identifier':row['identifier'],'revision':row['revision']}
        self.assertIn('error',self.invoke(action='edit',value='new procedure',confirmed=False,**base))
        result=self.invoke(action='edit',value='new procedure',confirmed=True,**base);self.assertEqual(result.get('status'),'saved',result)
        self.assertIn('error',self.invoke(action='delete',confirmed=True,**base))
        path=self.root/'workflows.json';after=path.read_bytes();path.write_text(json.dumps({'plan':'concurrent'}))
        self.assertIn('error',self.invoke(action='restore',backup_id=result['backup'],confirmed=True));path.write_bytes(after)
        self.assertEqual(self.invoke(action='restore',backup_id=result['backup'],confirmed=True).get('status'),'restored')
        row=self.row('workflows');result=self.invoke(action='delete',identifier=row['identifier'],revision=row['revision'],confirmed=True)
        self.assertEqual(result.get('status'),'deleted');self.assertEqual(self.invoke(action='restore',backup_id=result['backup'],confirmed=True).get('status'),'restored')
        self.assertEqual(json.loads(path.read_text()),{'plan':'old procedure'})
    def test_editing_shortcut_demotes_authorization_and_undo_restores(self):
        row=self.row('skills');base={'identifier':row['identifier'],'revision':row['revision']};path=self.root/'skills.json';original=path.read_bytes()
        self.assertIn('error',self.invoke(action='edit',value='rm -rf /',confirmed=True,**base));self.assertEqual(path.read_bytes(),original)
        result=self.invoke(action='edit',value=atticus.SHOW+' Other',confirmed=True,**base);self.assertEqual(result.get('status'),'saved',result)
        entry=json.loads(path.read_text())['fixture'];self.assertFalse(entry['evidence']['confirmed']);self.assertEqual(entry['evidence']['corrections'][-1]['reason'],'owner edited steps')
        self.assertEqual(memory_workflows.latest_recoverable(str(self.root)),result['backup'])
        self.assertEqual(self.invoke(action='restore',backup_id=result['backup'],confirmed=True).get('status'),'restored');self.assertEqual(path.read_bytes(),original)
    def test_stale_view_cannot_delete_after_cooperating_writer(self):
        row=self.row('skills');env=dict(os.environ,ATTICUS_DIR=str(self.root),PYTHONPYCACHEPREFIX='/tmp/atticus-test-cache',ATTICUS_POSTHOG_KEY='')
        env.pop('ATTICUS_ASK',None);env.pop('ATTICUS_AGENT',None)
        p=subprocess.run([sys.executable,'-c',"import atticus; atticus._save_shortcut('fixture', 'open -a Other')"],env=env,text=True,capture_output=True,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr);before=(self.root/'skills.json').read_bytes()
        self.assertIn('error',self.invoke(action='delete',identifier=row['identifier'],revision=row['revision'],confirmed=True));self.assertEqual((self.root/'skills.json').read_bytes(),before)
    def test_unknown_fields_fail_without_mutation(self):
        path=self.root/'skills.json';obj=json.loads(path.read_text());obj['fixture']['future']={'preserve':True};path.write_text(json.dumps(obj));original=path.read_bytes();row=self.row('skills')
        self.assertIn('error',self.invoke(action='delete',identifier=row['identifier'],revision=row['revision'],confirmed=True));self.assertEqual(path.read_bytes(),original)

if __name__=='__main__': unittest.main()
