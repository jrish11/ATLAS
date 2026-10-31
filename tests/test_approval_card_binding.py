import shutil,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class CardBindingTests(unittest.TestCase):
 @unittest.skipUnless(shutil.which('node'),'node unavailable')
 def test_actual_card_sends_displayed_token_for_button_and_expiry(self):
  src=(ROOT/'ui/ui.html').read_text();method=src[src.index('    ask([q, cmd, retry, details, approvalToken])'):src.index('    improve()',src.index('    ask([q, cmd, retry, details, approvalToken])'))]
  script=r'''
const sent=[],timers=[],cards=[];const post=x=>sent.push(x),noop=()=>{},clockGo=noop,clockHold=noop,status=noop,setState=noop,fit=noop,follow=noop,unpin=noop,unstream=noop;const setTimeout=f=>timers.push(f);
function card(){const buttons=[{},{}];const el={isConnected:true,className:'',style:{},classList:{contains:()=>false,add:noop,toggle:()=>false,remove:noop},remove:noop,querySelector:s=>s==='b'||s==='code'?{textContent:'',classList:{toggle:()=>false,add:noop,contains:()=>false,remove:noop}}:null,querySelectorAll:()=>buttons};cards.push(el);return el}
const document={createElement:card};const thread={querySelectorAll:()=>[],append:noop};const $=()=>thread,turn=()=>thread;const ui={''' + method + r'''};
ui.ask(['old','old target','','','old-token']);const old=cards[0];ui.ask(['new','new target','','','new-token']);const current=cards[1];old.querySelectorAll()[1].onclick({stopPropagation(){}});current.querySelectorAll()[1].onclick({stopPropagation(){}});timers[1]();
if(sent.length!==3||sent[0].approvalToken!=='old-token'||sent[1].approvalToken!=='new-token'||sent[2].approvalToken!=='new-token'||sent[2].allow!==false)throw Error(JSON.stringify(sent));
'''
  p=subprocess.run([shutil.which('node'),'-e',script],capture_output=True,text=True);self.assertEqual(p.returncode,0,p.stderr)
 def test_native_compares_before_allow_and_invalidates_on_cancel(self):
  s=(ROOT/'Atticus.swift').read_text();self.assertIn('approvalCardMatches(approvalCardID, b["approvalToken"] as? String)',s);self.assertIn('self.approvalCardID = UUID().uuidString',s);self.assertIn('approvalCardID=""; approvalCardPath=""; askFile = ""',s);self.assertIn('approvalCardPath == askFile',s);self.assertIn('self.approvalCardID=""; self.approvalCardPath=""; self.askFile = j["a"]',s)
