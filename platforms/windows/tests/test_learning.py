"""Learned commands, saved procedures, history, Try again and failure reports (ported from atticus-mac).
Scratch storage only: no Claude calls, no real apps, no network."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import atticus


class LearningTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)
        for p in (patch.object(atticus, 'DIR', root.name), patch.object(atticus, 'SKILLS', str(self.root / 'skills.json')),
                  patch.object(atticus, 'LAST', str(self.root / 'last_app')), patch.object(atticus, 'pref', side_effect=lambda k, d: d),
                  patch.dict(os.environ, {'ATTICUS_LIVE': ''})):
            p.start()
            self.addCleanup(p.stop)

    def test_saved_alias_never_creates_or_executes_a_command(self):
        with patch.object(atticus, 'open_app') as opened, patch.object(atticus.subprocess, 'run') as run:
            self.assertIsNone(atticus.fast('When I say writing time, open Notepad'))
            self.assertIsNone(atticus.replay('writing time'))
            opened.assert_not_called(); run.assert_not_called()
        self.assertEqual(atticus.skills(), {})

    def test_learned_task_is_never_replayed(self):
        atticus.learn('put notepad on the left', [f'{atticus.PLACE} Notepad left current'], 'Notepad is on the left.')
        with patch.object(atticus.subprocess, 'run') as run:
            self.assertIsNone(atticus.replay('put notepad on the left', ('Notepad', 'Paint')))
            run.assert_not_called()

    def test_a_replay_step_that_says_it_failed_hands_over_to_the_ai(self):
        atticus.save_skills({'open budget': {'cmds': [f'{atticus.SHOW} budget.xlsx'], 'reply': 'Opened.', 'mine': True}})
        bad = unittest.mock.Mock(returncode=0, stdout='could not open budget.xlsx', stderr='')
        with patch.object(atticus.subprocess, 'run', return_value=bad), patch.object(atticus, 'shim_env', return_value={}):
            self.assertIsNone(atticus.replay('open budget'))

    def test_shortcuts_keep_actions_drop_looking_around_and_refuse_what_needs_the_ai(self):
        sc = atticus.shortcut_commands
        self.assertEqual(sc('x', [f'{atticus.LOOK}; {atticus.SHOW} Spotify; {atticus.PLAY} "jazz"']), [f'{atticus.SHOW} Spotify', f"{atticus.PLAY} jazz"])
        self.assertEqual(sc('x', [f'{atticus.PLACE} Chrome left current', f'{atticus.PLACE} Code right current']),
                         [f'{atticus.PLACE} Chrome left current + Code right current'])   # back-to-back moves go at once
        self.assertIsNone(sc('x', [f'{atticus.CLIP} | grep x']))   # pipes need the AI
        self.assertIsNone(sc('x', [f'{atticus.WINDOWS} Chrome && {atticus.PLACE} Chrome left current']))   # a check it acts on can't be dropped
        self.assertEqual(sc('x', [f'{atticus.PLACE} Chrome left current && {atticus.LOOK}']), [f'{atticus.PLACE} Chrome left current'])   # a check after the act can

    def test_unused_learned_tasks_expire_but_the_users_own_stay(self):
        old = time.strftime('%Y-%m-%d', time.localtime(time.time() - 40 * 86400))
        atticus.save_skills({'a': {'cmds': ['x'], 'reply': 'A', 'at': old}, 'b': {'cmds': ['x'], 'reply': 'B', 'at': old, 'mine': True},
                             'c': {'cmds': ['x'], 'reply': 'C', 'at': time.strftime('%Y-%m-%d')}})
        self.assertEqual(set(atticus.skills()), {'b', 'c'})

    def test_moves_in_any_word_order(self):
        with patch.object(atticus, 'app_named', side_effect=lambda w: {'chrome': 'Google Chrome', 'notepad': 'Notepad'}.get(w)):
            self.assertEqual(atticus.move_target('full screen chrome on my big screen'), ('Google Chrome', 'full', 'monitor'))
            self.assertEqual(atticus.move_target('move chrome to the external display and maximize it'), None)   # "it" left over: the AI decides
            self.assertEqual(atticus.move_target('put chrome on the left of the laptop'), ('Google Chrome', 'left', 'laptop'))
            self.assertIsNone(atticus.move_target("what's on my monitor"))
            with patch.object(atticus, 'place', return_value='Google Chrome window -> left of DELL') as place, patch.object(atticus, 'proc_of', side_effect=lambda a: a):
                self.assertEqual(atticus.fast('Chrome left, Notepad right'), 'Google Chrome: left. Notepad: right.')
            self.assertEqual(place.call_count, 2)
            self.assertEqual(atticus.fast.cmds, [f"{atticus.PLACE} 'Google Chrome' left current + Notepad right current"])

    def test_procedures_are_saved_from_verified_tasks_and_follow_the_words(self):
        reply, saved = atticus.remember_workflow('make a calendar event',
            'Created it. [workflow create calendar event | Open Outlook calendar, fill the form, save; check the event shows.]', True, ['x'])
        self.assertEqual((reply, saved), ('Created it.', True))
        self.assertIn('fill the form', atticus.workflows('Can you create a new calendar event tomorrow?'))
        self.assertEqual(atticus.workflows('open calendar'), '')
        for reply, ok, cmds in [('Done. [workflow a b | c]', False, ['x']), ('Could not do it. [workflow a b | c]', True, ['x']), ('Done. [workflow a b | c]', True, [])]:
            self.assertFalse(atticus.remember_workflow('a b', reply, ok, cmds)[1])
        self.assertIsNone(atticus.fast('remember how to create a calendar event'))
        atticus.unlearn('make a new calendar event')   # "no, that's wrong" drops it, whatever the wording
        self.assertEqual(atticus.workflows('create calendar event'), '')

    def test_ai_replay_tags_are_only_saved_when_safe(self):
        atticus.remember_workflow('open my music', f'Playing. [workflow open my music | Play the playlist.] [replay {atticus.PLAY} "focus"]', True, ['x'])
        self.assertEqual(atticus.skills()['open my music']['cmds'], [f'{atticus.PLAY} "focus"'])
        for bad in ['rm -rf ~/x', f'{atticus.UI} click B3', f'{atticus.TRASH} ~/x']:
            atticus.remember_workflow('do thing', f'Done. [workflow do thing | a] [replay {bad}]', True, ['x'])
            self.assertNotIn('do thing', atticus.skills())

    def test_history_finds_past_asks_by_words_or_date(self):
        with open(self.root / 'log.jsonl', 'w') as f:
            f.write(json.dumps({'at': '2026-10-10 09:00:00', 'task': 'find the lamp link', 'reply': 'https://example.com/lamp'}) + '\n')
            f.write('not json\n' + json.dumps({'at': '2026-10-11 10:00:00', 'task': 'weather', 'reply': 'Sunny.'}) + '\n')
        self.assertIn('example.com/lamp', atticus.history('that lamp link'))
        self.assertIn('Sunny', atticus.history('2026-10-11'))
        self.assertEqual(atticus.history('zebra'), 'Nothing matches.')

    def test_all_rules_go_while_they_fit_and_earlier_answers_keep_more(self):
        mem = self.root / 'memory.md'
        with patch.object(atticus, 'MEMORY', str(mem)):
            mem.write_text('When I say dad, use the contact Papa.\n' + 'Keep replies short and friendly please.\n' * 40)
            self.assertIn('dad', atticus.relevant_rules('email Papa'))
        text = atticus.earlier_chat([{'q': f'q{i}', 'a': str(i) * 2000} for i in range(3)])
        self.assertIn('A: ' + '0' * 1000 + '\n', text)
        self.assertIn('A: ' + '2' * 2000 + '\n', text)

    def test_tool_help_never_runs_gui_apps_or_windows_own_tools(self):
        if sys.platform != 'win32':
            self.skipTest('Windows executables')
        windir = os.environ.get('SystemRoot', r'C:\Windows')
        self.assertFalse(atticus.console_exe(os.path.join(windir, 'notepad.exe')))   # GUI: --help would open it
        self.assertTrue(atticus.console_exe(os.path.join(windir, 'System32', 'where.exe')))
        # Resolve explicitly to Windows' tools: Git's `where` can precede
        # System32 on hosted runners, and is a different executable.
        paths = {'notepad': os.path.join(windir, 'notepad.exe'),
                 'where': os.path.join(windir, 'System32', 'where.exe')}
        with patch.object(atticus.shutil, 'which', side_effect=lambda name: paths.get(name)), \
             patch.object(atticus.subprocess, 'run') as run:
            self.assertEqual(atticus.tool_help('open notepad and run where'), '')
        run.assert_not_called()

    def test_failure_reporting_remains_disabled_with_legacy_settings(self):
        with patch.object(atticus, 'posthog') as send, patch.object(atticus, 'POSTHOG_KEY', 'legacy-key'), \
             patch.object(atticus, 'pref', return_value=True):
            atticus.report('private request', 'failed', ['private step'], 1, 'error')
        send.assert_not_called()

    def test_unknown_request_does_not_offer_model_retry(self):
        with patch.multiple(atticus, fast=lambda _: None, wait_commit=lambda: True), \
             patch.object(atticus, 'retry_offer') as offer, patch.object(atticus, 'start_claude') as start, \
             patch.object(atticus, 'run') as run, patch('sys.argv', ['atticus.py', 'Do fixture']), \
             patch('sys.stdout', io.StringIO()) as output:
            atticus.main()
        offer.assert_not_called(); start.assert_not_called(); run.assert_not_called()
        self.assertIn('unavailable', output.getvalue().lower())


if __name__ == '__main__':
    unittest.main()
