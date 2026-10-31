import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import folder_grants as g
class FolderGrantTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve();self.store=self.root/'store';self.store.mkdir();self.folder=self.root/'folder';self.folder.mkdir();self.path=str(self.folder);self.ident=g.identity(self.path)
 def add(self,access='read'):return g.manage(str(self.store),'add',path=self.path,access=access,expected=self.ident,confirmed=True)
 def test_requires_confirmation_supports_read_write_and_revoke(self):
  with self.assertRaises(ValueError):g.manage(str(self.store),'add',path=self.path,access='read',expected=self.ident)
  self.add();self.add('write');rows=g.manage(str(self.store),'list')['grants'];self.assertEqual({x['access'] for x in rows},{'read','write'});self.assertTrue(all(x['available'] for x in rows))
  with self.assertRaises(ValueError):self.add()
  with self.assertRaises(ValueError):g.manage(str(self.store),'revoke',identifier=rows[0]['id'],expected={'device':0,'inode':0},confirmed=True)
  self.assertEqual(g.manage(str(self.store),'revoke',identifier=rows[0]['id'],expected=rows[0]['identity'],confirmed=True)['status'],'revoked')
 def test_root_replacement_and_unavailability_fail_closed(self):
  self.add();self.folder.rename(self.root/'old');self.folder.mkdir();row=g.manage(str(self.store),'list')['grants'][0];self.assertFalse(row['available'])
  with self.assertRaises(ValueError):g.manage(str(self.store),'add',path=self.path,access='write',expected=self.ident,confirmed=True)
  self.folder.rmdir();self.assertFalse(g.manage(str(self.store),'list')['grants'][0]['available'])
 def test_symlink_and_traversal_are_refused(self):
  link=self.root/'link';link.symlink_to(self.folder,target_is_directory=True)
  for path in (str(link),str(self.folder/'..'/'folder')):
   with self.assertRaises(ValueError):g.identity(path)
 def test_corrupt_unknown_and_symlink_registry_never_rewritten(self):
  file=self.store/'folder-grants.json';file.write_text('{"version":1,"grants":[],"unknown":true}');before=file.read_bytes()
  with self.assertRaises(ValueError):self.add()
  self.assertEqual(file.read_bytes(),before);file.unlink();file.symlink_to(self.root/'elsewhere')
  with self.assertRaises(ValueError):self.add()
 def test_ui_discloses_no_prompt_reduction_or_os_grant(self):
  root=Path(__file__).resolve().parents[1];html=(root/'ui/settings.html').read_text();swift=(root/'Atticus.swift').read_text()
  self.assertIn('They do not authorize model sharing or reduce approvals',html);self.assertIn('does not grant macOS permission',swift);self.assertIn('picker.canChooseDirectories=true',swift)

 def test_local_preview_requires_native_confirmation_and_does_not_send_to_model(self):
  root=Path(__file__).resolve().parents[1];swift=(root/'Atticus.swift').read_text();html=(root/'ui/settings.html').read_text()
  start=swift.index('    func activateFolderRead(');end=swift.index('    func revokeFolderGrant(',start);activation=swift[start:end]
  self.assertIn('alert.runModal() == .alertFirstButtonReturn',activation);self.assertIn('localFolderReadScope=scope',activation)
  reader=swift[swift.index('final class LocalFolderReadScope'):swift.index('final class SettingsWindow')]
  for guard in ('O_NOFOLLOW','AT_SYMLINK_NOFOLLOW','65536','openRoot()','private[ _-]?key','scanned>2000','controlCharacters'):self.assertIn(guard,reader)
  self.assertLess(reader.index('fstatat(root,$0,&initial'),reader.index('openat(root,$0'))
  self.assertIn("$('folderLocalText').textContent=result.text",html);self.assertIn('Contents stay here and are not sent to a model',html)

 def test_empty_listing_does_not_create_profile_or_lock(self):
  missing=self.root/'new-profile';self.assertEqual(g.manage(str(missing),'list'),{'grants':[]});self.assertFalse(missing.exists())
  self.assertEqual(g.manage(str(missing),'add',path=self.path,access='read',expected=self.ident,confirmed=True)['status'],'saved')
