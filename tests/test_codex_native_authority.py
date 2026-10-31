"""Synthetic owner-channel checks; no real account, app, project or model."""
import tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
import atticus

class CodexNativeAuthorityTests(unittest.TestCase):
 def test_untrusted_process_cannot_start_or_approve(self):
  with tempfile.TemporaryDirectory() as d, patch.object(atticus,'DIR',d), patch.object(atticus,'trusted_native_context_parent',return_value=False), patch.object(atticus,'close_agent_window'):
   events=[];manager=atticus.Agents(emit=events.append);self.addCleanup(manager.close)
   manager.command({'action':'codex-start','folder':d,'task':'fixture','confirmed':True,'requestId':'12345678-1234-4123-8123-123456789abc'})
   self.assertEqual(manager.rows,{})
   row=manager.new();row.update(provider='codex',status='needs-you',question={'_a':'fixture'},folder=d);manager.rows[row['id']]=row
   pending={'token':'fixture','event':threading.Event(),'decision':'cancel'};manager.codex_approvals[row['id']]=pending
   manager.command({'action':'answer','id':row['id'],'question':'fixture','answer':'y'})
   self.assertFalse(pending['event'].is_set());self.assertEqual(pending['decision'],'cancel')
 def test_project_identity_rejects_replacement_and_symlink(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d).resolve()/'project';root.mkdir();st=root.stat();identity={'device':st.st_dev,'inode':st.st_ino}
   self.assertTrue(atticus.codex_project_matches(str(root),identity))
   root.rename(Path(d)/'old');root.mkdir();self.assertFalse(atticus.codex_project_matches(str(root),identity))
   link=Path(d)/'link';link.symlink_to(root,target_is_directory=True);self.assertFalse(atticus.codex_project_matches(str(link),identity))
 def test_native_confirms_exact_task_and_rechecks_approval(self):
  swift=(Path(__file__).resolve().parents[1]/'Atticus.swift').read_text()
  block=swift.split('        case "codex-start":',1)[1].split('        default: send(body)',1)[0]
  self.assertIn('Project: "+canonical',block);self.assertIn('Task: "+task',block)
  self.assertIn('alert.runModal() == .alertFirstButtonReturn',block)
  self.assertIn('decision == .alertFirstButtonReturn ? "y" : "n"',block);self.assertIn('send(reply);return',block)
  self.assertIn('now["_a"] as? String == token',block);self.assertIn('now["cmd"] as? String == details',block)
  self.assertIn('rows[id]?["status"] as? String == "needs-you"',block)
