import hashlib, io, json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import atticus, foreground_openai
from keychain_store import KeychainError, KeychainStore, ProviderKeyStore

class ForegroundKeyTests(unittest.TestCase):
    def test_foreground_slot_and_selection_do_not_touch_codex(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d,'settings.json');path.write_text(json.dumps({'codexAuthMode':'existing','codexApiKeyConfigured':True,'other':7}))
            backend=Mock();store=ProviderKeyStore(d,backend,slot='foreground-openai')
            with self.assertRaises(KeychainError):store.set_foreground_and_select('fixture-openai',False)
            backend.assert_not_called();store.set_foreground_and_select('fixture-openai',True)
            backend.set.assert_called_once_with('fixture-openai');backend.get.assert_not_called()
            data=json.loads(path.read_text());self.assertEqual(data['codexAuthMode'],'existing');self.assertTrue(data['codexApiKeyConfigured'])
            self.assertEqual(data['client'],'pi');self.assertEqual(data['foregroundProvider'],'openai');self.assertEqual(data['foregroundModel'],'gpt-6.1-terra');self.assertTrue(data['foregroundOpenAIKeyConfigured']);self.assertEqual(data['other'],7)
            self.assertNotIn('fixture-openai',path.read_text())
    def test_model_selection_preserves_codex_and_does_not_use_keychain(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d,'settings.json'); path.write_text(json.dumps({'client':'pi','foregroundProvider':'openai','foregroundOpenAIKeyConfigured':True,'codexAuthMode':'existing','other':7}))
            backend=Mock(); store=ProviderKeyStore(d,backend,slot='foreground-openai')
            with self.assertRaises(KeychainError): store.select_foreground_model('gpt-6.1-terra',False)
            with self.assertRaises(KeychainError): store.select_foreground_model('other',True)
            store.select_foreground_model('gpt-6.1-terra',True); backend.assert_not_called()
            data=json.loads(path.read_text());self.assertEqual(data['foregroundModel'],'gpt-6.1-terra');self.assertEqual(data['codexAuthMode'],'existing');self.assertEqual(data['other'],7)

    def test_foreground_conflict_reports_partial_save_and_preserves_external_edit(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d,'settings.json');path.write_text('{"codexAuthMode":"existing"}')
            backend=Mock();backend.set.side_effect=lambda _:path.write_text('{"concurrent":true}')
            with self.assertRaises(KeychainError):ProviderKeyStore(d,backend,slot='foreground-openai').set_foreground_and_select('fixture-openai',True)
            backend.set.assert_called_once_with('fixture-openai');self.assertEqual(path.read_text(),'{"concurrent":true}')
    def test_foreground_slot_is_distinct_and_passed_by_stdin(self):
        run=Mock(return_value=SimpleNamespace(stdout='{"ok":true}',returncode=0))
        KeychainStore('/fixture/helper',run,slot='foreground-openai').set('fixture-openai')
        args,kwargs=run.call_args;self.assertEqual(args[0],['/fixture/helper']);self.assertEqual(json.loads(kwargs['input'])['slot'],'foreground-openai');self.assertNotIn('fixture-openai',str(args))
    def test_prepare_filters_inherited_credentials_and_disables_tools(self):
        with tempfile.TemporaryDirectory() as d:
            loader=Mock(return_value='fixture-openai')
            with patch.object(foreground_openai,'_runtime_node',return_value='/fixture/node'):
                flags,env=foreground_openai.prepare(d,'gpt-4o-mini',{'PATH':'/fixture','HOME':'/fixture/home','OPENAI_API_KEY':'wrong','ANTHROPIC_API_KEY':'other','HTTP_PROXY':'https://invalid','NODE_OPTIONS':'--require evil'},loader)
            loader.assert_called_once_with();self.assertEqual(env['OPENAI_API_KEY'],'fixture-openai');self.assertNotIn('ANTHROPIC_API_KEY',env);self.assertNotIn('HTTP_PROXY',env);self.assertNotIn('NODE_OPTIONS',env)
            self.assertEqual(flags[flags.index('--provider')+1],'openai');self.assertEqual(flags[flags.index('--model')+1],'gpt-4o-mini');self.assertIn('--no-tools',flags);self.assertIn('--no-mcp',flags);self.assertIn('--no-extensions',flags);self.assertIn('--offline',flags);self.assertNotIn('fixture-openai',str(flags))
            self.assertEqual(Path(env['PI_CODING_AGENT_DIR']).stat().st_mode & 0o777,0o700)
    def test_invalid_model_never_loads_key(self):
        loader=Mock(return_value='fixture-openai')
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):foreground_openai.prepare(d,'openai/model',{},loader)
        loader.assert_not_called()

class IsolatedPiResolutionTests(unittest.TestCase):
    def test_pinned_dev_runtime_and_fail_closed_on_changes(self):
        with tempfile.TemporaryDirectory() as home:
            root=Path(home, 'resources/pi-runtime/node_modules')
            package=root/'@earendil-works/pi-coding-agent'; binary=root/'.bin/pi'
            (package/'dist/bundle').mkdir(parents=True); binary.parent.mkdir()
            node=root.parent/'bin/node';node.parent.mkdir();node.write_text('fixture');node.chmod(0o755)
            cli=package/'dist/bundle/cli.js';cli.write_text('fixture');cli.chmod(0o755)
            (package/'package.json').write_text(json.dumps({'name':'@earendil-works/pi-coding-agent','version':'1.4.0'}))
            binary.symlink_to(cli); profile=str(Path(home,'.config/atticus-personal-dev'))
            with patch.object(foreground_openai, '__file__', str(Path(home,'resources/foreground_openai.py'))):
                self.assertEqual(foreground_openai.resolve_pi(profile,home),str(binary))
                (package/'package.json').write_text(json.dumps({'name':'@earendil-works/pi-coding-agent','version':'9.0'}))
                self.assertIsNone(foreground_openai.resolve_pi(profile,home))
            fallback=Mock(return_value='/upstream/pi')
            self.assertEqual(foreground_openai.resolve_pi('/other/profile',home,fallback),'/upstream/pi')
            fallback.assert_called_once_with('pi')

class DevelopmentStartupTests(unittest.TestCase):
    def test_interrupted_jobs_do_not_resume_without_owner_action(self):
        rows=[{'id':'fixture','status':'running','provider':'claude','directory':'/fixture'}, {'id':'codex','status':'queued','provider':'codex','directory':'/fixture'}]
        launch=Mock(); save=Mock()
        with patch.dict(os.environ,{'ATTICUS_DEV_NO_AUTO_RESUME':'1'}),patch.object(atticus,'agent_history',return_value=rows),patch.object(atticus.Agents,'save',save):
            manager=atticus.Agents(emit=Mock(),launch=launch)
        launch.assert_not_called();self.assertEqual(manager.rows['fixture']['status'],'stopped');self.assertTrue(manager.rows['codex']['cancelReviewRequired'])
    def test_text_only_disables_permission_requests_and_routine_start(self):
        source=(Path(__file__).resolve().parents[1]/'Atticus.swift').read_text()
        self.assertIn('if !devTextOnly { SFSpeechRecognizer.requestAuthorization',source)
        self.assertIn('if !devTextOnly { prepareSpeech(); AVCaptureDevice.requestAccess',source)
        self.assertIn('if !devTextOnly {\n        keyMonitor = NSEvent.addGlobalMonitorForEvents',source)
        self.assertIn('No scheduled work without explicit owner action',source)

    def test_cancel_review_requires_native_confirmation(self):
        root=Path(__file__).resolve().parents[1];swift=(root/'Atticus.swift').read_text();page=(root/'ui/agents.html').read_text()
        self.assertIn('case "review-cancel":',swift);self.assertIn('"confirmed":true',swift);self.assertIn('Review cancellation…',page)

class ExternalPiResolutionTests(unittest.TestCase):
    def test_external_runtime_requires_completed_install_and_matching_node_digest(self):
        with tempfile.TemporaryDirectory() as home:
            runtime=Path(home,'Library/Application Support/Atticus Dev/pi-runtime'); root=runtime/'node_modules'; package=root/'@earendil-works/pi-coding-agent';binary=root/'.bin/pi'
            (package/'dist/bundle').mkdir(parents=True);binary.parent.mkdir();cli=package/'dist/bundle/cli.js';cli.write_text('fixture');cli.chmod(0o755);binary.symlink_to(cli)
            (package/'package.json').write_text(json.dumps({'name':'@earendil-works/pi-coding-agent','version':'1.4.0'}))
            node=Path(home,'vendor/node');node.parent.mkdir();node.write_bytes(b'fixture-node');node.chmod(0o755)
            descriptor=runtime/'runtime.json';descriptor.write_text(json.dumps({'node_path':str(node),'node_sha256':hashlib.sha256(node.read_bytes()).hexdigest()}))
            profile=str(Path(home,'.config/atticus-personal-dev'));fake_module=Path(home,'app/foreground_openai.py')
            with patch.object(foreground_openai,'__file__',str(fake_module)):
                self.assertEqual(foreground_openai.resolve_pi(profile,home),str(binary))
                (runtime/'INCOMPLETE').write_text('incomplete');self.assertIsNone(foreground_openai.resolve_pi(profile,home));(runtime/'INCOMPLETE').unlink()
                node.write_bytes(b'changed');self.assertIsNone(foreground_openai.resolve_pi(profile,home))
                loader=Mock(return_value='secret')
                with tempfile.TemporaryDirectory() as ask:
                    with self.assertRaises(ValueError):foreground_openai.prepare(ask,'gpt-6.1-terra',{'HOME':home},loader)
                loader.assert_not_called()

class SavedDestinationToolTests(unittest.TestCase):
    def setUp(self):
        p=patch.object(atticus,'pref',return_value=False);p.start();self.addCleanup(p.stop)
    def test_approval_denial_cancel_change_and_success(self):
        row={'label':'Fixture','url':'https://example.org/','confirmed':True,'aliases':['fixture'],'browser':'Safari'}
        opener=Mock(return_value='Requested opening Fixture in Safari.')
        with tempfile.TemporaryDirectory() as ask, patch.dict(os.environ,{'ATTICUS_ASK':ask,'ATTICUS_DIR':'/fixture/profile'}), patch.object(atticus.personal_commands,'resolve',return_value=row) as resolve:
            self.assertIn('not opened',atticus.foreground_saved_tool({'name':'Fixture'},approve=lambda _: 'n',open_action=opener)['text'])
            self.assertIn('not opened',atticus.foreground_saved_tool({'name':'Fixture'},approve=lambda _: None,open_action=opener)['text'])
            opener.assert_not_called();resolve.side_effect=[row,{**row,'url':'https://changed.example/'}]
            self.assertIn('changed',atticus.foreground_saved_tool({'name':'Fixture'},approve=lambda _: 'y',open_action=opener)['text']);opener.assert_not_called()
            resolve.side_effect=None;resolve.return_value=row;approval=Mock(return_value='y')
            self.assertIn('Requested',atticus.foreground_saved_tool({'name':'Fixture'},approve=approval,open_action=opener)['text']);opener.assert_called_once_with(row)
            self.assertIn('https://example.org/',approval.call_args.args[0]['cmd'])
    def test_cancelled_while_approval_is_pending_does_not_open(self):
        row={'label':'Fixture','url':'https://example.org/','confirmed':True,'aliases':['fixture'],'browser':'Safari'};opener=Mock()
        with tempfile.TemporaryDirectory() as ask,patch.dict(os.environ,{'ATTICUS_ASK':ask,'ATTICUS_DIR':'/fixture/profile'}),patch.object(atticus.personal_commands,'resolve',return_value=row):
            def approve(_): Path(ask,'declined').touch();return 'y'
            self.assertIn('not opened',atticus.foreground_saved_tool({'name':'Fixture'},approve=approve,open_action=opener)['text'])
        opener.assert_not_called()

    def test_invalid_or_ambiguous_never_asks_or_opens(self):
        approval=Mock();opener=Mock()
        with tempfile.TemporaryDirectory() as ask, patch.dict(os.environ,{'ATTICUS_ASK':ask,'ATTICUS_DIR':'/fixture/profile'}),patch.object(atticus.personal_commands,'resolve',return_value={'ambiguous':True}):
            for request in (None,{}, {'name':'x','command':'evil'}, {'name':1}, {'name':'x'*121}, {'name':'fixture'}): atticus.foreground_saved_tool(request,approve=approval,open_action=opener)
        approval.assert_not_called();opener.assert_not_called()
    def test_extension_child_environment_is_allowlisted_and_opt_in(self):
        code=atticus.FOREGROUND_SAVED_TOOL
        self.assertNotIn('...process.env',code);self.assertNotIn('OPENAI_API_KEY',code);self.assertIn('ATTICUS_ASK',code)
        source=(Path(__file__).resolve().parents[1]/'atticus.py').read_text()
        self.assertIn("pref('foregroundSavedDestinations', False) is True",source);self.assertIn("'--no-builtin-tools'",source)

class ForegroundHistoryTests(unittest.TestCase):
    def test_context_is_recent_bounded_and_resettable(self):
        pairs=[{'q':f'q{i}','a':f'a{i}'} for i in range(6)]
        self.assertEqual(foreground_openai.bounded_history(pairs),pairs[-4:])
        prompt=foreground_openai.foreground_prompt('follow up',pairs)
        self.assertIn('q5',prompt);self.assertNotIn('q0',prompt);self.assertEqual(foreground_openai.foreground_prompt('new',[]),'new')
        self.assertEqual(foreground_openai.bounded_history([{'q':'x'*2001,'a':'x'}]),[])
        self.assertEqual(foreground_openai.bounded_history([{'q':'\x01'*800,'a':'x'}]),[])
        self.assertEqual(foreground_openai.bounded_history([{'q':'ok','a':'ok','secret':'x'}]),[])
        source=(Path(__file__).resolve().parents[1]/'Atticus.swift').read_text();ui=(Path(__file__).resolve().parents[1]/'ui/ui.html').read_text()
        self.assertIn('foregroundHistory = []; foregroundPending = nil',source);self.assertIn('newConversation',ui)

class TextRouterTests(unittest.TestCase):
    def test_saved_document_runs_without_provider_and_honors_denial(self):
        prefs=lambda k,d: {'client':'pi','foregroundProvider':'openai'}.get(k,d);row={'type':'document','label':'Notes'}
        for approved in (False,True):
            with patch.object(atticus.sys,'argv',['atticus.py','--wait']),patch.object(atticus.sys,'stdin',io.StringIO(json.dumps({'front':'','task':'open notes'})+'\n')),patch.dict(os.environ,{'ATTICUS_DEV_KEYCHAIN_HELPER':'/fixture/helper'}),patch.object(atticus,'pref',side_effect=prefs),patch.object(atticus.personal_commands,'resolve',return_value=row),patch.object(atticus.personal_commands,'open_destination',return_value='Requested opening Notes; check that the document is ready.') as opener,patch.object(atticus,'wait_commit',return_value=approved),patch.object(atticus,'run_pi') as provider,patch.object(atticus,'log_turn'),patch.object(atticus,'say'):
                atticus.main();provider.assert_not_called();self.assertEqual(opener.call_count,1 if approved else 0)

    def test_typed_foreground_bypasses_screen_and_personal_context(self):
        prefs=lambda k,d: {'client':'pi','foregroundProvider':'openai','foregroundModel':'gpt-6.1-terra'}.get(k,d)
        def respond(task,request=None,history=None):
            atticus.run.ok=True;atticus.run.ran=[];return ('fixture answer',0.0,[])
        with patch.object(atticus.sys,'argv',['atticus.py','--wait']),patch.object(atticus.sys,'stdin',io.StringIO(json.dumps({'front':'','task':'fixture question'})+'\n')),patch.dict(os.environ,{'ATTICUS_DEV_KEYCHAIN_HELPER':'/fixture/helper'}),patch.object(atticus,'pref',side_effect=prefs),patch.object(atticus,'run_pi',side_effect=respond) as provider,patch.object(atticus,'log_turn') as logger,patch.object(atticus,'say') as say,patch.object(atticus,'screens',side_effect=AssertionError('screen access')),patch.object(atticus,'profile_context',side_effect=AssertionError('profile access')),patch.object(atticus,'window_summary',side_effect=AssertionError('window access')):
            atticus.main()
        provider.assert_called_once_with('fixture question',request='fixture question',history=[]);say.assert_called_with('✓','fixture answer');self.assertEqual(logger.call_args.args[:2],('', ''))

class ForegroundPiTests(unittest.TestCase):
    def test_confirmed_foreground_uses_only_isolated_key_and_text_only_flags(self):
        events=[json.dumps({'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':'Fixture answer.'}],'usage':{}}})+'\n']
        proc=SimpleNamespace(stdin=Mock(),stdout=io.StringIO(''.join(events)),returncode=0,wait=lambda:0,poll=lambda:0,pid=1)
        loader=Mock(return_value='fixture-foreground-key');popen=Mock(return_value=proc)
        if hasattr(atticus.run,'why'): delattr(atticus.run,'why')  # first request in a fresh worker
        prefs=lambda k,d: {'client':'pi','foregroundProvider':'openai','foregroundModel':'gpt-4o-mini','safe':True}.get(k,d)
        with patch.object(atticus.shutil,'which',return_value='/fixture/pi'),patch.object(foreground_openai,'_runtime_node',return_value='/fixture/node'),patch.object(atticus,'pref',side_effect=prefs),patch.object(atticus,'system_prompt',side_effect=AssertionError('personal memory access')),patch.object(atticus,'user_content',side_effect=AssertionError('context access')),patch.object(atticus,'wait_commit',return_value=True),patch.object(atticus,'relay'),patch.object(atticus.signal,'signal'),patch.object(atticus.atexit,'register'),patch.object(atticus.subprocess,'Popen',popen),patch.object(atticus.keychain_store.ProviderKeyStore,'get',loader),patch.object(atticus.keychain_store,'KeychainStore',return_value=Mock()) as backend,patch.dict(os.environ,{'ATTICUS_DEV_KEYCHAIN_HELPER':'/fixture/helper','OPENAI_API_KEY':'ambient-key','ANTHROPIC_API_KEY':'other-key','HTTP_PROXY':'https://invalid'},clear=False):
            reply,_,_=atticus.run_pi('fixture question')
        self.assertEqual(reply,'Fixture answer.');self.assertTrue(atticus.run.ok);loader.assert_called_once_with();self.assertEqual(backend.call_args.kwargs['slot'],'foreground-openai')
        proc.stdin.write.assert_called_once_with('fixture question');self.assertNotIn('fixture question',str(popen.call_args.args[0]));self.assertNotIn('system_prompt', str(popen.call_args.args[0]));self.assertIn('No tools or computer actions are available', str(popen.call_args.args[0]))
        args,kwargs=popen.call_args;argv=args[0];env=kwargs['env'];self.assertIn('--no-tools',argv);self.assertIn('--no-mcp',argv);self.assertNotIn('--extension',argv);self.assertEqual(argv[argv.index('--provider')+1],'openai');self.assertEqual(env['OPENAI_API_KEY'],'fixture-foreground-key');self.assertNotIn('ANTHROPIC_API_KEY',env);self.assertNotIn('HTTP_PROXY',env);self.assertNotIn('fixture-foreground-key',str(argv))
    def test_key_is_redacted_from_model_output_and_errors(self):
        events=[json.dumps({'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':'fixture-foreground-key'}],'usage':{}}})+'\n']
        proc=SimpleNamespace(stdin=Mock(),stdout=io.StringIO(''.join(events)),returncode=0,wait=lambda:0,poll=lambda:0,pid=1)
        prefs=lambda k,d: {'client':'pi','foregroundProvider':'openai','foregroundModel':'gpt-4o-mini','safe':True}.get(k,d)
        with patch.object(atticus.shutil,'which',return_value='/fixture/pi'),patch.object(foreground_openai,'_runtime_node',return_value='/fixture/node'),patch.object(atticus,'pref',side_effect=prefs),patch.object(atticus,'wait_commit',return_value=True),patch.object(atticus,'relay'),patch.object(atticus.signal,'signal'),patch.object(atticus.atexit,'register'),patch.object(atticus.subprocess,'Popen',return_value=proc),patch.object(atticus.keychain_store.ProviderKeyStore,'get',return_value='fixture-foreground-key'),patch.dict(os.environ,{'ATTICUS_DEV_KEYCHAIN_HELPER':'/fixture/helper'},clear=False):
            reply,_,_=atticus.run_pi('fixture question')
        self.assertEqual(reply,'[redacted]');self.assertNotIn('fixture-foreground-key',atticus.run.error)
    def test_cancelled_or_missing_pi_never_loads_key(self):
        loader=Mock(return_value='fixture-foreground-key')
        with patch.object(atticus.shutil,'which',return_value='/fixture/pi'),patch.object(atticus,'wait_commit',return_value=False),patch.object(atticus.keychain_store.ProviderKeyStore,'get',loader):
            self.assertIn('cancelled',atticus.run_pi('fixture')[0].lower())
        loader.assert_not_called()
    def test_settings_only_policy_disallows_codex_and_labels_scope(self):
        source=(Path(__file__).resolve().parents[1]/'Atticus.swift').read_text();code=source.split('enum SettingsOnlyPolicy',1)[1].split('if CommandLine.arguments.dropFirst() == ["--settings-only"]',1)[0]
        self.assertIn('foregroundOpenAIKey',code);self.assertIn('foreground-openai',code);self.assertIn('Save and use OpenAI',code);self.assertIn('Codex login is separate and unchanged',code);self.assertIn('text-only',code);self.assertIn('configuration.websiteDataStore = .nonPersistent()',code);self.assertIn("key.setAttribute('autocomplete','off')",code);self.assertIn('["do":"set","k":"codexApiKey","v":"fixture"]',code)

if __name__=='__main__':unittest.main()
