"""The isolated settings-only path never starts Atticus workers or probes."""
import os, subprocess, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
class SettingsOnlyStartup(unittest.TestCase):
    def test_settings_only_branch_precedes_every_normal_startup(self):
        source=(ROOT/'Atticus.swift').read_text()
        branch=source.index('if CommandLine.arguments.dropFirst() == ["--settings-only"]')
        self.assertLess(branch,source.index('AudioRecovery.start()'))
        self.assertLess(branch,source.index('let agentsUI = AgentPanels()'))
        self.assertLess(branch,source.index('Onboarding.plan { c in'))
        self.assertLess(branch,source.index('registerHotkey()\nregisterDictateHotkey()'))
        code=source[branch:source.index('AudioRecovery.start()',branch)]
        self.assertIn('application.run()',code);self.assertIn('exit(0)',code)
        self.assertIn('Bundle.main.bundleIdentifier == "com.atticus.personal.dev"',code)
    def test_only_explicit_key_save_can_dispatch_and_page_blocks_network(self):
        source=(ROOT/'Atticus.swift').read_text();code=source.split('enum SettingsOnlyPolicy',1)[1].split('if CommandLine.arguments.dropFirst() == ["--settings-only-selftest"]',1)[0]
        self.assertIn('request["do"] as? String == "set"',code);self.assertIn('request["k"] as? String == "foregroundOpenAIKey"',code)
        self.assertIn('default-src \'none\'',code);self.assertIn('SettingsOnlyPolicy.perform(request)',code)
        for name in ('agentsUI', 'Onboarding.plan', 'Onboarding.connectors', 'microphoneChoices', 'requestAccess', 'AudioRecovery.start', 'Prefs.set('):
            self.assertNotIn(name,code)
        self.assertNotRegex(code, r'\bPrefs\.d\b')
        self.assertIn('Existing key is not checked',code)
        self.assertIn('configuration.websiteDataStore = .nonPersistent()',code)
        self.assertIn("key.setAttribute('autocomplete','off')",code)
        self.assertIn('Save and use OpenAI',code)
        self.assertIn('keychainAction("set-foreground-and-select"',code)
        self.assertIn('Keychain may have changed',code)
    @unittest.skipUnless(os.environ.get('ATTICUS_SETTINGS_ONLY_CANDIDATE'), 'candidate not supplied')
    def test_synthetic_policy_selftest(self):
        binary=Path(os.environ['ATTICUS_SETTINGS_ONLY_CANDIDATE'])/'Contents/MacOS/Atticus'
        result=subprocess.run([str(binary),'--settings-only-selftest'],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),'settings-only selftest ok')

if __name__=='__main__': unittest.main()
