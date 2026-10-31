"""VM-only file-origin WKWebView UUID regression; no app, credentials, or provider."""
import json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from tests.test_shelf_page import HARNESS
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=r'''
const wait=ms=>new Promise(r=>setTimeout(r,ms));
agents.mode('view');agents.list([]);
if(typeof crypto.randomUUID!=='undefined'||typeof crypto.getRandomValues!=='function')throw Error('fixture did not disable randomUUID or secure bytes unavailable');
document.getElementById('new-codex').click();document.getElementById('codex-task').value='synthetic';
document.getElementById('codex-form').requestSubmit();document.getElementById('codex-form').requestSubmit();await wait(30);
const bytes=window.__uuidBytes.slice();bytes[6]=(bytes[6]&15)|64;bytes[8]=(bytes[8]&63)|128;
const hex=bytes.map(x=>x.toString(16).padStart(2,'0')).join('');const id=`${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
const disabled=document.getElementById('codex-submit').disabled;
document.getElementById('codex-dismiss').click();document.getElementById('new-codex').click();
agents.codexStartCancelled('stale');const stillPending=document.getElementById('codex-submit').disabled;
agents.codexStartCancelled(id);const unlocked=!document.getElementById('codex-submit').disabled;
const row={id:'fixture',provider:'codex',folder:'/fixture',status:'done',title:'Fixture',created:Date.now()/1000};
agents.list([row]);agents.select('fixture');document.getElementById('followup').value='next';document.getElementById('send').click();document.getElementById('send').click();await wait(20);
return {id,disabled,stillPending,unlocked,randomCalls:window.__randomCalls,protocol:location.protocol};
'''

class CodexUUIDWebKit(unittest.TestCase):
 @unittest.skipUnless(sys.platform=='darwin' and os.environ.get('ATTICUS_VM')=='1','offscreen WKWebView fixture runs only in the isolated VM')
 def test_file_origin_start_duplicate_cancel_and_continue(self):
  with tempfile.TemporaryDirectory(prefix='atlas-uuid-webkit-') as d:
   root=Path(d);page=root/'agents.html';source=root/'harness.swift';binary=root/'harness'
   page.write_text((ROOT/'ui/agents.html').read_text().replace('/*ORBS*/',(ROOT/'ui/orbs.js').read_text()))
   swift=HARNESS.replace('let h = Harness(), cfg = WKWebViewConfiguration()','let h = Harness(), cfg = WKWebViewConfiguration(); cfg.websiteDataStore = .nonPersistent()')
   inject="Object.defineProperty(crypto,'randomUUID',{value:undefined,configurable:true});const secure=crypto.getRandomValues.bind(crypto);window.__randomCalls=0;Object.defineProperty(crypto,'getRandomValues',{value:function(a){const r=secure(a);window.__uuidBytes=Array.from(a);window.__randomCalls++;return r},configurable:true});"
   marker='cfg.userContentController.add(h, name: "agents"); cfg.userContentController.add(h, name: "errors")'
   swift=swift.replace(marker,marker+'\ncfg.userContentController.addUserScript(WKUserScript(source:'+json.dumps(inject)+', injectionTime:.atDocumentStart, forMainFrameOnly:true))')
   old='h.web.loadHTMLString(try! String(contentsOfFile: CommandLine.arguments[1], encoding: .utf8), baseURL: nil)'
   swift=swift.replace(old,'let file=URL(fileURLWithPath:CommandLine.arguments[1]); h.web.loadFileURL(file,allowingReadAccessTo:file.deletingLastPathComponent())')
   self.assertNotIn(old,swift);source.write_text(swift)
   env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin','HOME':d,'TMPDIR':d,'ATTICUS_DIR':str(root/'profile'),'ATTICUS_POSTHOG_KEY':'','CLANG_MODULE_CACHE_PATH':str(root/'clang')}
   built=subprocess.run(['swiftc',str(source),'-o',str(binary)],capture_output=True,text=True,env=env,timeout=90);self.assertEqual(built.returncode,0,built.stderr)
   result=subprocess.run([str(binary),str(page),SCRIPT],capture_output=True,text=True,env=env,timeout=30);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   out=json.loads(result.stdout.strip().splitlines()[-1]);value=out['result'];posts=out['posts']
   self.assertEqual(value['protocol'],'file:');self.assertTrue(value['disabled'] and value['stillPending'] and value['unlocked']);self.assertEqual(value['randomCalls'],1)
   starts=[p for p in posts if p.get('action')=='codex-start'];self.assertEqual(len(starts),1);self.assertEqual(starts[0]['requestId'],value['id'])
   followups=[p for p in posts if p.get('action')=='followup'];self.assertEqual(len(followups),1)
   self.assertFalse([p for p in posts if 'error' in p])
