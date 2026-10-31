import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import atticus
import personal_commands as p


class PersonalCommandsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def test_confirmed_alias_and_ambiguous_destinations(self):
        p.save(self.dir, 'School', 'https://example.org/', ['school portal'])
        self.assertEqual(p.resolve(self.dir, 'go to my school portal')['label'], 'School')
        self.assertIsNone(p.resolve(self.dir, 'search school portal'))
        with self.assertRaises(ValueError):
            p.save(self.dir, 'Other', 'https://other.example/', ['school portal'])
        with open(os.path.join(self.dir, 'destinations.json'), 'w') as f:
            json.dump([{'label':'one','url':'https://example.org/','browser':'Safari','confirmed':True,'aliases':['x']},
                       {'label':'two','url':'https://elsewhere.org/','browser':'Safari','confirmed':True,'aliases':['x']}], f)
        self.assertTrue(p.resolve(self.dir, 'open x')['ambiguous'])

    def test_reject_secrets_and_insecure_urls(self):
        for url in ('http://example.org', 'https://user:secret@example.org', 'https://example.org/?token=secret', 'https://example.org/#token'):
            with self.assertRaises(ValueError): p.save(self.dir, 'test', url, [])

    def test_remember_current_saves_only_safe_front_safari_url(self):
        runner = Mock(return_value=SimpleNamespace(returncode=0, stdout='https://example.org/home\n'))
        self.assertIn('Remembered', p.remember_current(self.dir, 'history homework', runner))
        self.assertEqual(p.resolve(self.dir, 'open history homework')['url'], 'https://example.org/home')
        runner.return_value.stdout = 'https://example.org/?token=secret'
        self.assertIn('cannot safely save', p.remember_current(self.dir, 'other', runner))
        self.assertIsNone(p.resolve(self.dir, 'open other'))

    def test_untrusted_agent_cannot_save_current_page(self):
        with patch.dict(os.environ, {'ATTICUS_AGENT':'1'}), patch.object(p, 'remember_current') as remember:
            self.assertIn('explicit request', atticus.fast('remember this is my homework'))
            remember.assert_not_called()

    def test_malformed_destination_store_is_never_rewritten(self):
        path=Path(self.dir,'destinations.json')
        for invalid in ([None], [1], [{'label':'Fixture','aliases':None}], {'not':'a list'}):
            path.write_text(json.dumps(invalid));before=path.read_bytes()
            with self.assertRaises(ValueError):p.save(self.dir,'Fixture','https://example.org/',[])
            self.assertEqual(path.read_bytes(),before)
            with self.assertRaises(ValueError):p.remove(self.dir,'Fixture')
            self.assertEqual(path.read_bytes(),before)
            runner=Mock(return_value=SimpleNamespace(returncode=0,stdout='https://example.org/'))
            self.assertIn('could not save',p.remember_current(self.dir,'Fixture',runner).lower())
            self.assertEqual(path.read_bytes(),before)

    def test_remember_current_requires_front_safari(self):
        runner = Mock(return_value=SimpleNamespace(returncode=0, stdout='not-safari\n'))
        self.assertIn('Bring the correct Safari page', p.remember_current(self.dir, 'homework', runner))
        self.assertEqual(p.read(self.dir), [])

    def test_existing_fast_router_uses_confirmed_destination(self):
        p.save(self.dir, 'Fixture', 'https://example.org/', ['fixture portal'])
        with patch.object(atticus, 'DIR', self.dir), patch.object(p, 'open_destination', return_value='Fixture opened') as opened:
            self.assertEqual(atticus.fast('open fixture portal'), 'Fixture opened')
            self.assertEqual(opened.call_count, 1)

    def test_owner_correction_records_previous_destination(self):
        p.save(self.dir, 'Fixture', 'https://example.org/old', ['fixture'])
        p.save(self.dir, 'Fixture', 'https://example.org/new', ['fixture'])
        row = p.resolve(self.dir, 'open fixture')
        self.assertEqual(row['url'], 'https://example.org/new')
        self.assertEqual(row['corrections'][0]['url'], 'https://example.org/old')
        self.assertTrue(row['corrections'][0]['confirmed'])

    def test_remove_destination(self):
        p.save(self.dir, 'Fixture', 'https://example.org/', [])
        self.assertTrue(p.remove(self.dir, 'Fixture'))
        self.assertFalse(p.remove(self.dir, 'Fixture'))
        self.assertEqual(p.read(self.dir), [])

    def test_missing_or_invalid_label_never_dispatches_safari(self):
        runner=Mock()
        for label in (None, 1, '', '   '):
            row={'label':label,'url':'https://example.org/','browser':'Safari','aliases':['fixture'],'confirmed':True}
            Path(self.dir,'destinations.json').write_text(json.dumps([row]))
            self.assertIsNone(p.resolve(self.dir,'open fixture'))
            self.assertIn('nothing was opened',p.open_destination(row,runner))
        runner.assert_not_called()

    def test_documents_are_confirmed_revision_bound_and_never_execute_scripts(self):
        root=Path(self.dir).resolve(); doc=root/'fixture.txt';doc.write_text('fixture')
        with self.assertRaises(ValueError):p.save_document(self.dir,'Notes',str(doc),[],confirmed=False)
        p.save_document(self.dir,'Notes',str(doc),['notes'],confirmed=True);row=p.resolve(self.dir,'open notes');runner=Mock(return_value=SimpleNamespace(returncode=0))
        self.assertIn('Requested opening',p.open_destination(row,runner));self.assertEqual(runner.call_args.args[0],['/usr/bin/open','--',str(doc)])
        doc.write_text('changed document');runner.reset_mock();self.assertIn('changed',p.open_destination(row,runner));runner.assert_not_called()
        doc.unlink();self.assertIn('unavailable',p.open_destination(row,runner));runner.assert_not_called()
        script=root/'fixture.command';script.write_text('echo no')
        with self.assertRaises(ValueError):p.save_document(self.dir,'Script',str(script),[],confirmed=True)
        link=root/'link.txt';link.symlink_to(script)
        with self.assertRaises(ValueError):p.save_document(self.dir,'Link',str(link),[],confirmed=True)
    def test_denied_document_open_and_ambiguous_names_are_safe(self):
        root=Path(self.dir).resolve();one=root/'one.txt';two=root/'two.txt';one.write_text('1');two.write_text('2')
        p.save_document(self.dir,'One',str(one),[],confirmed=True);row=p.resolve(self.dir,'open one')
        runner=Mock(return_value=SimpleNamespace(returncode=1));self.assertIn('could not be opened',p.open_destination(row,runner));self.assertEqual(runner.call_count,1)
        rows=p.read(self.dir);second={**rows[0],'label':'Two','path':str(two),'file_revision':p.document_revision(str(two))};rows.append(second)
        Path(self.dir,'destinations.json').write_text(json.dumps(rows));self.assertEqual(p.resolve(self.dir,'open one'),{'ambiguous':True})

    def test_document_alias_conflict_is_rejected_without_change(self):
        root=Path(self.dir).resolve();one=root/'one.md';two=root/'two.md';one.write_text('1');two.write_text('2')
        p.save_document(self.dir,'One',str(one),['shared'],confirmed=True);before=Path(self.dir,'destinations.json').read_bytes()
        with self.assertRaises(ValueError):p.save_document(self.dir,'Two',str(two),['shared'],confirmed=True)
        self.assertEqual(Path(self.dir,'destinations.json').read_bytes(),before)

    def test_existing_tab_does_not_open_another(self):
        runner = Mock(return_value=SimpleNamespace(returncode=0, stdout='switched\n'))
        self.assertIn('Requested switching', p.open_destination({'url':'https://example.org/', 'label':'test'}, runner))
        self.assertEqual(runner.call_count, 1)

    def test_absent_opens_but_does_not_claim_verified(self):
        runner = Mock(side_effect=[SimpleNamespace(returncode=0, stdout='absent\n'), SimpleNamespace(returncode=0)])
        self.assertIn('check that the page loaded', p.open_destination({'url':'https://example.org/', 'label':'test'}, runner))
        self.assertEqual(runner.call_count, 2)

    def test_root_url_matches_browser_canonical_trailing_slash(self):
        runner = Mock(return_value=SimpleNamespace(returncode=0, stdout='switched\n'))
        p.open_destination({'url':'https://example.org', 'label':'test'}, runner)
        self.assertEqual(runner.call_args.args[0][-1], 'https://example.org/')

    def test_multiple_tabs_ask_instead_of_guessing(self):
        runner = Mock(return_value=SimpleNamespace(returncode=0, stdout='ambiguous\n'))
        self.assertIn('choose', p.open_destination({'url':'https://example.org/', 'label':'test'}, runner))
        self.assertEqual(runner.call_count, 1)

    def test_permission_failure_never_opens_or_retries(self):
        runner = Mock(return_value=SimpleNamespace(returncode=1, stdout=''))
        self.assertIn('Automation permission', p.open_destination({'url':'https://example.org/', 'label':'test'}, runner))
        self.assertEqual(runner.call_count, 1)

if __name__ == '__main__': unittest.main()
