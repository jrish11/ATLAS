import tempfile
import unittest
from pathlib import Path
from vault_journal import JournalError, daily_summary, journal_completed

class VaultJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); (self.root / '.obsidian').mkdir()
        self.task = {'id':'fixture-1', 'title':'Reviewed fixture', 'status':'done', 'verified':True, 'ended':1793390400}

    def test_verified_entries_deduplicate_and_aggregate_without_rewriting(self):
        one = journal_completed(self.root, self.task)
        path = Path(one['path']); original = path.read_text()
        self.assertIn('Reviewed fixture', original)
        self.assertEqual(journal_completed(self.root, self.task)['status'], 'duplicate')
        two = journal_completed(self.root, {**self.task, 'id':'fixture-2'})
        self.assertEqual(path.read_text(), original)
        self.assertNotEqual(one['path'], two['path'])
        self.assertEqual(len(daily_summary(self.root, path.parent.name)),2)

    def test_unverified_and_invalid_vault_do_not_write(self):
        with self.assertRaises(JournalError): journal_completed(self.root, {**self.task, 'verified':False})
        self.assertFalse((self.root/'Atticus').exists())
        with tempfile.TemporaryDirectory() as other:
            with self.assertRaises(JournalError): journal_completed(other, self.task)

    def test_concurrent_external_creation_is_preserved_as_conflict(self):
        def edit(p): p.write_text('External edit')
        result = journal_completed(self.root, self.task, edit)
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(Path(result['path']).read_text(), 'External edit')
        self.assertEqual(daily_summary(self.root, Path(result['path']).parent.name),[])

    def test_existing_entry_modified_externally_is_not_overwritten(self):
        path=Path(journal_completed(self.root,self.task)['path']);path.write_text('User edited')
        self.assertEqual(journal_completed(self.root,self.task)['status'],'conflict')
        self.assertEqual(path.read_text(),'User edited')

    def test_symlinked_area_is_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            (self.root/'Atticus').symlink_to(other)
            with self.assertRaises(JournalError): journal_completed(self.root, self.task)

if __name__ == '__main__': unittest.main()
