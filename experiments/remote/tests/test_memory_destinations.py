import json, os, tempfile, unittest
from unittest.mock import Mock
from pathlib import Path
import personal_commands as p
import memory_destinations as m

class DestinationMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup); self.d=self.tmp.name
        p.save(self.d,'Fixture','https://example.org/old',['home'])
    def test_document_delete_restore_conflict_and_reject_url_edit(self):
        doc=Path(self.d).resolve()/'notes.txt';doc.write_text('fixture');p.save_document(self.d,'Notes',str(doc),[],confirmed=True)
        row=next(x for x in p.read(self.d) if x.get('type')=='document');revision=m.digest(row)
        with self.assertRaises(ValueError):m.manage(self.d,'edit',label='Notes',url='https://example.org/',aliases=[],confirmed=True,revision=revision)
        result=m.manage(self.d,'delete',label='Notes',confirmed=True,revision=revision);self.assertIsNone(p.resolve(self.d,'open notes'))
        self.assertEqual(m.manage(self.d,'restore',backup_id=result['backup'],confirmed=True)['status'],'restored')
        self.assertEqual(p.resolve(self.d,'open notes')['path'],str(doc));doc.unlink()
        runner=Mock();self.assertIn('unavailable',p.open_destination(p.resolve(self.d,'open notes'),runner));runner.assert_not_called()

    def test_edit_and_restore_record(self):
        result=m.manage(self.d,'edit',label='Fixture',url='https://example.org/new',aliases=['home'],confirmed=True,revision=m.digest(p.read(self.d)[0]))
        self.assertEqual(p.read(self.d)[0]['url'],'https://example.org/new')
        self.assertEqual(p.read(self.d)[0]['corrections'][-1]['url'],'https://example.org/old')
        self.assertEqual(os.stat(Path(self.d,'memory-backups',result['backup']+'.json')).st_mode & 0o777,0o600)
        m.manage(self.d,'restore',backup_id=result['backup'],confirmed=True)
        self.assertEqual(p.read(self.d)[0]['url'],'https://example.org/old')
    def test_delete_and_restore(self):
        result=m.manage(self.d,'delete',label='Fixture',confirmed=True,revision=m.digest(p.read(self.d)[0]))
        self.assertFalse(p.read(self.d));self.assertEqual(m.latest_recoverable(self.d),result['backup']);m.manage(self.d,'restore',backup_id=result['backup'],confirmed=True)
        self.assertEqual(p.read(self.d)[0]['label'],'Fixture')
    def test_cancellation_and_conflict_never_change_registry(self):
        with self.assertRaises(ValueError):m.manage(self.d,'delete',label='Fixture')
        result=m.manage(self.d,'delete',label='Fixture',confirmed=True,revision=m.digest(p.read(self.d)[0]))
        p.save(self.d,'Other','https://other.example/',[])
        self.assertEqual(m.latest_recoverable(self.d),'')
        with self.assertRaisesRegex(ValueError,'changed'):m.manage(self.d,'restore',backup_id=result['backup'],confirmed=True)
        self.assertEqual([r['label'] for r in p.read(self.d)],['Other'])
    def test_stale_displayed_revision_cannot_overwrite_newer_change(self):
        revision=m.digest(p.read(self.d)[0])
        p.save(self.d,'Fixture','https://example.org/newer',['home'])
        with self.assertRaisesRegex(ValueError,'changed since'):
            m.manage(self.d,'delete',label='Fixture',revision=revision,confirmed=True)
        self.assertEqual(p.read(self.d)[0]['url'],'https://example.org/newer')

    def test_unknown_fields_are_never_discarded(self):
        path=Path(self.d,'destinations.json');data=json.loads(path.read_text());data[0]['future']='keep';path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'Unknown'):m.manage(self.d,'delete',label='Fixture',confirmed=True,revision=m.digest(p.read(self.d)[0]))
        self.assertEqual(json.loads(path.read_text())[0]['future'],'keep')
    def test_conflicting_alias_and_credential_url_are_rejected(self):
        p.save(self.d,'Other','https://other.example/',['elsewhere'])
        for url,aliases in [('https://user:pass@example.org/',[]),('https://example.org/?key=secret',[]),('https://example.org/',['elsewhere'])]:
            with self.assertRaises(ValueError):m.manage(self.d,'edit',label='Fixture',url=url,aliases=aliases,confirmed=True,revision=m.digest(p.read(self.d)[0]))
        self.assertEqual(len(p.read(self.d)),2)
if __name__=='__main__':unittest.main()
