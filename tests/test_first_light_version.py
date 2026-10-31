"""Synthetic release identity checks; no installation or migration."""
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class FirstLightVersionTests(unittest.TestCase):
 def test_display_name_does_not_replace_upstream_version_or_identity(self):
  ui=(ROOT/'ui/settings.html').read_text();build=(ROOT/'build-personal-dev.sh').read_text();swift=(ROOT/'Atticus.swift').read_text()
  self.assertIn('ATLAS 1.1 · First Light · Atticus ',ui)
  self.assertIn('<key>CFBundleIdentifier</key><string>com.atticus.personal.dev</string>',build)
  self.assertIn('<key>CFBundleVersion</key><string>2</string>',build)
  self.assertIn('<key>CFBundleShortVersionString</key><string>$VERSION</string>',build)
  self.assertEqual((ROOT/'VERSION').read_text().strip(),'1.5.4')
  self.assertIn('/.config/atticus-personal-dev',swift)
 def test_manual_updates_do_not_compare_display_labels(self):
  swift=(ROOT/'Atticus.swift').read_text();section=swift.split('enum Updater',1)[1].split('//',1)[0]
  self.assertIn('manualUpdates',section)
