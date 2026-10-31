import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('approval_client', ROOT / 'approval_client.py')
client_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(client_module)


class FakePipe:
    def __init__(self, scenario='accept'):
        self.request = None; self.scenario = scenario
    def write(self, raw): self.request = json.loads(raw)
    def flush(self): pass
    def readline(self, limit):
        q = self.request
        if self.scenario == 'disconnect': return b''
        response = {'session':q['session'], 'nonce':q['nonce'], 'digest':q['digest'], 'expiresUnixMs':11000, 'decision':'accept'}
        if self.scenario == 'nonce': response['nonce'] = 'stale'
        if self.scenario == 'session': response['session'] = 'wrong'
        if self.scenario == 'digest': response['digest'] = 'wrong'
        if self.scenario == 'expired': response['expiresUnixMs'] = 10000
        if self.scenario == 'denied': response['decision'] = 'decline'
        if self.scenario == 'junk': return b'{bad}\n'
        return (json.dumps(response) + '\n').encode()


class ApprovalClientTests(unittest.TestCase):
    def make(self, scenario):
        pipe = FakePipe(scenario)
        return client_module.ApprovalClient(pipe, pipe, 'native-session', 'Task', '/project', 'workspace-write; network-disabled', clock=lambda:10), pipe

    def test_accept_matches_request_and_complete_payload(self):
        client, pipe = self.make('accept')
        operation = {'method':'item/fileChange/requestApproval', 'params':{'threadId':'t','turnId':'u','path':'file.txt'}}
        self.assertEqual(client.decide(operation), 'accept')
        self.assertEqual(json.loads(pipe.request['payload']), operation)
        self.assertEqual((pipe.request['task'],pipe.request['project'],pipe.request['scope']), ('Task','/project','workspace-write; network-disabled'))

    def test_unmatched_expired_and_disconnected_fail_closed(self):
        for scenario in ('nonce','session','digest','expired','disconnect','junk'):
            with self.subTest(scenario=scenario):
                client,_ = self.make(scenario)
                self.assertEqual(client.decide({'method':'fixture'}),'cancel')

    def test_decline_and_closed_do_not_grant(self):
        client,_ = self.make('denied'); self.assertEqual(client.decide({'a':1}), 'decline')
        client.close(); self.assertEqual(client.decide({'a':2}), 'cancel')

    def test_long_request_fails_without_pipe_write(self):
        client, pipe = self.make('accept')
        self.assertEqual(client.decide({'data':'x'*9000}), 'cancel')
        self.assertIsNone(pipe.request)

    def test_unique_nonces_for_separate_requests(self):
        client, pipe = self.make('accept')
        self.assertEqual(client.decide({'x':1}), 'accept'); first=pipe.request['nonce']
        self.assertEqual(client.decide({'x':1}), 'accept'); self.assertNotEqual(first,pipe.request['nonce'])

    def test_host_context_must_match_requested_task_and_project(self):
        import io
        hello = {'session':'s', 'task':'task', 'project':'/project', 'scope':'workspace-write; network-disabled'}
        def stream(): return io.BytesIO((json.dumps(hello) + '\n').encode())
        self.assertEqual(client_module.ApprovalClient.from_host(stream(), io.BytesIO(), 'task', '/project').task, 'task')
        for task, project in [('other','/project'), ('task','/other')]:
            with self.subTest(task=task, project=project), self.assertRaises(client_module.ApprovalError):
                client_module.ApprovalClient.from_host(stream(), io.BytesIO(), task, project)

    def test_host_context_timeout_is_fail_closed(self):
        import io, threading
        stopped = threading.Event()
        class WaitingReader:
            def readline(self, limit): stopped.wait(.1); return b''
        try:
            with self.assertRaises(client_module.ApprovalError):
                client_module.ApprovalClient.from_host(WaitingReader(), io.BytesIO(), 'task', '/project', timeout=.01)
        finally: stopped.set()

    def test_rejects_unsupported_or_unbound_codex_requests(self):
        client, pipe = self.make('accept')
        for request in ({'method':'unknown', 'params':{}}, {'method':'item/fileChange/requestApproval','params':{}}, {'method':'item/commandExecution/requestApproval','params':{'threadId':'t'}}):
            self.assertEqual(client.codex_handler(request), 'cancel')
        self.assertIsNone(pipe.request)

    def test_fake_codex_server_uses_bound_native_decision(self):
        import os
        from unittest.mock import patch
        base = ROOT.parent
        sys.path.insert(0, str(base)); sys.path.insert(0, str(base / 'tests'))
        from codex_provider import CodexProvider
        from test_atlas_codex_provider import fake_spawn
        client, pipe = self.make('accept')
        with tempfile.TemporaryDirectory() as project, patch.dict(os.environ, {'FIXTURE_WINDOWS':'1', 'FIXTURE_REQUEST':'item/commandExecution/requestApproval', 'FIXTURE_ACCEPT':'1'}):
            result = CodexProvider(popen=fake_spawn, platform_profile='windows', approval_handler=client.codex_handler).run(project, 'fixture task')
        self.assertEqual(result['status'], 'done')
        self.assertEqual(json.loads(pipe.request['payload'])['params']['turnId'], 'fixture-turn')

    def test_timeout_fails_closed_and_closes_client(self):
        import threading
        blocker=threading.Event()
        class WaitingPipe(FakePipe):
            def readline(self, limit): blocker.wait(.1); return b''
        p=WaitingPipe(); c=client_module.ApprovalClient(p,p,'s','task','/project','workspace-write; network-disabled',clock=lambda:10,timeout=.01)
        self.assertEqual(c.decide({'x':1}),'cancel'); self.assertTrue(c.closed); blocker.set()

if __name__ == '__main__': unittest.main()
