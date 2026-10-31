import base64,hashlib,importlib.util,io,json,tarfile,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent

def module(name,file):
 spec=importlib.util.spec_from_file_location(name,HERE/file);obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj
p=module('release_provenance','provenance.py')
class ProvenanceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  for x in ('tarballs','notices','installed'):(self.root/x).mkdir()
  pkg={'name':'fixture-package','version':'1.0.0','license':'MIT'};files={'package/package.json':json.dumps(pkg).encode(),'package/LICENSE':b'fixture license text '+b'x'*120,'package/index.js':b'fixture code'}
  buf=io.BytesIO()
  with tarfile.open(fileobj=buf,mode='w:gz') as tar:
   for name,data in files.items():
    item=tarfile.TarInfo(name);item.size=len(data);tar.addfile(item,io.BytesIO(data))
  self.archive=buf.getvalue();integrity='sha512-'+base64.b64encode(hashlib.sha512(self.archive).digest()).decode();url='https://registry.npmjs.org/fixture-package/-/fixture-package-1.0.0.tgz'
  self.lock={'version':'1.0.0','integrity':integrity,'resolved':url};self.meta={'name':'fixture-package','version':'1.0.0','license':'MIT','dist':{'integrity':integrity,'tarball':url}}
  dest=self.root/'installed/fixture-package';dest.mkdir()
  for name,data in files.items():(dest/Path(name).name).write_bytes(data)
 def get(self,url,limit):
  if url.endswith('/1.0.0'):return json.dumps(self.meta).encode()
  if url.endswith('.tgz'):return self.archive
  raise AssertionError('unexpected URL')
 def test_verified_archive_notice_and_installed_files(self):
  with patch.object(p,'get',side_effect=self.get):r=p.verify('fixture-package',self.lock,self.root,self.root/'installed')
  self.assertEqual(r['installed_files_verified'],3);self.assertTrue((self.root/'notices'/r['notice_file']).is_file())
 def test_tamper_and_registry_mismatch_fail(self):
  (self.root/'installed/fixture-package/index.js').write_text('tampered')
  with patch.object(p,'get',side_effect=self.get),self.assertRaisesRegex(ValueError,'differs'):p.verify('fixture-package',self.lock,self.root,self.root/'installed')
  self.meta['version']='2.0.0'
  with patch.object(p,'get',side_effect=self.get),self.assertRaisesRegex(ValueError,'disagrees'):p.verify('fixture-package',self.lock,self.root,self.root/'installed')
 def test_repository_parsing_rejects_untrusted_hosts(self):
  self.assertEqual(p.repository({'repository':{'url':'git://github.com/example/project.git'}}),('example','project'))
  self.assertIsNone(p.repository({'repository':{'url':'https://evil.example/project.git'}}))
if __name__=='__main__':unittest.main()
