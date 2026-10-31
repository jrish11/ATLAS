import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import atticus

class WorkflowConfidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.patch=patch.multiple(atticus, DIR=str(self.root), SKILLS=str(self.root/'skills.json'))
        self.patch.start(); self.addCleanup(self.patch.stop)

    def test_legacy_records_migrate_without_changing_old_file(self):
        legacy={'auto':{'cmds':['open x'],'reply':'Done.','at':time.strftime('%Y-%m-%d')},
                'owner':{'cmds':['open y'],'reply':'Done.','asked':'when I say owner open y','mine':True,'at':time.strftime('%Y-%m-%d')}}
        path=self.root/'skills.json';path.write_text(json.dumps(legacy))
        migrated=atticus.skills()
        self.assertEqual(json.loads(path.read_text()),legacy)
        self.assertFalse(atticus.workflow_trusted(migrated['auto']))
        self.assertTrue(atticus.workflow_trusted(migrated['owner']))
        atticus.save_skills(migrated)
        self.assertEqual(atticus.skills()['auto']['evidence']['source'],'legacy')
        self.assertEqual(path.stat().st_mode & 0o777,0o600)

    def test_three_observations_or_explicit_owner_confirmation(self):
        entry={};cmds=['open x']
        for count in range(1,4):
            evidence=atticus.workflow_evidence(entry,cmds)
            entry={'cmds':cmds,'evidence':evidence}
            self.assertFalse(atticus.workflow_trusted(entry))
        replacement=atticus.workflow_evidence(entry,['open z'])
        self.assertFalse(atticus.workflow_trusted({'evidence':replacement}))
        self.assertEqual(replacement['successes'],1)
        self.assertEqual(len(replacement['corrections']),1)
        explicit=atticus.workflow_evidence({},cmds,True)
        self.assertTrue(atticus.workflow_trusted({'evidence':explicit}))

    def test_risky_and_non_navigation_shortcuts_never_bypass_the_gate(self):
        self.assertFalse(atticus.instant_replay_allowed("osascript -e 'tell application \"Fixture\" to quit'"))
        self.assertFalse(atticus.instant_replay_allowed(atticus.HANDS + ' menu Fixture Delete'))
        self.assertFalse(atticus.instant_replay_allowed(atticus.TYPE + ' secret'))
        self.assertTrue(atticus.instant_replay_allowed(atticus.SHOW + ' Fixture'))
        self.assertTrue(atticus.instant_replay_allowed(atticus.PLACE + ' Fixture left current'))

    def test_owner_confirmation_never_bypasses_action_gate_even_if_safe_mode_off(self):
        row={'cmds':["osascript -e 'tell application \"Fixture\" to quit'"], 'reply':'Done.',
             'mine':True, 'at':time.strftime('%Y-%m-%d')}
        (self.root/'skills.json').write_text(json.dumps({'fixture':row}))
        with patch.object(atticus, 'pref', return_value=False), patch.object(atticus.subprocess, 'run') as action:
            self.assertIsNone(atticus.replay('fixture'))
            action.assert_not_called()

    def test_failure_demotes_previously_confirmed_shortcut(self):
        row={'cmds':['open x'],'reply':'Done.','mine':True,'asked':'when i say x open x', 'at':time.strftime('%Y-%m-%d')}
        (self.root/'skills.json').write_text(json.dumps({'x':row}))
        self.assertTrue(atticus.workflow_trusted(atticus.skills()['x']))
        atticus.workflow_failed('x')
        saved=atticus.skills()['x']['evidence']
        self.assertFalse(saved['confirmed'])
        self.assertEqual(saved['successes'],0)
        self.assertFalse(atticus.workflow_trusted({'evidence':saved}))


    def test_explicit_confirmation_shows_steps_and_requires_unchanged_binding(self):
        row={'cmds':[atticus.SHOW+' Fixture'],'reply':'Done.','at':time.strftime('%Y-%m-%d')}
        (self.root/'skills.json').write_text(json.dumps({'fixture':row}))
        with patch.dict('os.environ',{'ATTICUS_ASK':str(self.root)}), patch.object(atticus,'ask_user',return_value='y') as ask:
            self.assertIn('confirmed',atticus.confirm_workflow('fixture').lower())
            self.assertEqual(ask.call_args.args[0]['cmd'],row['cmds'][0])
        self.assertTrue(atticus.workflow_trusted(atticus.skills()['fixture']))

    def test_denial_or_changed_steps_never_confirm(self):
        row={'cmds':[atticus.SHOW+' Fixture'],'reply':'Done.','at':time.strftime('%Y-%m-%d')}
        path=self.root/'skills.json';path.write_text(json.dumps({'fixture':row}))
        with patch.dict('os.environ',{'ATTICUS_ASK':str(self.root)}), patch.object(atticus,'ask_user',return_value='n'):
            self.assertIn('not confirmed',atticus.confirm_workflow('fixture').lower())
        self.assertFalse(atticus.workflow_trusted(atticus.skills()['fixture']))
        def change(*args):
            path.write_text(json.dumps({'fixture':{**row,'cmds':[atticus.SHOW+' Other']}})); return 'y'
        with patch.dict('os.environ',{'ATTICUS_ASK':str(self.root)}), patch.object(atticus,'ask_user',side_effect=change):
            self.assertIn('changed',atticus.confirm_workflow('fixture').lower())
        self.assertFalse(atticus.workflow_trusted(atticus.skills()['fixture']))

if __name__=='__main__':unittest.main()
