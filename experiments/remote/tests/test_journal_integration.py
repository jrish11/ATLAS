import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import atticus

class JournalIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); (self.root/'.obsidian').mkdir()
        self.row = {'id':'fixture', 'title':'Completed fixture', 'status':'done', 'verified':True, 'ended':1793390400, 'folder':str(self.root/'project')}
        self.settings = {'journalEnabled':True, 'journalVault':str(self.root), 'journalExcludedFolders':[], 'journalExcludedTerms':[]}
        self.patch = patch.object(atticus, 'pref', side_effect=lambda key, default:self.settings.get(key, default))
        self.patch.start(); self.addCleanup(self.patch.stop)

    def test_opt_in_verified_task_is_journaled_once(self):
        self.assertEqual(atticus.journal_verified_agent(self.row)['status'], 'written')
        self.assertEqual(atticus.journal_verified_agent(self.row)['status'], 'duplicate')
        self.assertEqual(len(list((self.root/'Atticus'/'Agent Activity').glob('*/*.md'))), 1)

    def test_disabled_unverified_and_excluded_do_not_write(self):
        self.settings['journalEnabled'] = False
        self.assertEqual(atticus.journal_verified_agent(self.row)['status'], 'disabled')
        self.settings['journalEnabled'] = True
        self.assertEqual(atticus.journal_verified_agent({**self.row, 'verified':False})['status'], 'unverified')
        self.settings['journalExcludedFolders'] = [str(self.root/'project')]
        self.assertEqual(atticus.journal_verified_agent(self.row)['status'], 'excluded')
        self.assertEqual(atticus.journal_verified_agent({**self.row, 'folder':''})['status'], 'excluded_unknown_scope')
        self.settings['journalExcludedFolders'] = []
        self.settings['journalExcludedTerms'] = ['fixture']
        self.assertEqual(atticus.journal_verified_agent(self.row)['status'], 'excluded')
        self.assertFalse((self.root/'Atticus').exists())

    def test_user_confirmation_records_verified_completion(self):
        with patch.object(atticus, 'DIR', str(self.root)):
            manager = atticus.Agents(emit=lambda event: None)
            self.addCleanup(manager.close)
            row = manager.new()
            row.update(title='Completed fixture', status='done', ended=1793390400, folder=str(self.root/'project'))
            manager.rows[row['id']] = row; manager.save(row)
            manager.command({'action':'verify-result', 'id':row['id'], 'confirmed':False})
            self.assertNotIn('verified', row)
            manager.command({'action':'verify-result', 'id':row['id'], 'confirmed':True})
            self.assertTrue(row['verified'])
            self.assertEqual(row['journalStatus'], 'written')
            self.assertEqual(len(list((self.root/'Atticus'/'Agent Activity').glob('*/*.md'))), 1)

    def test_invalid_exclusion_fails_closed(self):
        self.settings['journalExcludedFolders'] = ['relative']
        self.assertEqual(atticus.journal_verified_agent(self.row)['status'], 'invalid_privacy_settings')

if __name__ == '__main__': unittest.main()
