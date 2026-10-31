import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class AtlasBrandingTests(unittest.TestCase):
    def test_identity_and_storage_stay_compatible(self):
        build = (ROOT / 'build-personal-dev.sh').read_text()
        self.assertIn('<key>CFBundleIdentifier</key><string>com.atticus.personal.dev</string>', build)
        self.assertIn('<key>CFBundleName</key><string>ATLAS</string>', build)
        self.assertIn('<key>CFBundleExecutable</key><string>Atticus</string>', build)
        self.assertNotIn('app.atlas.local', build)
        self.assertIn('atticus-personal-dev', (ROOT / 'Atticus.swift').read_text())
        self.assertIn('Atticus Dev', (ROOT / 'foreground_openai.py').read_text())
    def test_lineage_and_manual_updates_are_visible(self):
        page = (ROOT / 'ui/settings.html').read_text()
        self.assertIn('Personal fork of Atticus', page)
        self.assertIn('Plip attribution', page)
        self.assertIn('This build does not check or install updates.', page)
        self.assertIn('Meet ATLAS', (ROOT / 'ui/onboarding.html').read_text())
        self.assertIn('Ask ATLAS', (ROOT / 'ui/ui.html').read_text())
