import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import atticus

ROOT=Path(__file__).resolve().parents[1]
class NoFounderReportingTests(unittest.TestCase):
 def test_legacy_opt_in_and_environment_cannot_send(self):
  with tempfile.TemporaryDirectory() as d, patch.object(atticus,'DIR',d), patch.object(atticus,'POSTHOG_KEY','legacy-fixture'), patch.object(atticus,'pref',return_value=True), patch.dict(os.environ,{'ATTICUS_POSTHOG_KEY':'legacy-fixture'},clear=False), patch.object(atticus.subprocess,'Popen') as popen, patch.object(atticus.urllib.request,'urlopen') as urlopen:
   self.assertFalse(atticus.telemetry_enabled());atticus.ping();atticus.posthog('used');atticus.report('fixture','fixture',[],1,'failed');atticus.report_error('fixture');atticus.dictation_event('cleanup',1,1,1,False,False)
   popen.assert_not_called();urlopen.assert_not_called();self.assertFalse(Path(d,'id').exists())
 def test_no_founder_controls_and_manual_updates_remain(self):
  onboarding=(ROOT/'ui/onboarding.html').read_text();settings=(ROOT/'ui/settings.html').read_text();swift=(ROOT/'Atticus.swift').read_text();overlay=(ROOT/'ui/ui.html').read_text()
  self.assertNotIn('<section class="page" id="improve">',onboarding);self.assertNotIn('<section class="page" id="tip">',onboarding)
  for text in ('data-k="stats"','data-k="improve"','data-k="support"','data-do="kofi"'):self.assertNotIn(text,settings)
  self.assertNotIn('add(help, "Leave a Tip',swift);self.assertIn('func telemetry(_ args: [String]) { }',swift);self.assertIn('improve() { }',overlay)
  self.assertIn('This build does not check or install updates.',settings);self.assertIn('Personal fork of Atticus',settings);self.assertIn('Plip attribution',settings)
