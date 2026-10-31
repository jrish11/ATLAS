"""Synthetic regressions for reviewed CodeQL findings."""
import ast
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class PrivateTextTests(unittest.TestCase):
    def test_atomic_private_replacement_and_failure_cleanup(self):
        for source in (ROOT / 'atticus.py', ROOT / 'experiments/remote/atticus.py'):
            tree = ast.parse(source.read_text())
            function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'private_text')
            env = {'os': os, 'tempfile': tempfile}
            exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), 'exec'), env)
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / 'request'
                target.write_text('old'); target.chmod(0o644)
                real_replace = os.replace
                def inspect(src, dst):
                    self.assertEqual(stat.S_IMODE(os.stat(src).st_mode), 0o600)
                    self.assertEqual(target.read_text(), 'old')
                    real_replace(src, dst)
                with mock.patch.object(os, 'replace', side_effect=inspect): env['private_text'](str(target), 'synthetic')
                self.assertEqual(target.read_text(), 'synthetic')
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
                with mock.patch.object(os, 'replace', side_effect=OSError('fixture')):
                    with self.assertRaises(OSError): env['private_text'](str(target), 'new')
                self.assertEqual(target.read_text(), 'synthetic')
                self.assertEqual([p.name for p in Path(directory).iterdir()], ['request'])


@unittest.skipUnless(shutil.which('node'), 'Node is required for JavaScript checks')
class IntegrationURLTests(unittest.TestCase):
    def test_only_same_origin_http_key_links_are_allowed(self):
        text = (ROOT / 'platforms/windows/ui/settings.html').read_text()
        start = text.index('  const integrationKeyURL =')
        end = text.index('\n  };', start) + len('\n  };')
        cases = '''
const good = [['https://example.test','/key','https://example.test/key'],
              ['http://localhost:9000','/settings','http://localhost:9000/settings']];
for (const [a,p,w] of good) if (integrationKeyURL(a,p) !== w) process.exit(1);
for (const [a,p] of [['javascript:alert(1)','/key'],['data:text/html,x','/key'],
 ['https://user:pass@example.test','/key'],['https://example.test','//evil.test'],
 ['https://example.test','/\\\\evil.test'],['not a url','/key']])
 if (integrationKeyURL(a,p) !== null) process.exit(2);
'''
        result = subprocess.run(['node', '-e', text[start:end] + cases], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__': unittest.main()
