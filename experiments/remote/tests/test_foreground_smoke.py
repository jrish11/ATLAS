import json, os, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import foreground_smoke

class SmokeTests(unittest.TestCase):
    def test_one_fixed_request_is_bounded_and_exclusive(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=Path(d,'ledger.json'); calls=[]
            def fake(args, **kw):
                calls.append((args,kw)); self.assertEqual(kw['env']['OPENAI_API_KEY'],'mock-secret-value')
                profile=Path(kw['env']['PI_CODING_AGENT_DIR'])
                self.assertEqual(json.loads((profile/'models.json').read_text())['providers']['openai']['models'][0]['maxTokens'],128)
                self.assertEqual(json.loads((profile/'models.json').read_text())['providers']['openai']['models'][0]['api'],'openai-responses')
                self.assertFalse(json.loads((profile/'settings.json').read_text())['retry']['enabled'])
                event={'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':'READY'}],'usage':{'input':4,'output':1},'stopReason':'stop'}}
                return SimpleNamespace(returncode=0,stdout=json.dumps(event))
            with patch.object(foreground_smoke.foreground_openai,'resolve_pi',return_value='/fixture/pi'), patch.object(foreground_smoke.foreground_openai,'_runtime_node',return_value='/fixture/node'), patch.object(foreground_smoke.keychain_store.ProviderKeyStore,'get',return_value='mock-secret-value'):
                out=foreground_smoke.run(d,d,'/fixture/helper',str(ledger),fake)
                with self.assertRaises(FileExistsError): foreground_smoke.run(d,d,'/fixture/helper',str(ledger),fake)
            args,kw=calls[0];self.assertEqual(len(calls),1);self.assertEqual(out['response'],'READY');self.assertIn('--no-tools',args);self.assertIn('--offline',args);self.assertEqual(args[args.index('--thinking')+1],'off');self.assertEqual(args[-1],foreground_smoke.PROMPT);self.assertNotIn('mock-secret-value',str(args));self.assertNotIn('mock-secret-value',ledger.read_text())
    def test_malformed_events_and_private_usage_fields_are_not_saved(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=Path(d,'ledger.json')
            events=[[],{'type':'message_end','message':[]},{'type':'message_end','message':{'role':'assistant','content':[None]}},{'type':'message_end','message':{'role':'assistant','content':[{'type':'text','text':'READY'}],'usage':{'input':2,'secret':'DO_NOT_RECORD','cost':{'total':0.1,'extra':'DO_NOT_RECORD'}},'stopReason':'stop'}}]
            runner=lambda *a,**kw:SimpleNamespace(returncode=0,stdout='\n'.join(map(json.dumps,events)))
            with patch.object(foreground_smoke.foreground_openai,'resolve_pi',return_value='/fixture/pi'),patch.object(foreground_smoke.foreground_openai,'_runtime_node',return_value='/fixture/node'),patch.object(foreground_smoke.keychain_store.ProviderKeyStore,'get',return_value='mock-secret'):
                result=foreground_smoke.run(d,d,'/fixture/helper',str(ledger),runner)
            self.assertEqual(result['usage'],{'input':2,'cost':{'total':0.1}});self.assertNotIn('DO_NOT_RECORD',ledger.read_text())

    def test_startup_gate_precedes_normal_initialization(self):
        source=(Path(__file__).resolve().parents[1]/'Atticus.swift').read_text()
        gate=source.index('if CommandLine.arguments.dropFirst() == ["--foreground-smoke"]')
        self.assertLess(gate,source.index('AudioRecovery.start()'));self.assertLess(gate,source.index('let agentsUI = AgentPanels()'))
        self.assertIn('loadPage(v,"ui.html")',source);self.assertIn('text == "Reply with the single word READY."',source)
