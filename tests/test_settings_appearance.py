"""Settings appearance defaults and native/UI wiring, without changing macOS appearance."""
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
class AppearanceTests(unittest.TestCase):
 def test_system_is_default_and_legacy_settings_are_not_migrated(self):
  source=(ROOT/'Atticus.swift').read_text()
  self.assertIn('"settingsAppearance": "system"',source)
  fn=source.split('func settingsAppearance(',1)[1].split('// The custom fork',1)[0]
  self.assertIn('case "light": return NSAppearance(named:.aqua)',fn)
  self.assertIn('case "dark": return NSAppearance(named:.darkAqua)',fn)
  self.assertIn('default: return nil',fn)
  self.assertIn('w.appearance = settingsAppearance(Prefs.str("settingsAppearance"))',source)
  self.assertIn('win?.appearance = settingsAppearance(Prefs.str(k))',source)
  self.assertIn('!["system","light","dark"].contains(v as? String ?? "")',source)
 def test_source_button_uses_verified_fork_and_keeps_attribution(self):
  source=(ROOT/'Atticus.swift').read_text();page=(ROOT/'ui/settings.html').read_text()
  self.assertIn('let atlasSourceRepository = URL(string:"https://github.com/jrish11/ATLAS")!',source)
  self.assertIn('case "github": NSWorkspace.shared.open(atlasSourceRepository)',source)
  self.assertIn('upstream Atticus and Plip attribution',page)
 def test_ui_has_accessible_three_way_choice_and_honest_scope(self):
  page=(ROOT/'ui/settings.html').read_text()
  self.assertIn('role="group" aria-label="Settings appearance"',page)
  for value in ('system','light','dark'):self.assertIn('data-v="'+value+'"',page)
  self.assertIn('chat panel keeps its dark style',page)
  self.assertIn('@media (prefers-color-scheme: dark)',page)
  self.assertIn('body nav button.on',page)
