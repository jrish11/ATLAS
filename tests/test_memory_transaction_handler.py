import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
import memory_inspector
import memory_rules_store

APP = Path(__file__).resolve().parents[1] / 'atticus.py'

class HandlerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / 'project'; self.project.mkdir()
        self.fact = {'id':'fact123','category':'preferences','kind':'style','value':'plain','source':'you','date':'2026-01-01'}
        self.project_row = {'label':'Fixture','folder':str(self.project),'aliases':['fixture'],'confirmed':True,'source':'owner','scope':'device','updated':1}
        self.write('me.json', {'version':2,'facts':[self.fact]})
        self.write('projects.json', [self.project_row]); (self.root/'memory.md').write_text('- Example rule\n')
    def write(self, name, obj): (self.root/name).write_text(json.dumps(obj))
    def invoke(self, request, agent=False):
        env = dict(os.environ, ATTICUS_DIR=str(self.root), PYTHONPYCACHEPREFIX='/tmp/atticus-test-cache', ATTICUS_POSTHOG_KEY='')
        env.pop('ATTICUS_ASK',None);env.pop('ATTICUS_AGENT',None)
        if agent: env['ATTICUS_AGENT']='1'
        p = subprocess.run([sys.executable, str(APP), '--memory-transaction'],input=json.dumps(request),text=True,capture_output=True,env=env,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr); return json.loads(p.stdout)
    def row(self, category):
        return next(r for r in memory_inspector.inspect(str(self.root)) if r['category']==category)
    def request(self, row, action, **extra):
        return {'category':row['category'],'action':action,'identifier':row['identifier'],'revision':row['revision'], **extra}
    def test_each_category_edit_delete_and_restore_using_displayed_revision(self):
        for category, value, filename in [('profile','concise','me.json'),('rules','Revised rule','memory.md'),('projects',{'folder':str(self.project),'aliases':['fixture','sample']},'projects.json')]:
            with self.subTest(category=category):
                path=self.root/filename; original=path.read_bytes(); row=self.row(category)
                denied=self.invoke(self.request(row,'edit',value=value,confirmed=False)); self.assertIn('error',denied); self.assertEqual(path.read_bytes(),original)
                denied=self.invoke(self.request(row,'edit',value=value,confirmed=True),agent=True); self.assertIn('error',denied);self.assertEqual(path.read_bytes(),original)
                changed=self.invoke(self.request(row,'edit',value=value,confirmed=True)); self.assertEqual(changed.get('status'),'saved',changed)
                self.assertNotEqual(path.read_bytes(),original)
                stale=self.invoke(self.request(row,'delete',confirmed=True));self.assertIn('error',stale)
                restored=self.invoke({'category':category,'action':'restore','backup_id':changed['backup'],'confirmed':True});self.assertEqual(restored.get('status'),'restored',restored);self.assertEqual([r['text'] for r in memory_rules_store.parse(path.read_bytes())], ['Example rule']) if category == 'rules' else self.assertEqual(path.read_bytes(),original)
                deleted=self.invoke(self.request(self.row(category),'delete',confirmed=True));self.assertEqual(deleted.get('status'),'deleted',deleted)
                restored=self.invoke({'category':category,'action':'restore','backup_id':deleted['backup'],'confirmed':True});self.assertEqual(restored.get('status'),'restored',restored);self.assertEqual([r['text'] for r in memory_rules_store.parse(path.read_bytes())], ['Example rule']) if category == 'rules' else self.assertEqual(path.read_bytes(),original)
    def test_correction_handler_and_discoverable_undo(self):
        correction={'url':'https://example.org/old','source':'owner','confirmed':True,'extra':{'keep':True}}
        parent={'label':'Portal','url':'https://example.org/','aliases':['portal'],'browser':'Safari','confirmed':True,'source':'owner','corrections':[correction]}
        self.write('destinations.json',[parent]); row=self.row('corrections')
        saved=self.invoke(self.request(row,'edit',value='https://example.org/new',confirmed=True));self.assertEqual(saved.get('status'),'saved',saved)
        import memory_corrections
        self.assertEqual(memory_corrections.latest_recoverable(str(self.root)),saved['backup'])
        restored=self.invoke({'category':'corrections','action':'restore','backup_id':saved['backup'],'confirmed':True});self.assertEqual(restored.get('status'),'restored',restored)
        result=json.loads((self.root/'destinations.json').read_text())[0]['corrections'][0]
        self.assertEqual(result['url'],correction['url']);self.assertEqual(result['extra'],correction['extra']);self.assertIn('id',result)
    def test_conflict_and_exclusion_are_enforced_by_handler(self):
        row=self.row('projects'); result=self.invoke(self.request(row,'delete',confirmed=True))
        self.write('projects.json',[dict(self.project_row,label='New')])
        self.assertIn('error',self.invoke({'category':'projects','action':'restore','backup_id':result['backup'],'confirmed':True}))
        self.write('projects.json',[self.project_row]); row=self.row('projects')
        self.write('settings.json',{'journalExcludedFolders':[str(self.project)]})
        self.assertIn('error',self.invoke(self.request(row,'delete',confirmed=True)))
        self.assertEqual(json.loads((self.root/'projects.json').read_text()),[self.project_row])
    def test_index_hides_excluded_projects_and_uneditable_unknown_fields(self):
        rows=memory_inspector.inspect(str(self.root),[str(self.project)])
        self.assertNotIn('projects',[r['category'] for r in rows])
        self.fact['future']='preserve';self.write('me.json',{'version':2,'facts':[self.fact]})
        self.assertNotIn('revision',self.row('profile'))
    def test_unknown_profile_fields_survive_reads_and_old_writer_rejects_them(self):
        import atticus
        from unittest.mock import patch
        self.fact['future'] = {'keep': True}
        self.write('me.json', {'version':2, 'facts':[self.fact]})
        original = (self.root/'me.json').read_bytes()
        with patch.object(atticus, 'DIR', str(self.root)), patch.object(atticus, 'ME_FILE', str(self.root/'me.json')):
            atticus.me()
            self.assertEqual((self.root/'me.json').read_bytes(), original)
            with self.assertRaises(ValueError): atticus.profile_add('notes','new',source='you')
            self.assertEqual((self.root/'me.json').read_bytes(), original)
    def test_excluded_project_is_never_copied_into_backup(self):
        private=self.root/'private'; private.mkdir()
        self.write('projects.json',[self.project_row, dict(self.project_row,label='Private',folder=str(private))])
        row=next(r for r in memory_inspector.inspect(str(self.root), [str(private)]) if r['category']=='projects')
        self.write('settings.json',{'journalExcludedFolders':[str(private)]})
        result=self.invoke(self.request(row,'delete',confirmed=True))
        self.assertIn('error',result)
        self.assertFalse((self.root/'memory-transaction-backups').exists())
    def test_null_profile_is_not_overwritten_by_old_writer(self):
        import atticus
        from unittest.mock import patch
        (self.root/'me.json').write_text('null')
        with patch.object(atticus, 'DIR', str(self.root)), patch.object(atticus, 'ME_FILE', str(self.root/'me.json')):
            with self.assertRaises(ValueError): atticus.profile_add('notes','new',source='you')
        self.assertEqual((self.root/'me.json').read_text(), 'null')
    def test_sensitive_profile_values_are_not_editable(self):
        self.fact['kind']='password';self.write('me.json',{'version':2,'facts':[self.fact]})
        self.assertNotIn('revision',self.row('profile'))
    def test_recovery_is_discoverable_after_restart_and_exclusions_can_block_restore(self):
        import memory_transactions
        row=self.row('projects');deleted=self.invoke(self.request(row,'delete',confirmed=True))
        self.assertEqual(memory_transactions.latest_recoverable(str(self.root))['projects'], deleted['backup'])
        self.write('settings.json',{'journalExcludedFolders':[str(self.project)]})
        result=self.invoke({'category':'projects','action':'restore','backup_id':deleted['backup'],'confirmed':True})
        self.assertIn('error',result);self.assertEqual(json.loads((self.root/'projects.json').read_text()),[])
    def test_legacy_editors_use_confirmed_transaction_path(self):
        ui = (APP.parent/'ui/settings.html').read_text()
        rules = ui.split("$('rules').querySelectorAll('[data-i]')",1)[1].split('    const add =',1)[0]
        profile = ui.split("document.querySelectorAll('[data-profile-id]')",1)[1].split("document.querySelectorAll('[data-profile-add]')",1)[0]
        self.assertIn("do:'memoryTransaction'", rules)
        self.assertIn('matches.length===1', rules)
        self.assertIn("do:'memoryTransaction'", profile)
        self.assertNotIn("do:'me',action:'drop'", profile)
        swift = APP.with_name('Atticus.swift').read_text()
        legacy = swift.split('case "me":',1)[1].split('case "apps":',1)[0]
        for unsafe in ('case "set":','case "drop":','case "forget-source":','case "rule":','case "forget",'):
            self.assertNotIn(unsafe, legacy)
        transaction = swift.split('case "memoryTransaction":',1)[1].split('case "memoryDestination":',1)[0]
        self.assertIn('else { refresh(); return }', transaction)
    def test_native_confirmation_and_build_packaging(self):
        swift=APP.with_name('Atticus.swift').read_text()
        branch=swift.split('case "memoryTransaction":',1)[1].split('case "memoryDestination":',1)[0]
        self.assertIn('guard confirm(',branch);self.assertIn('else { return }',branch);self.assertIn('"confirmed":true',branch)
        self.assertIn('memory_transactions.py',APP.with_name('build-personal-dev.sh').read_text())

if __name__ == '__main__': unittest.main()
