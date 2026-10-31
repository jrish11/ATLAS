import io
import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import atticus


class PreviewBoundaryTests(unittest.TestCase):
    def test_provider_launcher_never_starts_for_legacy_flags(self):
        for settings in ({'safe':False, 'provider':'claude'}, {'safe':True, 'provider':'codex'}):
            with self.subTest(settings=settings), patch.object(atticus, 'pref', side_effect=lambda k,d:settings.get(k,d)), \
                 patch.object(atticus.subprocess, 'Popen') as spawn, \
                 patch.dict(os.environ, {'ATTICUS_ASK':'legacy', 'ATTICUS_POSTHOG_KEY':'legacy'}):
                self.assertIsNone(atticus.start_claude({'legacy': {}}, 'sonnet'))
                spawn.assert_not_called()

    def test_saved_shell_never_replays_regardless_of_safety_setting(self):
        with patch.object(atticus, 'skills', return_value={'open work': {'cmds':['arbitrary shell'], 'reply':'done'}}), \
             patch.object(atticus.subprocess, 'run') as spawn, patch.object(atticus, 'pref', return_value=False):
            self.assertIsNone(atticus.replay('open work'))
            self.assertIsNone(atticus.fast('when I say work, open app'))
            spawn.assert_not_called()

    def test_unknown_confirmed_request_never_starts_provider_or_screen_capture(self):
        for provider in ('claude', 'codex'):
            with self.subTest(provider=provider), patch('sys.argv', ['atticus.py','--wait']), \
                 patch('sys.stdin', io.StringIO('Notepad\tchange my files\n')), \
                 patch.object(atticus, 'pref', side_effect=lambda k,d: provider if k=='provider' else d), \
                 patch.object(atticus, 'wait_commit', return_value=True), patch.object(atticus, 'fast', return_value=None), \
                 patch.object(atticus, 'start_claude') as start, patch.object(atticus, 'run') as run, \
                 patch.object(atticus, 'look') as look, patch.object(atticus, 'say') as say, patch.object(atticus.signal, 'signal'):
                atticus.main()
                start.assert_not_called(); run.assert_not_called(); look.assert_not_called()
                self.assertIn('unavailable', say.call_args.args[1].lower())

    def test_unsafe_helpers_and_aliases_are_blocked(self):
        for option in ('--gate', '--set', '--watch', '--watching', '--shortcut', '--type', '--ui', '--keys', '--trash', '--int', '--look', '--codex-account'):
            with self.subTest(option=option), patch('sys.argv', ['atticus.py', option, 'anything']), \
                 patch.object(atticus.subprocess, 'Popen') as spawn, patch.object(atticus.subprocess, 'run') as run, \
                 patch('sys.stdout', new_callable=io.StringIO) as output:
                atticus.main()
                self.assertIn('unavailable', output.getvalue().lower())
                spawn.assert_not_called(); run.assert_not_called()

    def test_preseeded_legacy_approval_files_cannot_grant_access(self):
        with tempfile.TemporaryDirectory() as root:
            from pathlib import Path
            approval = Path(root) / 'a'; approval.write_text('y')
            with patch.dict(os.environ, {'ATTICUS_ASK': root}), patch('sys.argv', ['atticus.py', '--gate']), \
                 patch.object(atticus, 'gate') as gate, patch('sys.stdout', new_callable=io.StringIO) as output:
                atticus.main()
                gate.assert_not_called()
                self.assertIn('unavailable', output.getvalue().lower())
                self.assertEqual(approval.read_text(), 'y')

    def test_direct_model_runner_cannot_write_to_supplied_process(self):
        process = Mock()
        result, _, _ = atticus.run('change files', process)
        self.assertIn('unavailable', result)
        process.stdin.write.assert_not_called(); process.wait.assert_not_called()

    def test_partial_speech_cannot_dispatch_fast_action(self):
        with patch.dict(os.environ, {'ATTICUS_LIVE':'1'}), patch('sys.argv', ['atticus.py','--fast','open Notepad']), \
             patch.object(atticus, 'fast') as action:
            with self.assertRaises(SystemExit): atticus.main()
            action.assert_not_called()

if __name__ == '__main__': unittest.main()
