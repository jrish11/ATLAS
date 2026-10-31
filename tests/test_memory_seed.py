import json
import tempfile
import unittest
from pathlib import Path
import memory_seed

class SeedTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.root=self.tmp.name
  self.seed={'version':1,'records':[{'category':'basics','kind':'name','value':'Example'},{'category':'preferences','kind':'style','value':'Concise'}]}
 def test_preview_confirm_duplicate_and_provenance(self):
  p=memory_seed.snapshot(self.root,self.seed); self.assertEqual([r['status'] for r in p['records']],['add','add']);self.assertFalse(Path(self.root,'me.json').exists())
  self.assertEqual(memory_seed.snapshot(self.root,self.seed,p['revision'],True)['added'],2)
  rows=json.loads(Path(self.root,'me.json').read_text())['facts'];self.assertTrue(all(x['source']=='you' and x['id'].startswith('seed-') for x in rows))
  self.assertEqual(memory_seed.snapshot(self.root,self.seed)['records'][0]['status'],'skip-existing')
 def test_stale_and_cancel_leave_store(self):
  p=memory_seed.snapshot(self.root,self.seed); Path(self.root,'me.json').write_text('{"version":2,"facts":[]}')
  with self.assertRaises(ValueError):memory_seed.snapshot(self.root,self.seed,p['revision'],True)
  self.assertEqual(json.loads(Path(self.root,'me.json').read_text())['facts'],[])
 def test_reject_private_unknown_and_duplicates(self):
  for s in [dict(self.seed,extra=1),{'version':1,'records':[{'category':'health','kind':'x','value':'y'}]},{'version':1,'records':[{'category':'notes','kind':'password','value':'abc'}]},{'version':1,'records':self.seed['records']*2}]:
   with self.assertRaises(ValueError): memory_seed.snapshot(self.root,s)
 def test_unknown_fields_and_legacy_not_rewritten(self):
  for raw in ({'version':2,'facts':[{'id':'x','unknown':1}]},{'name':'Example'}):
   path=Path(self.root,'me.json');path.write_text(json.dumps(raw));before=path.read_bytes()
   with self.assertRaises(ValueError): memory_seed.snapshot(self.root,self.seed)
   self.assertEqual(path.read_bytes(),before)
