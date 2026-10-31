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
  self.assertIn('Autopilot targets…',s)
  self.assertIn('guard autonomy.hasGrant, !autonomy.active else { return }',s)
  self.assertIn('NSWorkspace.didWakeNotification',s)

 def test_one_screen_keeps_exact_scope_and_revalidates_before_enable(self):
  s=(ROOT/'Atticus.swift').read_text();view=s.split('final class AutopilotTargetsView:',1)[1].split('// The menu bar icon',1)[0]
  toggle=s.split('    @objc func toggleAutonomy()',1)[1].split('    func autopilotTargetError()',1)[0]
  self.assertIn('Selected targets:',view);self.assertIn('target=self;apps.action=#selector(updatePreview)',view)
  self.assertEqual(toggle.count('alert.runModal()'),1)
  self.assertIn('Enable for 10 minutes',toggle);self.assertIn('Other actions still require approval',toggle)
  self.assertIn('choices.allSatisfy({$0.command==id+" — "+path})',toggle)
  self.assertIn('choice.command==selector.sites.titleOfSelectedItem',toggle)
  self.assertIn('targets.allSatisfy({$0.currentRevision() == $0.revision})',toggle)
  self.assertLess(toggle.index('autonomyAudit("activation_confirmed")'),toggle.index('autonomy.activate(targets'))
  self.assertIn('Autopilot on ·',s);self.assertIn('autonomy.selectedCommands',s);self.assertIn('Stop Autopilot',s)

 def test_stop_cancels_before_blocking_audit(self):
  s=(ROOT/'Atticus.swift').read_text();helper=s.split('func stopScopedAutonomy(',1)[1].split('\n}',1)[0]
  self.assertLess(helper.index('scope.stop()'),helper.index('cancel()'))
  self.assertLess(helper.index('cancel()'),helper.index('schedule { _=audit() }'))
  self.assertIn('auditStarted.wait(timeout:.now()+1)',s);self.assertIn('return false},schedule:',s)
  self.assertIn('AutonomyAudit.writes.enter()',s);self.assertIn('AutonomyAudit.writes.notify(queue: .main)',s)
