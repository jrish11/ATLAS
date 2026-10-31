import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class NativeScopeGateTests(unittest.TestCase):
 def test_scope_is_ephemeral_and_owner_activated(self):
  s=(ROOT/'Atticus.swift').read_text();scope=s.split('struct ScopedTarget {',1)[1].split('    override init() {',1)[0]
  self.assertIn('static let featureEnabled = true',scope);self.assertIn('private var targets: [ScopedTarget] = []',scope);self.assertIn('private var targets: [ScopedTarget]',scope);self.assertIn('stopScopedAutonomy(autonomy,cancel:{app.cancel()}',scope)
  self.assertNotIn('autonomyCall',scope);self.assertNotIn('ATTICUS_OWNER_PID',scope);self.assertNotIn('.stopped',scope)
 def test_native_checks_revision_and_time_after_validation(self):
  s=(ROOT/'Atticus.swift').read_text();self.assertIn('target.currentRevision() == target.revision',s);self.assertIn('return active && now() < expires',s);self.assertIn('fakeNow=701;return "v1"',s)
  self.assertIn('if NativeAutonomyScope.featureEnabled, pieces.count == 3',s)
  self.assertIn('let freshScope=NativeAutonomyScope();precondition(!freshScope.active)',s)
  self.assertLess(s.index('guard alert.runModal() == .alertFirstButtonReturn'),s.index('autonomy.activate(targets'))
  self.assertIn('Autonomous mode — approved tasks',s)
  self.assertIn('guard autonomy.hasGrant, !autonomy.active else { return }',s)
  self.assertIn('NSWorkspace.didWakeNotification',s)

 def test_stop_cancels_before_blocking_audit(self):
  s=(ROOT/'Atticus.swift').read_text();helper=s.split('func stopScopedAutonomy(',1)[1].split('\n}',1)[0]
  self.assertLess(helper.index('scope.stop()'),helper.index('cancel()'))
  self.assertLess(helper.index('cancel()'),helper.index('schedule { _=audit() }'))
  self.assertIn('auditStarted.wait(timeout:.now()+1)',s);self.assertIn('return false},schedule:',s)
  self.assertIn('AutonomyAudit.writes.enter()',s);self.assertIn('AutonomyAudit.writes.notify(queue: .main)',s)
