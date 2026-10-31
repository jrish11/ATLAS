"""Synthetic update metadata/hostile archives only; never touches installed apps."""
import base64, copy, datetime as dt, hashlib, io, json, os, plistlib, stat, tempfile, unittest, zipfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock
import update_verify as u

NOW=dt.datetime(2026,10,31,12,tzinfo=dt.timezone.utc)
def dump(x):return json.dumps(x,separators=(',',':')).encode()
def metadata():
 return {'schema':1,'product':'ATLAS','repository':'jrish11/ATLAS','version':'v3.7','sequence':7,'channel':'prerelease','published_at':'2026-10-31T11:00:00Z','expires_at':'2026-11-02T11:00:00Z','minimum_macos':'26.0','architecture':'arm64','bundle_id':u.BUNDLE_ID,'archive':{'url':'https://github.com/jrish11/ATLAS/releases/download/v3.7/ATLAS-v3.7-macOS-arm64-PUBLIC.zip','sha256':'a'*64,'size':10},'changelog':'Fixture changes only.'}
ENVELOPE=dump({'algorithm':'Ed25519','key_id':'fixture','signature':base64.b64encode(b'0'*64).decode()})
def verify(data=None,**changes):
 opts=dict(pinned_verify=lambda *_:True,now=NOW,current_version='v3.6',highest_sequence=6,machine='arm64',macos='26.0',allow_prerelease=True);opts.update(changes)
 return u.verify_manifest(dump(metadata() if data is None else data),ENVELOPE,**opts)
def zip_data(extra=(),identity=None):
 output=io.BytesIO()
 rows=[('ATLAS.app/Contents/Info.plist',plistlib.dumps({'CFBundleIdentifier':u.BUNDLE_ID if identity is None else identity,'CFBundleExecutable':'Atticus'})),('ATLAS.app/Contents/MacOS/Atticus',b'fixture'),('ATLAS.app/Contents/MacOS/PersonalKeychain',b'fixture'),('ATLAS.app/Contents/Resources/Licenses/Atticus-MIT.txt',b'fixture MIT'),('ATLAS.app/Contents/Resources/Licenses/Plip-MIT.txt',b'fixture MIT')]
 with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as z:
  for name,data in rows+list(extra):z.writestr(name,data)
 return output.getvalue()
class ManifestTests(unittest.TestCase):
 def test_accepts_exact_signed_bytes_and_returns_immutable_fields(self):
  check=Mock(return_value=True);r=verify(pinned_verify=check);self.assertEqual(r.version,'v3.7');check.assert_called_once_with('fixture',b'0'*64,dump(metadata()))
  with self.assertRaises(Exception):r.version='v0.0'
 def test_empty_or_bad_trust_never_falls_back_to_checksum(self):
  for verifier in (None,lambda *_:False,lambda *_:1,Mock(side_effect=RuntimeError('fixture'))):
   with self.subTest(verifier=verifier),self.assertRaises(u.UpdateRejected):verify(pinned_verify=verifier)
 def test_duplicate_nonfinite_nested_malformed_and_oversize_json(self):
  for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'\xff',b'[',b'['*2000+b']'*2000,b' '*u.MAX_MANIFEST+b'0'):
   with self.subTest(raw=raw[:30]),self.assertRaises(u.UpdateRejected):u.strict_json(raw)
 def test_identity_schema_and_unknown_fields_rejected(self):
  for field,value in [('schema',True),('schema',2),('product','Other'),('repository','attacker/ATLAS'),('bundle_id','com.atticus.app'),('unexpected',1)]:
   data=metadata();data[field]=value
   with self.subTest(field=field),self.assertRaises(u.UpdateRejected):verify(data)
 def test_rollback_sameversion_sequence_and_large_version_rejected(self):
  for field,value in [('version','v3.6'),('version','v2.99'),('version','v'+'9'*5000+'.1'),('sequence',6),('sequence',True),('sequence',2**54)]:
   data=metadata();data[field]=value
   with self.subTest(field=field),self.assertRaises(u.UpdateRejected):verify(data)
 def test_channel_architecture_and_minimum_os_fail_closed(self):
  for options in ({'allow_prerelease':False},{'machine':'x86_64'},{'macos':'25.9'}):
   with self.subTest(options=options),self.assertRaises(u.UpdateRejected):verify(**options)
  data=metadata();data['channel']='beta'
  with self.assertRaises(u.UpdateRejected):verify(data)
 def test_time_expiry_future_missing_timezone_and_invalid_lifetime(self):
  for field,value in [('expires_at','2026-10-31T12:00:00Z'),('published_at','2026-11-01T11:00:00Z'),('published_at','2026-02-30T11:00:00Z'),('expires_at','2028-11-02T11:00:00Z')]:
   data=metadata();data[field]=value
   with self.subTest(field=field),self.assertRaises(u.UpdateRejected):verify(data)
  with self.assertRaises(u.UpdateRejected):verify(now=NOW.replace(tzinfo=None))
 def test_download_origin_asset_query_and_credentials_not_configurable(self):
  for url in ['http://github.com/jrish11/ATLAS/releases/download/v3.7/ATLAS-v3.7-macOS-arm64-PUBLIC.zip','https://evil.example/update.zip',metadata()['archive']['url']+'?token=x',metadata()['archive']['url'].replace('github.com','github.com@evil.example'),metadata()['archive']['url'].replace('PUBLIC','PRIVATE')]:
   data=metadata();data['archive']['url']=url
   with self.subTest(url=url),self.assertRaises(u.UpdateRejected):verify(data)
 def test_signature_envelope_mutations(self):
  for change in ({'algorithm':'none'},{'signature':'?'},{'signature':True},{'key_id':'../../key'},{'extra':'x'}):
   env=json.loads(ENVELOPE);env.update(change)
   with self.subTest(change=change),self.assertRaises(u.UpdateRejected):u.verify_manifest(dump(metadata()),dump(env),pinned_verify=lambda *_:True,now=NOW,current_version='v3.6',highest_sequence=6,machine='arm64',macos='26.0',allow_prerelease=True)
 def test_hash_size_and_changelog_bounds(self):
  for field,value in [('size',True),('size',u.MAX_ARCHIVE+1),('sha256','A'*64)]:
   data=metadata();data['archive'][field]=value
   with self.subTest(field=field),self.assertRaises(u.UpdateRejected):verify(data)
  for value in ['',None,'x'*32001,'bad\x00text']:
   data=metadata();data['changelog']=value
   with self.subTest(value=str(value)[:10]),self.assertRaises(u.UpdateRejected):verify(data)
class ArchiveTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(prefix='atlas-update-fixture-');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.data=zip_data();self.path=self.root/'update.zip';self.path.write_bytes(self.data);self.release=replace(verify(),size=len(self.data),sha256=hashlib.sha256(self.data).hexdigest())
 def test_validated_stage_does_not_install_or_touch_existing_app(self):
  old=self.root/'Installed.app';old.mkdir();(old/'sentinel').write_text('unchanged');callback=Mock(return_value=True)
  result=u.stage_archive(self.path,self.release,self.root/'staged',verify_bundle=callback)
  self.assertEqual(result.name,'ATLAS.app');self.assertEqual((old/'sentinel').read_text(),'unchanged');self.assertEqual(len(callback.call_args_list),1)
  self.assertEqual(stat.S_IMODE(result.parent.stat().st_mode),0o700)
 def test_no_default_native_verifier_and_denial_removes_only_own_stage(self):
  with self.assertRaises(u.UpdateRejected):u.stage_archive(self.path,self.release,self.root/'stage')
  with self.assertRaises(u.UpdateRejected):u.stage_archive(self.path,self.release,self.root/'denied',verify_bundle=lambda *_:False)
  self.assertFalse((self.root/'denied').exists());self.assertTrue(self.path.exists())
 def test_existing_stage_is_never_replaced(self):
  dest=self.root/'existing';dest.mkdir();(dest/'sentinel').write_text('keep')
  with self.assertRaises(FileExistsError):u.stage_archive(self.path,self.release,dest,verify_bundle=lambda *_:True)
  self.assertEqual((dest/'sentinel').read_text(),'keep')
 def test_changed_hash_size_symlink_and_fifo_fail_without_dispatch(self):
  for release in (replace(self.release,sha256='0'*64),replace(self.release,size=len(self.data)+1),replace(self.release,size=u.MAX_ARCHIVE+1)):
   with self.assertRaises(u.UpdateRejected):u.archive_bytes(self.path,release)
  link=self.root/'link';link.symlink_to(self.path)
  with self.assertRaises(OSError):u.archive_bytes(link,self.release)
  fifo=self.root/'fifo';os.mkfifo(fifo)
  with self.assertRaises(u.UpdateRejected):u.archive_bytes(fifo,self.release)
 def test_unsafe_paths_and_private_roots_rejected_before_writes(self):
  for name in ['../escape','/tmp/escape','ATLAS.app/../escape','ATLAS.app//x','ATLAS.app/./x','ATLAS.app\\escape','ATLAS.app/x:y','Optional Profile/profile.json','ATLAS.app/settings.json','ATLAS.app/secret.pem','ATLAS.app/Contents/Info.plist/child','ATLAS.app/Contents/info.PLIST']:
   with self.subTest(name=name),self.assertRaises(u.UpdateRejected):u.inspect_archive(zip_data([(name,b'fixture')]))
  # Python's writer truncates a NUL name, so mutate both on-disk name records.
  raw=zip_data([('ATLAS.app/xAy',b'fixture')]).replace(b'ATLAS.app/xAy',b'ATLAS.app/x\x00y')
  with self.assertRaises(u.UpdateRejected):u.inspect_archive(raw)
 def test_symlink_special_and_duplicate_entries_rejected(self):
  for mode in (stat.S_IFLNK|0o777,stat.S_IFIFO|0o600,stat.S_IFSOCK|0o600):
   info=zipfile.ZipInfo('ATLAS.app/link');info.create_system=3;info.external_attr=mode<<16
   with self.subTest(mode=mode),self.assertRaises(u.UpdateRejected):u.inspect_archive(zip_data([(info,b'target')]))
  with self.assertRaises(u.UpdateRejected):u.inspect_archive(zip_data([('ATLAS.app/Contents/MacOS/Atticus',b'duplicate')]))
 def test_nfc_alias_and_file_directory_conflicts(self):
  for rows in [[('ATLAS.app/e\u0301.txt',b'x')],[('ATLAS.app/a/b',b'x'),('ATLAS.app/a',b'y')]]:
   with self.assertRaises(u.UpdateRejected):u.inspect_archive(zip_data(rows))
 def test_missing_identity_and_native_exception_preserve_installed_state(self):
  bad=zip_data(identity='com.atticus.personal.bad')
  self.path.write_bytes(bad)
  bad_release=replace(self.release,size=len(bad),sha256=hashlib.sha256(bad).hexdigest())
  callback=Mock(return_value=True)
  with self.assertRaises(u.UpdateRejected):u.stage_archive(self.path,bad_release,self.root/'bad',verify_bundle=callback)
  callback.assert_not_called()
  self.path.write_bytes(self.data)
  with self.assertRaises(RuntimeError):u.stage_archive(self.path,self.release,self.root/'crash',verify_bundle=Mock(side_effect=RuntimeError('fixture')))
  self.assertFalse((self.root/'crash').exists())
if __name__=='__main__':unittest.main()
