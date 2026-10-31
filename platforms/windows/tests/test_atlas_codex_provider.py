import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from codex_provider import CodexProvider, ProviderError

SERVER = str(Path(__file__).with_name('codex_fake_server.py'))

def fake_spawn(args, **kwargs):
    env = dict(kwargs.get('env', os.environ))
    if any(str(arg).startswith('skills.config=') for arg in args): env['FIXTURE_OVERRIDE']='1'
    if any(str(arg)=='mcp_servers.fixture.enabled=false' for arg in args): env['FIXTURE_MCP_DISABLED']='1'
    if any(str(arg)=='apps.example.enabled=false' for arg in args): env['FIXTURE_APP_DISABLED']='1'
    profile = next((str(arg).split('=',1)[1] for arg in args if str(arg).startswith('default_permissions=')), '"missing"')
    env['FIXTURE_PROFILE'] = __import__('json').loads(profile)
    kwargs['env'] = env
    return subprocess.Popen([sys.executable, SERVER], **kwargs)

class CodexProviderTests(unittest.TestCase):
    def test_thread_stream_and_completion(self):
        events = []
        with tempfile.TemporaryDirectory() as d:
            provider = CodexProvider(popen=fake_spawn, emit=events.append)
            result = provider.run(d, 'fixture task')
        self.assertEqual(result, {'status':'done', 'result':'Finished fixture.'})
        self.assertIn({'type':'thread', 'id':'fixture-thread'}, events)
        self.assertIn({'type':'text', 'text':'Finished fixture.'}, events)

    def test_early_and_late_events_are_bound_to_confirmed_turn(self):
        events = []
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_EARLY':'1','FIXTURE_LATE':'1'}):
            result=CodexProvider(popen=fake_spawn, emit=events.append).run(d,'fixture task')
        self.assertEqual(result, {'status':'done','result':'Early fixture. Finished fixture.'})
        self.assertEqual([e['id'] for e in events if e['type']=='turn'], ['fixture-turn'])

    def test_approval_before_turn_confirmation_fails_closed(self):
        from unittest.mock import Mock
        handler=Mock(return_value='accept')
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_EARLY_APPROVAL':'1'}):
            result=CodexProvider(popen=fake_spawn,approval_handler=handler).run(d,'fixture task')
        self.assertEqual(result['status'],'failed');handler.assert_not_called()

    def test_malformed_and_stale_events_never_change_active_turn(self):
        from unittest.mock import Mock
        handler=Mock(return_value='accept'); provider=CodexProvider(approval_handler=handler)
        provider.thread_id='thread'; provider.turn_id='current'; provider._send=Mock()
        for params in (None, 'bad', [], {'threadId':'thread','turn':'bad'}, {'threadId':'thread','turn':{'id':'old','status':'completed'}}, {'threadId':'other','turn':{'id':'current','status':'completed'}}):
            for method in ('turn/started','turn/completed','item/agentMessage/delta'):
                self.assertIsNone(provider._handle({'method':method,'params':params}))
        self.assertEqual(provider.turn_id,'current');self.assertIsNone(provider._completed);self.assertEqual(provider.text,'')
        provider._handle({'id':'bad','method':'item/commandExecution/requestApproval','params':'bad'})
        handler.assert_not_called(); self.assertEqual(provider._send.call_args.args[0]['result']['decision'],'cancel')

    def test_late_or_duplicate_messages_cannot_revive_completed_turn(self):
        from unittest.mock import Mock
        handler=Mock(return_value='accept'); provider=CodexProvider(approval_handler=handler)
        provider.thread_id='thread'; provider.turn_id='current'; provider._send=Mock()
        event={'method':'turn/completed','params':{'threadId':'thread','turn':{'id':'current','status':'completed'}}}
        self.assertIsNotNone(provider._handle(event)); self.assertIsNone(provider._handle(event))
        provider._handle({'method':'item/agentMessage/delta','params':{'threadId':'thread','turnId':'current','delta':'late'}})
        provider._handle({'id':'late','method':'item/commandExecution/requestApproval','params':{'threadId':'thread','turnId':'current'}})
        handler.assert_not_called();self.assertEqual(provider.text,'');self.assertEqual(provider._send.call_args.args[0]['result']['decision'],'cancel')

    def test_cancellation_is_not_reported_as_success_if_completion_races(self):
        provider = CodexProvider(popen=fake_spawn)
        provider.emit = lambda event: provider.interrupt() if event.get('type') == 'turn' else None
        with tempfile.TemporaryDirectory() as d:
            result=provider.run(d,'fixture task')
        self.assertEqual(result['status'],'stopped')
        self.assertIn('partial changes',result['result'])
        self.assertIn(result.get('server_status'),('completed','interrupted','failed'))
        if result['server_status']=='completed':self.assertIn('reported the turn completed',result['result'])

    def test_invalid_response_is_rejected_and_boolean_id_is_not_correlated(self):
        from unittest.mock import Mock
        provider=CodexProvider(); provider._send=Mock()
        provider._messages.put({'id':True,'result':{'bad':'boolean id'}})
        provider._messages.put({'id':1,'result':'invalid'})
        with self.assertRaisesRegex(ProviderError,'invalid'):
            provider._request('fixture',{})

    def test_cancelled_turn_never_approves_late_request(self):
        from unittest.mock import Mock
        handler=Mock(return_value='accept'); provider=CodexProvider(approval_handler=handler)
        provider.thread_id='thread';provider.turn_id='current';provider._stopped=True;provider._send=Mock()
        provider._handle({'id':'request','method':'item/fileChange/requestApproval','params':{'threadId':'thread','turnId':'current'}})
        handler.assert_not_called();self.assertEqual(provider._send.call_args.args[0]['result']['decision'],'cancel')

    def test_failed_turn_returns_safe_model_category_not_raw_diagnostic(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_TURN_ERROR':'1'}):
            result=CodexProvider(popen=fake_spawn).run(d,'fixture task')
        self.assertEqual(result['status'],'failed');self.assertEqual(result['error_category'],'model_unavailable_account')
        self.assertIn('not supported',result['result'])
        for secret in ('fixture-secret','Bearer','/private/fixture'):self.assertNotIn(secret,str(result))

    def test_safe_error_categories_never_echo_unknown_input(self):
        from codex_provider import classify_turn_error
        cases=[({'codexErrorInfo':'usageLimitExceeded','message':'fixture-secret'},'usage_limit'),
               ({'codexErrorInfo':{'httpConnectionFailed':{'httpStatusCode':503}},'message':'fixture-secret'},'connection'),
               ({'codexErrorInfo':'other','message':'fixture-secret /private/path'},'unknown'),
               ({'codexErrorInfo':['bad'],'message':None},'unknown')]
        for error,expected in cases:
            with self.subTest(expected=expected):
                category,message=classify_turn_error(error);self.assertEqual(category,expected)
                self.assertNotIn('fixture-secret',message);self.assertNotIn('/private/path',message)

    def test_cancellation_while_approval_waits_cannot_accept(self):
        from unittest.mock import Mock
        provider=CodexProvider();provider.thread_id='thread';provider.turn_id='turn';provider._send=Mock()
        def answer(_):
            provider.interrupt();return 'accept'
        provider.approval_handler=answer
        provider._handle({'id':'approval','method':'item/fileChange/requestApproval','params':{'threadId':'thread','turnId':'turn'}})
        self.assertEqual(provider._send.call_args.args[0]['result']['decision'],'cancel')
        self.assertTrue(provider.approval_denied)

    def test_protected_scope_and_symlink_overlap_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d,'home');home.mkdir();state=home/'.codex';state.mkdir();project=home/'project';project.mkdir()
            link=Path(d,'state-link');link.symlink_to(state,target_is_directory=True)
            with patch.dict(os.environ,{'HOME':str(home),'CODEX_HOME':str(state),'ATTICUS_DIR':str(home/'.config/atticus-personal-dev')}):
                self.assertEqual(CodexProvider.validate_scope(str(project)),os.path.realpath(project))
                for path in (home,Path(d),state,link):
                    with self.subTest(path=str(path)),self.assertRaises(ProviderError):CodexProvider.validate_scope(str(path))

    def test_unresponsive_turn_has_a_finite_unconfirmed_timeout(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'FIXTURE_HANG':'1'}):
            result=CodexProvider(popen=fake_spawn,turn_timeout=1).run(d,'fixture')
        self.assertEqual(result['error_category'],'timeout');self.assertIn('not confirmed',result['result'])

    def test_resume_and_deny_approval(self):
        events = []
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_APPROVAL':'1'}):
            provider = CodexProvider(popen=fake_spawn, emit=events.append)
            result = provider.run(d, 'fixture task', 'fixture-thread')
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any(e['type'] == 'approval_denied' for e in events))

    def test_all_server_requests_are_denied_and_correlated(self):
        methods = ('item/commandExecution/requestApproval', 'item/fileChange/requestApproval',
                   'item/permissions/requestApproval', 'item/tool/requestUserInput', 'unexpected/tool/request')
        for method in methods:
            with self.subTest(method=method), tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_REQUEST':method}):
                events = []
                result = CodexProvider(popen=fake_spawn, emit=events.append).run(d, 'fixture task')
                self.assertEqual(result['status'], 'failed')
                self.assertTrue(any(e.get('type') == 'approval_denied' and e.get('method') == method for e in events))

    def test_explicit_approval_is_correlated_and_never_auto_accepted(self):
        from unittest.mock import Mock
        handler=Mock(return_value='accept')
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_REQUEST':'item/commandExecution/requestApproval','FIXTURE_ACCEPT':'1'}):
            result=CodexProvider(popen=fake_spawn, approval_handler=handler).run(d,'task')
        self.assertEqual(result['status'],'done')
        self.assertEqual(handler.call_args.args[0]['id'],'approval-1')
        self.assertEqual(handler.call_args.args[0]['params']['turnId'],'fixture-turn')
        handler.reset_mock()
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_REQUEST':'item/commandExecution/requestApproval','FIXTURE_WRONG_APPROVAL_THREAD':'1'}):
            result=CodexProvider(popen=fake_spawn, approval_handler=handler).run(d,'task')
        self.assertEqual(result['status'],'failed'); handler.assert_not_called()

    def test_inherited_hooks_fail_before_thread_start(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_HOOKS':'1'}):
            events = []
            with self.assertRaisesRegex(ProviderError, 'not approved'):
                CodexProvider(popen=fake_spawn, emit=events.append).run(d, 'fixture task')
            self.assertFalse(any(e.get('type') == 'thread' for e in events))

    def test_inherited_skills_are_disabled_then_rechecked(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_SKILLS':'1'}):
            self.assertEqual(CodexProvider(popen=fake_spawn).run(d, 'fixture task')['status'], 'done')
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_SKILLS':'1','FIXTURE_SKILLS_STUCK':'1'}):
            with self.assertRaisesRegex(ProviderError, 'remain enabled'):
                CodexProvider(popen=fake_spawn).run(d, 'fixture task')

    def test_effective_config_or_scope_mismatch_stops_before_turn(self):
        for env, message in (({'FIXTURE_UNSAFE_CONFIG':'1'}, 'safety settings'), ({'FIXTURE_APP_OVERRIDE':'1'}, 'app restrictions'), ({'FIXTURE_WRONG_PROFILE':'1'}, 'sandbox and approval scope')):
            with self.subTest(env=env), tempfile.TemporaryDirectory() as d, patch.dict(os.environ, env):
                events=[]
                with self.assertRaisesRegex(ProviderError, message):
                    CodexProvider(popen=fake_spawn, emit=events.append).run(d, 'fixture task')
                self.assertFalse(any(e.get('type') == 'turn' for e in events))

    def test_inherited_enabled_apps_are_disabled_in_child(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_APP_ENABLED':'1'}):
            self.assertEqual(CodexProvider(popen=fake_spawn).run(d,'fixture task')['status'],'done')

    def test_inherited_mcp_servers_are_disabled_and_inventory_checked(self):
        events = []
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_MCP':'1'}):
            result=CodexProvider(popen=fake_spawn, emit=events.append).run(d,'fixture task')
        self.assertEqual(result['status'],'done')
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'FIXTURE_MCP':'1','FIXTURE_MCP_TOOL':'1'}):
            events=[]
            with self.assertRaisesRegex(ProviderError, 'inventory'):
                CodexProvider(popen=fake_spawn,emit=events.append).run(d,'fixture task')
            self.assertFalse(any(e['type']=='thread' for e in events))

    def test_mcp_fail_closed_on_ignored_override_unknown_key_or_incomplete_inventory(self):
        cases=[({'FIXTURE_MCP':'1','FIXTURE_MCP_IGNORED':'1'},'not disabled'),
               ({'FIXTURE_MCP_UNSAFE':'1'},'names'),
               ({'FIXTURE_MCP':'1','FIXTURE_MCP_ERROR':'1'},'inventory'),
               ({'FIXTURE_MCP':'1','FIXTURE_MCP_CURSOR':'1'},'inventory')]
        for environment,reason in cases:
            with self.subTest(environment=environment),tempfile.TemporaryDirectory() as d, patch.dict(os.environ,environment):
                events=[]
                with self.assertRaisesRegex(ProviderError,reason):CodexProvider(popen=fake_spawn,emit=events.append).run(d,'fixture')
                self.assertFalse(any(e.get('type')=='thread' for e in events))

    def test_existing_login_requires_account_and_confirmed_single_default_model(self):
        cases=[({'FIXTURE_WRONG_ACCOUNT':'1'},'ChatGPT account'),({'FIXTURE_NO_DEFAULT':'1'},'default model'),
               ({'FIXTURE_DUPLICATE_DEFAULT':'1'},'default model'),({'FIXTURE_WRONG_MODEL':'1'},'default model')]
        for environment,reason in cases:
            with self.subTest(environment=environment),tempfile.TemporaryDirectory() as d,patch.dict(os.environ,environment):
                events=[]
                with self.assertRaisesRegex(ProviderError,reason):CodexProvider(popen=fake_spawn,emit=events.append).run(d,'fixture')
                self.assertFalse(any(e.get('type')=='turn' for e in events))

    def test_auth_mode_selects_key_only_when_explicitly_requested(self):
        from unittest.mock import Mock
        calls=[]
        def spawn(args, **kwargs):
            calls.append((args, dict(kwargs['env'])))
            return fake_spawn(args, **kwargs)
        resolver=Mock(return_value='fixture-openai-key')
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'OPENAI_API_KEY':'inherited-key'}):
            self.assertEqual(CodexProvider(popen=spawn, api_key_resolver=resolver).run(d,'task')['status'],'done')
            self.assertNotIn('OPENAI_API_KEY',calls[-1][1]); resolver.assert_not_called()
            self.assertEqual(CodexProvider(popen=spawn, auth_mode='api_key', api_key_resolver=resolver).run(d,'task')['status'],'done')
            self.assertEqual(calls[-1][1]['OPENAI_API_KEY'],'fixture-openai-key')
            self.assertNotIn('fixture-openai-key',str(calls[-1][0]))
            resolver.assert_called_once_with()

    def test_replaced_project_during_preflight_never_dispatches_turn(self):
        for trigger in ('model/list','thread/start'):
            with self.subTest(trigger=trigger), tempfile.TemporaryDirectory(dir='/tmp') as d:
                root=Path(d).resolve()/'project';root.mkdir();sent=[]
                class ReplaceDuringPreflight(CodexProvider):
                    def _send(self,payload):
                        result=super()._send(payload)
                        sent.append(payload.get('method'));return result
                    def _request(self,method,params,timeout=30):
                        result=super()._request(method,params,timeout)
                        if method == trigger:
                            root.rename(root.parent/'old');root.mkdir()
                        return result
                provider=ReplaceDuringPreflight(popen=fake_spawn)
                with self.assertRaisesRegex(ProviderError,'project folder changed'):
                    provider.run(str(root),'fixture')
                self.assertNotIn('turn/start',sent)
                if trigger == 'model/list': self.assertNotIn('thread/start',sent)

    def test_replaced_project_after_preflight_blocks_skills_relaunch(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as d:
            root=Path(d).resolve()/'project';root.mkdir();launches=[]
            def spawn(*args,**kw): launches.append(1);return fake_spawn(*args,**kw)
            class ReplaceAfterPreflight(CodexProvider):
                def _preflight(self,cwd):
                    root.rename(root.parent/'old');root.mkdir()
                    return ['/tmp/fixture/SKILL.md']
            with self.assertRaisesRegex(ProviderError,'project folder changed'):
                ReplaceAfterPreflight(popen=spawn).run(str(root),'fixture')
            self.assertEqual(len(launches),1)

    def test_cancel_during_preflight_blocks_skills_relaunch_and_turn(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as d:
            sent=[];launches=[]
            def spawn(*args,**kw): launches.append(1);return fake_spawn(*args,**kw)
            class CancelDuringPreflight(CodexProvider):
                def _send(self,payload):
                    result=super()._send(payload)
                    sent.append(payload.get('method'));return result
                def _preflight(self,cwd):
                    self.interrupt()
                    return ['/tmp/fixture/SKILL.md']
            provider=CancelDuringPreflight(popen=spawn)
            with self.assertRaisesRegex(ProviderError,'cancelled before launch'):
                provider.run(d,'fixture')
            self.assertEqual(len(launches),1)
            self.assertNotIn('thread/start',sent);self.assertNotIn('turn/start',sent)

    def test_missing_key_fails_before_starting_server(self):
        from unittest.mock import Mock
        spawn=Mock()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ProviderError, 'unavailable'):
                CodexProvider(popen=spawn, auth_mode='api_key', api_key_resolver=lambda:None).run(d,'task')
        spawn.assert_not_called()

    def test_requires_explicit_existing_absolute_scope(self):
        with self.assertRaises(ProviderError): CodexProvider(popen=fake_spawn).run('relative', 'task')
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ProviderError): CodexProvider(popen=fake_spawn).run(d, '')
