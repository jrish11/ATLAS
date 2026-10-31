import json, tempfile, unittest
from pathlib import Path
import memory_inspector as m
class MemoryInspectorTests(unittest.TestCase):
 def test_schema_exclusion_and_structural_export(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d); private=p/'private';private.mkdir();public=p/'public';public.mkdir()
   def write(name,obj):(p/name).write_text(json.dumps(obj))
   write('me.json',{'facts':[{'kind':'style','value':'confidential fixture','source':'you'}, {'kind':'private','sensitive':True}]})
   (p/'memory.md').write_text('- Test rule\n')
   write('destinations.json',[{'label':'Portal','confirmed':True,'url':'https://example.org/private','corrections':[{'source':'owner','confirmed':True}]}])
   write('projects.json',[{'label':'excluded','folder':str(private),'confirmed':True},{'label':'included','folder':str(public),'confirmed':True}])
   write('skills.json',{'workflow':{'evidence':{'source':'owner','confirmed':True}}})
   (p/'recent.jsonl').write_text(json.dumps({'q':'session query','t':1})+'\n')
   agent=p/'agents'/('a'*32);agent.mkdir(parents=True);(agent/'state.json').write_text(json.dumps({'title':'task','folder':str(public),'status':'done'}))
   rows=m.inspect(d,[str(private)]); cats={r['category'] for r in rows}
   self.assertTrue({'profile','rules','destinations','projects','workflows','corrections','tasks'}<=cats)
   self.assertNotIn('excluded',[r['title'] for r in rows]);self.assertNotIn('sessions',cats)
   encoded=json.dumps(m.export_metadata(rows,list(m.CATEGORIES)))
   for private_text in ('confidential fixture','Portal','example.org','Test rule','included','"workflow"','"task"'):
    self.assertNotIn(private_text,encoded)
   self.assertIn('sessions',{r['category'] for r in m.inspect(d,[])})
 def test_private_child_and_unscoped_tasks_are_hidden(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);private=p/'private';child=private/'nested';child.mkdir(parents=True)
   (p/'projects.json').write_text(json.dumps([{'label':'hidden','folder':str(child),'confirmed':True}]))
   agents=p/'agents';agents.mkdir()
   for name,folder in [('a'*32,str(child)),('b'*32,'')]:
    agent=agents/name;agent.mkdir();(agent/'state.json').write_text(json.dumps({'title':name,'folder':folder}))
   self.assertEqual(m.inspect(d,[str(private)]),[])
 def test_symlinked_stores_are_not_followed(self):
  with tempfile.TemporaryDirectory() as d,tempfile.TemporaryDirectory() as other:
   Path(other,'source.json').write_text(json.dumps({'facts':[{'kind':'private'}]}))
   Path(d,'me.json').symlink_to(Path(other,'source.json'))
   self.assertEqual(m.inspect(d),[])
 def test_export_ignores_unknown_fields_and_untrusted_metadata(self):
  data=m.export_metadata([{'category':'projects','title':'secret','source':'secret','scope':'secret','password':'secret','status':'secret'}],['projects'])
  self.assertNotIn('secret',json.dumps(data));self.assertEqual(data['items'][0]['source'],'unknown')
 def test_legacy_profile_is_indexed_without_rewrite(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d,'me.json'); original=json.dumps({'name':'Example','facts':['legacy personal value'],'future':{'untouched':True}});p.write_text(original)
   rows=m.inspect(d)
   self.assertEqual([r['title'] for r in rows],['Legacy name','Legacy fact']);self.assertEqual(p.read_text(),original)
 def test_invalid_exclusion_fails_closed(self):
  with self.assertRaises(ValueError):m.inspect('/tmp',['relative'])
 def test_unknown_malformed_stores_are_safe(self):
  with tempfile.TemporaryDirectory() as d:
   Path(d,'me.json').write_text('{broken')
   Path(d,'destinations.json').write_text('[1,{},null]')
   self.assertEqual(m.inspect(d),[])
if __name__=='__main__':unittest.main()
