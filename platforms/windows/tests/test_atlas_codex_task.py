import os
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import atlas_codex_task
from codex_provider import CodexProvider, ProviderError
from test_atlas_codex_provider import fake_spawn


class WindowsCodexTaskTests(unittest.TestCase):
    def test_default_gate_cannot_launch(self):
        factory = Mock()
        result = atlas_codex_task.run_task('hello', '/tmp', lambda _: None, factory)
        self.assertEqual(result['status'], 'unavailable')
        factory.assert_not_called()

    def test_no_workspace_or_missing_cli(self):
        factory = Mock()
        self.assertEqual(atlas_codex_task.run_task('hello', 'relative', lambda _:None, factory, verified=True)['status'], 'failed')
        with tempfile.TemporaryDirectory() as d, patch('atlas_codex_task.shutil.which', return_value=None):
            self.assertEqual(atlas_codex_task.run_task('hello', d, lambda _:None, factory, verified=True)['status'], 'failed')
        factory.assert_not_called()

    def test_windows_profile_streams_and_denies_approval(self):
        def factory(**kwargs): return CodexProvider(popen=fake_spawn, **kwargs)
        events = []
        with tempfile.TemporaryDirectory() as d, patch('atlas_codex_task.shutil.which', return_value='codex'), patch.dict(os.environ, {'FIXTURE_WINDOWS':'1'}):
            result = atlas_codex_task.run_task('fixture task', d, events.append, factory, verified=True)
            self.assertEqual(result['status'], 'done')
            self.assertIn({'type':'text', 'text':'Finished fixture.'}, events)
            with patch.dict(os.environ, {'FIXTURE_REQUEST':'item/commandExecution/requestApproval'}):
                events.clear()
                result = atlas_codex_task.run_task('fixture task', d, events.append, factory, verified=True)
                self.assertEqual(result['status'], 'failed')
                self.assertTrue(any(e.get('type') == 'approval_denied' for e in events))

    def test_windows_profile_rejects_unconfirmed_permission(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_WINDOWS':'1', 'FIXTURE_WRONG_PROFILE':'1'}):
            events = []
            with self.assertRaisesRegex(ProviderError, 'scope'):
                CodexProvider(popen=fake_spawn, platform_profile='windows', emit=events.append).run(d, 'fixture')
            self.assertFalse(any(e.get('type') == 'turn' for e in events))

    def test_windows_cancel_and_resume_are_not_success_on_race(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_WINDOWS':'1'}):
            provider = CodexProvider(popen=fake_spawn, platform_profile='windows')
            provider.emit = lambda e: provider.interrupt() if e.get('type') == 'turn' else None
            result = provider.run(d, 'fixture', 'fixture-thread')
            self.assertEqual(result['status'], 'stopped')
            self.assertIn('partial changes', result['result'])

    def test_interrupt_file_waits_for_delayed_terminal_ack(self):
        events = []
        with tempfile.TemporaryDirectory() as d, patch('atlas_codex_task.shutil.which', return_value='codex'), patch.dict(os.environ, {'FIXTURE_WINDOWS':'1', 'FIXTURE_HANG':'1', 'FIXTURE_INTERRUPT_DELAY':'1'}):
            cancel = os.path.join(d, 'cancel')
            def emit(event):
                events.append(event)
                if event.get('type') == 'turn': open(cancel, 'w').close()
            def factory(**kwargs): return CodexProvider(popen=fake_spawn, **kwargs)
            result = atlas_codex_task.run_task('fixture', d, emit, factory, verified=True, cancel_path=cancel)
            self.assertEqual(result['status'], 'stopped')
            self.assertEqual(result.get('server_status'), 'interrupted')
            self.assertIn('partial changes', result['result'])

    def test_interrupt_without_ack_has_bounded_unknown_outcome(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_WINDOWS':'1', 'FIXTURE_HANG':'1', 'FIXTURE_INTERRUPT_NO_ACK':'1'}):
            provider = CodexProvider(popen=fake_spawn, platform_profile='windows')
            provider.emit = lambda e: provider.interrupt() if e.get('type') == 'turn' else None
            start = time.monotonic()
            result = provider.run(d, 'fixture')
            self.assertEqual(result['status'], 'stopped')
            self.assertIn('not confirmed', result['result'])
            self.assertLess(time.monotonic() - start, 8)

    def test_interrupt_completion_race_and_disconnect_never_claim_success(self):
        for flag in ('FIXTURE_INTERRUPT_RACE', 'FIXTURE_INTERRUPT_DISCONNECT'):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_WINDOWS':'1','FIXTURE_HANG':'1',flag:'1'}):
                provider = CodexProvider(popen=fake_spawn, platform_profile='windows')
                provider.emit = lambda e: provider.interrupt() if e.get('type') == 'turn' else None
                result = provider.run(d, 'fixture')
                self.assertEqual(result['status'], 'stopped')
                if flag.endswith('RACE'): self.assertEqual(result['server_status'], 'completed')
                else: self.assertIn('not confirmed', result['result'])

if __name__ == '__main__': unittest.main()
