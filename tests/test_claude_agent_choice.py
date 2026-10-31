"""Synthetic Claude/Codex selection; never launches a real provider."""
import os,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
import atticus
REQUEST='12345678-1234-4123-8123-123456789abc'
ORIGINAL_SAFE_MODE=atticus.safe_mode
class ClaudeAgentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.tmp.cleanup)
  self.patches=[patch.object(atticus,'DIR',self.tmp.name),patch.object(atticus,'trusted_native_context_parent',return_value=True),patch.object(atticus,'safe_mode',return_value=True),patch.object(atticus.shutil,'which',return_value='/fixture/claude')]
  for p in self.patches:p.start();self.addCleanup(p.stop)
  self.events=[];self.manager=atticus.Agents(emit=self.events.append,launch=Mock());self.addCleanup(self.manager.close)
 def test_confirmed_claude_dispatch_deduplicates_and_has_its_own_provider(self):
  self.manager.start=Mock();data={'action':'claude-start','folder':'','task':'synthetic','requestId':REQUEST,'confirmed':True}
  self.manager.command(data);self.manager.command(data)
  self.assertEqual(len(self.manager.rows),1);row=next(iter(self.manager.rows.values()));self.assertEqual(row['provider'],'claude');self.assertEqual(row['clientRequest'],REQUEST);self.assertEqual(row['_requestedModel'],'sonnet')
  self.manager.start.assert_called_once();self.manager.command({**data,'task':'different'});self.manager.start.assert_called_once();self.assertIn('conflict',self.events[-1]['error'])
 def test_untrusted_or_unconfirmed_requests_do_not_create_or_dispatch(self):
  self.manager.start=Mock();data={'action':'claude-start','folder':'','task':'synthetic','requestId':REQUEST,'confirmed':True}
  for bad in ({**data,'confirmed':False},{**data,'folder':'/private'},{**data,'requestId':'bad'},{**data,'task':''},{**data,'task':'bad\x00input'},{**data,'task':'bad\x1binput'}):self.manager.command(bad)
  with patch.object(atticus,'trusted_native_context_parent',return_value=False):self.manager.command(data)
  self.assertFalse(self.manager.rows);self.manager.start.assert_not_called()
 def test_explicit_claude_account_does_not_use_custom_server_or_inherited_tools(self):
  process=Mock();spawn=Mock(return_value=process);root=Path(self.tmp.name);row={'id':'fixture','directory':str(root),'provider':'claude'}
  prefs=lambda k,d: {'safe':True,'agentUserTools':True}.get(k,d)
  with patch.object(atticus,'pref',side_effect=prefs),patch.object(atticus,'system_prompt',return_value='synthetic'),patch.object(atticus,'server',side_effect=AssertionError('custom provider must not be read')),patch.object(atticus,'user_agent_tools',side_effect=AssertionError('tools must not load')),patch.object(atticus.subprocess,'Popen',spawn),patch.dict(os.environ,{'ANTHROPIC_API_KEY':'synthetic','ANTHROPIC_BASE_URL':'synthetic','ANTHROPIC_DEFAULT_SONNET_MODEL':'synthetic'}):
   p=atticus.start_claude('sonnet',row)
  args=spawn.call_args.args[0];env=spawn.call_args.kwargs['env'];self.assertEqual(spawn.call_args.kwargs['cwd'],str(root));self.assertTrue(all(not k.startswith('ANTHROPIC_') for k in env));self.assertIn('--disable-slash-commands',args);self.assertNotIn('ToolSearch',args[args.index('--tools')+1]);self.assertIn('Personal tools are disabled',args[args.index('--system-prompt')+1]);self.assertEqual(env['ATTICUS_FORCE_SAFE'],'1');settings=__import__('json').loads(args[args.index('--settings')+1]);self.assertTrue(settings['sandbox']['enabled']);self.assertFalse(settings['sandbox']['allowUnsandboxedCommands']);self.assertEqual(settings['sandbox']['excludedCommands'],[]);p.errors.close()
 def test_legacy_safe_off_blocks_explicit_claude_entry(self):
  self.manager.start=Mock();data={'action':'claude-start','folder':'','task':'synthetic','requestId':REQUEST,'confirmed':True}
  with patch.object(atticus,'safe_mode',return_value=False):
   self.manager.command(data)
   with self.assertRaisesRegex(OSError,'Safe mode'):atticus.start_claude('sonnet',{'id':'fixture','directory':self.tmp.name,'provider':'claude'})
  self.assertFalse(self.manager.rows);self.manager.start.assert_not_called()
 def test_forced_safety_remains_on_after_setting_changes(self):
  with patch.dict(os.environ,{'ATTICUS_FORCE_SAFE':'1'}),patch.object(atticus,'pref',return_value=False):
   self.assertTrue(ORIGINAL_SAFE_MODE())
 def test_native_confirmation_and_visible_selector_exist(self):
  root=Path(__file__).resolve().parents[1];swift=(root/'Atticus.swift').read_text();page=(root/'ui/agents.html').read_text()
  self.assertIn('Start this Claude Code task?',swift);self.assertIn('case "claude-start":',swift);self.assertIn('Claude Code · existing Claude account',page);self.assertIn('Codex · existing ChatGPT account',page)
