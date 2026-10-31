"""Synthetic release identity checks; no installation or migration."""
import json, shutil, subprocess, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class FirstLightVersionTests(unittest.TestCase):
 def test_display_name_does_not_replace_upstream_version_or_identity(self):
  ui=(ROOT/'ui/settings.html').read_text();build=(ROOT/'build-personal-dev.sh').read_text();swift=(ROOT/'Atticus.swift').read_text()
  self.assertIn('ATLAS 1.1 · First Light · Atticus ',ui)
  self.assertIn('<key>CFBundleIdentifier</key><string>com.atticus.personal.dev</string>',build)
  self.assertIn('<key>CFBundleVersion</key><string>3</string>',build)
  self.assertIn('<key>CFBundleShortVersionString</key><string>1.1.0</string>',build)
  self.assertIn('<key>AtticusUpstreamVersion</key><string>$VERSION</string>',build)
  self.assertIn('<key>ATLASUpdateEpoch</key><integer>1</integer>',build)
  self.assertIn('d.upstreamVersion',ui)
  self.assertIn('AtticusUpstreamVersion',swift)
  self.assertEqual((ROOT/'VERSION').read_text().strip(),'1.5.4')
  self.assertIn('/.config/atticus-personal-dev',swift)
 def test_about_uses_separate_product_and_upstream_versions(self):
  node=shutil.which('node')
  if not node:self.skipTest('Node is unavailable')
  line=next(line.strip() for line in (ROOT/'ui/settings.html').read_text().splitlines() if "$('ver').textContent = $('aboutver').textContent" in line)
  script="""const assert=require('assert');const line=JSON.parse(process.argv[1]);
  function render(d){const els={ver:{},aboutver:{}};const $=id=>els[id];eval(line);assert.equal(els.ver.textContent,els.aboutver.textContent);return els.ver.textContent;}
  assert.equal(render({manualUpdates:true,version:'1.1.0',upstreamVersion:'1.5.4'}),'ATLAS 1.1 · First Light · Atticus 1.5.4');
  assert.equal(render({manualUpdates:false,version:'upstream'}),'Version upstream');"""
  result=subprocess.run([node,'-e',script,json.dumps(line)],capture_output=True,text=True,timeout=10)
  self.assertEqual(result.returncode,0,result.stderr)
 def test_manual_updates_do_not_compare_display_labels(self):
  swift=(ROOT/'Atticus.swift').read_text();section=swift.split('enum Updater',1)[1].split('//',1)[0]
  self.assertIn('manualUpdates',section)
