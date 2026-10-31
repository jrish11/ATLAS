import json
import os
import tempfile
import unittest
from pathlib import Path
import memory_transactions as tx
import memory_rules_store as rs

class Transactions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def write(self, name, value):
        (self.root / name).write_text(value if isinstance(value, str) else json.dumps(value))
    def test_rules_revision_confirmation_and_restore_conflict(self):
        self.write('memory.md', '- first\n- second\n')
        args = (str(self.root), 'rules', 'edit')
        with self.assertRaises(ValueError): tx.manage(*args, identifier='first', revision=tx.digest('first'), value='new')
        with self.assertRaises(ValueError): tx.manage(*args, identifier='first', revision='stale', value='new', confirmed=True)
        self.assertEqual((self.root/'memory.md').read_text(), '- first\n- second\n')
        result = tx.manage(*args, identifier='first', revision=tx.digest('first'), value='new', confirmed=True)
        after = (self.root/'memory.md').read_bytes()
        self.write('memory.md', '- new\n- changed\n')
        with self.assertRaises(ValueError): tx.manage(str(self.root),'rules','restore',backup_id=result['backup'],confirmed=True)
        (self.root/'memory.md').write_bytes(after)
        tx.manage(str(self.root),'rules','restore',backup_id=result['backup'],confirmed=True)
        self.assertEqual([x['text'] for x in rs.parse((self.root/'memory.md').read_bytes())], ['first','second'])
    def test_profile_unknown_legacy_and_private(self):
        for profile in ({'name':'legacy'}, {'version':2,'facts':[{'id':'x','value':'v','unknown':1}]}, {'version':2,'facts':[{'id':'x','value':'v','sensitive':True}]}):
            self.write('me.json', profile)
            with self.assertRaises(ValueError): tx.manage(str(self.root),'profile','delete',identifier='x',revision=tx.digest(profile.get('facts',[{}])[0]),confirmed=True)
            self.assertEqual(json.loads((self.root/'me.json').read_text()), profile)
    def test_large_backup_can_be_discovered_and_restored(self):
        text = 'x' * 4_100_000
        self.write('memory.md', '- ' + text + '\n')
        result = tx.manage(str(self.root), 'rules', 'delete', identifier=text, revision=tx.digest(text), confirmed=True)
        self.assertEqual(tx.latest_recoverable(str(self.root)).get('rules'), result['backup'])
        tx.manage(str(self.root), 'rules', 'restore', backup_id=result['backup'], confirmed=True)
        self.assertEqual(rs.parse((self.root/'memory.md').read_bytes())[0]['text'], text)
    def test_project_delete_restore(self):
        row = {'label':'Example','folder':str(self.root),'aliases':['example'],'confirmed':True,'source':'owner','scope':'device','updated':0}
        self.write('projects.json',[row])
        out=tx.manage(str(self.root),'projects','delete',identifier='Example',revision=tx.digest(row),confirmed=True)
        self.assertEqual(json.loads((self.root/'projects.json').read_text()), [])
        tx.manage(str(self.root),'projects','restore',backup_id=out['backup'],confirmed=True)
        self.assertEqual(json.loads((self.root/'projects.json').read_text()), [row])
        self.assertEqual(os.stat(self.root/'memory-transaction-backups'/ (out['backup']+'.json')).st_mode & 0o777, 0o600)

if __name__ == '__main__': unittest.main()
