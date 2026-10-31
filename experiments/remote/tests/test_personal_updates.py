import unittest
from pathlib import Path

class PersonalUpdateTests(unittest.TestCase):
 def test_personal_build_never_schedules_or_fetches_updates(self):
  root=Path(__file__).resolve().parents[1];source=(root/'Atticus.swift').read_text();updater=source.split('enum Updater {',1)[1].split('// Opening Atticus again',1)[0]
  check=updater.split('static func check(',1)[1].split('static func restartWhenIdle',1)[0]
  schedule=updater.split('static func schedule()',1)[1]
  self.assertLess(check.index('if manualUpdates'),check.index('git fetch'))
  self.assertLess(schedule.index('if manualUpdates'),schedule.index('Timer.scheduledTimer'))
  self.assertIn('precondition(done && Updater.status == Updater.manualMessage)',source)
 def test_personal_ui_is_explicit_and_auth_is_separate(self):
  root=Path(__file__).resolve().parents[1];page=(root/'ui/settings.html').read_text()
  self.assertIn('d.managedUpdates || d.manualUpdates',page);self.assertIn('This build does not check or install updates.',page)
  self.assertIn('Foreground OpenAI API through Pi; separate from Codex account login.',page)
  self.assertIn('Scoped Codex tasks use your existing account login.',page)
