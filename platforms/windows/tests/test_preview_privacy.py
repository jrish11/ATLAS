import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import atticus


class PreviewPrivacyTests(unittest.TestCase):
    def test_telemetry_and_tips_remain_off_with_inherited_legacy_values(self):
        with tempfile.TemporaryDirectory() as root, patch.object(atticus, 'DIR', root), \
             patch.object(atticus, 'POSTHOG_KEY', 'inherited-test-key'), \
             patch.object(atticus, 'pref', return_value=True), \
             patch.dict(os.environ, {'ATTICUS_UI': '1', 'ATTICUS_POSTHOG_KEY': 'inherited-test-key'}), \
             patch.object(atticus.urllib.request, 'urlopen') as network, \
             patch.object(atticus, 'say') as output:
            atticus.posthog('used')
            atticus.ping()
            atticus.report('private request', 'failure', ['private action'], 10, 'error')
            atticus.tip('failure', 'suggestion', 'task', 20)
            network.assert_not_called()
            output.assert_not_called()
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_inherited_telemetry_key_is_not_loaded_in_fresh_process(self):
        with tempfile.TemporaryDirectory() as root:
            env = dict(os.environ, ATTICUS_DIR=root, ATTICUS_POSTHOG_KEY='inherited-test-key', PYTHONUTF8='1')
            p = subprocess.run([sys.executable, '-c', 'import atticus; assert atticus.POSTHOG_KEY == ""'], env=env, capture_output=True, text=True, timeout=15)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(list(Path(root).iterdir()), [])

if __name__ == '__main__': unittest.main()
