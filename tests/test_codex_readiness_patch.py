"""Tests a proposed backend integration without changing production source."""
import ast
from pathlib import Path
import os
import re
import subprocess
import tempfile
import threading
import types
import unittest
from unittest.mock import Mock

ROOT=Path(__file__).resolve().parents[1]
FIX=ROOT/'tests/fixtures/codex-ui-integration'

class ProposedReadinessTests(unittest.TestCase):
 def namespace(self):
  import codex_provider
  ns={'platform':Mock(system=Mock(return_value='Darwin')),'pref':Mock(return_value='existing'),
      'os':Mock(path=Mock(isdir=Mock(return_value=True))), 'codex_provider':Mock(CodexProvider=Mock(validate_scope=Mock()),ProviderError=codex_provider.ProviderError),
      'shutil':Mock(which=Mock(return_value='/synthetic/codex')),'subprocess':Mock(run=Mock(return_value=types.SimpleNamespace(returncode=0,stdout='codex-cli 0.155.1\n')),SubprocessError=subprocess.SubprocessError),'re':re}
  exec(compile((FIX/'readiness-policy.py').read_text(),str(FIX/'readiness-policy.py'),'exec'),ns)
  return ns

 def test_known_version_is_only_provisional_and_adapter_still_required(self):
  n=self.namespace();ready,reason=n['codex_scoped_readiness']({'folder':'/fixture'})
  self.assertTrue(ready);self.assertIn('must pass adapter preflight',reason)
  n['codex_provider'].CodexProvider.validate_scope.assert_called_once_with('/fixture')
  self.assertEqual(n['subprocess'].run.call_args.args[0],['/synthetic/codex','--version'])

 def test_denies_unknown_version_api_fallback_wrong_os_and_protected_scope(self):
  for version in ('codex-cli 0.156.0','codex-cli 0.155.1 extra','malformed',''):
   n=self.namespace();n['subprocess'].run.return_value.stdout=version
   self.assertFalse(n['codex_scoped_readiness']({'folder':'/fixture'})[0])
  n=self.namespace();n['pref'].return_value='api_key';self.assertFalse(n['codex_scoped_readiness']({'folder':'/fixture'})[0]);n['subprocess'].run.assert_not_called()
  n=self.namespace();n['platform'].system.return_value='Linux';self.assertFalse(n['codex_scoped_readiness']({'folder':'/fixture'})[0])
  n=self.namespace();n['codex_provider'].CodexProvider.validate_scope.side_effect=n['codex_provider'].ProviderError('Protected scope')
  self.assertEqual(n['codex_scoped_readiness']({'folder':'/fixture'}),(False,'Protected scope'))

 def test_missing_cli_scope_and_version_timeout_are_fail_closed(self):
  n=self.namespace();n['shutil'].which.return_value=None;self.assertFalse(n['codex_scoped_readiness']({'folder':'/fixture'})[0])
  n=self.namespace();self.assertFalse(n['codex_scoped_readiness']({})[0])
  n=self.namespace();n['subprocess'].run.side_effect=subprocess.TimeoutExpired('codex',3);self.assertFalse(n['codex_scoped_readiness']({'folder':'/fixture'})[0])

 def test_proposed_action_requires_confirmation_and_deduplicates_after_restart(self):
  # Apply only to a temporary copy. Execute the exact proposed command method
  # against a fake registry/launcher; never import or run the candidate app.
  with tempfile.TemporaryDirectory(prefix='atticus-patch-test-') as d:
   p=Path(d,'atticus.py');p.write_text((ROOT/'atticus.py').read_text())
   r=subprocess.run(['/usr/bin/patch','--quiet',str(p),str(FIX/'backend-readiness.patch')],capture_output=True,text=True,timeout=10)
   self.assertEqual(r.returncode,0,r.stderr+r.stdout)
   tree=ast.parse(p.read_text());cls=next(x for x in tree.body if isinstance(x,ast.ClassDef) and x.name=='Agents');method=next(x for x in cls.body if isinstance(x,ast.FunctionDef) and x.name=='command')
   fake=ast.ClassDef(name='Fixture',bases=[],keywords=[],body=[method],decorator_list=[])
   ns={'re':re,'os':os,'agent_title':lambda text:text[:20]};exec(compile(ast.fix_missing_locations(ast.Module(body=[fake],type_ignores=[])),'proposed-command','exec'),ns)
   manager=ns['Fixture']();manager.lock=threading.RLock();manager.rows={};manager.emit=Mock();manager.save=Mock();manager.start=Mock();manager.new=Mock(return_value={'id':'fixture'})
   data={'action':'codex-start','folder':d,'task':'inspect','requestId':'12345678-1234-4123-8123-123456789abc','confirmed':True}
   manager.command({**data,'confirmed':False});manager.start.assert_not_called()
   manager.command(data);manager.start.assert_called_once()
   manager.command(data);manager.start.assert_called_once()
   # Simulate a restored registry: persisted request receipt still deduplicates.
   manager.rows={k:dict(v,status='stopped') for k,v in manager.rows.items()};manager.command(data);manager.start.assert_called_once()
   manager.command({**data,'task':'different'});manager.start.assert_called_once()
   self.assertIn('conflict',manager.emit.call_args.args[0]['error'])

if __name__=='__main__':unittest.main()
