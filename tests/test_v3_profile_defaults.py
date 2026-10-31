import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import atticus
class V3ProfileTests(unittest.TestCase):
 def test_fresh_defaults_and_existing_preferences_survive(self):
  with tempfile.TemporaryDirectory() as d:
   directory=Path(d,'.config','atticus-personal-dev');directory.mkdir(parents=True);path=directory/'settings.json'
   with patch.object(atticus,'HOME',d),patch.object(atticus,'DIR',str(directory)),patch.object(atticus,'PREFS',str(path)):
    self.assertEqual(atticus.pref('client','claude'),'pi');self.assertEqual(atticus.pref('foregroundProvider',''),'openai');self.assertEqual(atticus.pref('codexAuthMode',''),'existing');self.assertFalse(path.exists())
    original={'client':'claude','foregroundProvider':'other','codexAuthMode':'existing','unknown':'preserve'};path.write_text(json.dumps(original));before=path.read_bytes()
    self.assertEqual(atticus.pref('client','pi'),'claude');self.assertEqual(atticus.pref('foregroundProvider','openai'),'other');self.assertEqual(path.read_bytes(),before)
    path.write_text('{bad');self.assertEqual(atticus.pref('client','caller-default'),'caller-default');self.assertEqual(path.read_text(),'{bad')
 def test_onboarding_discloses_separate_codex_and_no_live_jobs(self):
  s=Path(__file__).resolve().parents[1].joinpath('ui/onboarding.html').read_text();self.assertIn('Codex uses your existing ChatGPT account separately',s);self.assertIn('Codex jobs are not yet enabled',s);self.assertIn('<summary>Other providers</summary>',s)
