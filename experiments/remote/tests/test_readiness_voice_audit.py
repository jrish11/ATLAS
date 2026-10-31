"""Extract production Swift guards into a credential/device-free Foundation harness.

No AppKit/AVFoundation import, permission request, audio capture or provider call.
These prove guard/segment behavior, not actual macOS speech availability.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]


def section(source, start, end):
    return source[source.index(start):source.index(end, source.index(start))]


class VoiceReadinessAudit(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('ATTICUS_VM') or os.environ.get('ATTICUS_ALLOW_HOST_UI'),
                         'repository host guard requires VM or explicit host UI authorization')
    def test_actual_permission_guards_and_stale_transcripts(self):
        source = (ROOT / 'Atticus.swift').read_text()
        guards = section(source, '        guard AVCaptureDevice.authorizationStatus(for: .audio) == .authorized else {', '        if !quiet && !dictate && !replying')
        stitch = section(source, 'func stitchTranscript(', '\nfinal class SpeechInputs:')
        piece = section(source, '    func speechPiece(', '\n    func rolloverSpeech(')
        swift = r'''import Foundation
enum Auth { case authorized, denied, notDetermined, restricted }
struct AVCaptureDevice {
 static var permission = Auth.authorized, available = true
 enum Media { case audio }
 static func authorizationStatus(for: Media)->Auth { permission }
 init?(uniqueID: String) { if !Self.available { return nil } }
 static func `default`(for: Media)->AVCaptureDevice? { AVCaptureDevice(uniqueID:"fake") }
}
enum SFSpeechRecognizer { static var permission = Auth.authorized; static func authorizationStatus()->Auth { permission } }
enum Prefs { static var model="speech"; static func str(_ key:String)->String { model } }
final class Whisper { static let shared=Whisper(); var ready=true }
final class Settings { var opened=0; func open(tab:String) { opened += 1 } }
enum Atticus { static let settings=Settings() }
struct MicChoice { let uid:String }
func listenMic()->MicChoice? { nil }
''' + stitch + r'''
final class Fixture {
 var replying=false, dictate=false, hushCount=0, replyStops=0, messages=[String](), reached=false
 var listenID=7, activeSpeechSegment=1
 var speechText:[Int:(base:String,done:String,live:String)] = [1:("Open", "", "")]
 var heardValues=[String]()
 func hush(){ hushCount += 1 }; func stopOfferInput(){replyStops += 1}
 func js(_ kind:String,_ text:String){messages.append(text)}; func hide(after:Int){}
 func heard(_ text:String){heardValues.append(text)}
 func attempt(){
''' + guards + r'''
 _ = device; reached=true
 }
''' + piece + r'''
}
var checks=0
func check(_ value:@autoclosure()->Bool){precondition(value());checks += 1}
for state in [Auth.denied,.notDetermined,.restricted] {
 AVCaptureDevice.permission=state; let f=Fixture();f.attempt()
 check(!f.reached);check(f.hushCount==1);check(f.messages.last?.contains("Microphone")==true)
}
AVCaptureDevice.permission = .denied
let replying=Fixture();replying.replying=true;replying.attempt();check(replying.replyStops==1);check(replying.hushCount==0)
AVCaptureDevice.permission = .authorized
SFSpeechRecognizer.permission = .denied
let denied=Fixture();denied.attempt();check(!denied.reached);check(denied.messages.last?.contains("Speech Recognition")==true)
let dictation=Fixture();dictation.dictate=true;dictation.attempt();check(dictation.reached)
Prefs.model="whisper";Whisper.shared.ready=false
let missing=Fixture();missing.attempt();check(!missing.reached);check(Atticus.settings.opened==1)
Whisper.shared.ready=true
let local=Fixture();local.attempt();check(local.reached)
AVCaptureDevice.available=false
let unplugged=Fixture();unplugged.attempt();check(!unplugged.reached);check(unplugged.messages.last?.contains("No microphone")==true)
AVCaptureDevice.available=true;Prefs.model="speech";SFSpeechRecognizer.permission = .authorized
let retry=Fixture();retry.attempt();check(retry.reached)
let stream=Fixture()
stream.speechPiece("stale",final:true,segment:1,listeningID:6);check(stream.heardValues.isEmpty)
stream.speechPiece("missing",final:true,segment:99,listeningID:7);check(stream.heardValues.isEmpty)
stream.speechPiece("Schoology",final:false,segment:1,listeningID:7);check(stream.heardValues==["Open Schoology"])
stream.speechPiece("Lovable",final:true,segment:1,listeningID:7);check(stream.heardValues.last=="Open Lovable")
stream.listenID += 1;stream.speechPiece("late",final:true,segment:1,listeningID:7);check(stream.heardValues.count==2)
print("synthetic production guard checks: \(checks)")
'''
        with tempfile.TemporaryDirectory(prefix='atticus-voice-audit-') as d:
            root=Path(d); harness=root/'guards.swift'; binary=root/'guards'
            harness.write_text(swift)
            env={'PATH':'/usr/bin:/bin','HOME':d,'TMPDIR':d,'CLANG_MODULE_CACHE_PATH':str(root/'clang'),'SWIFT_MODULECACHE_PATH':str(root/'swift')}
            built=subprocess.run(['/usr/bin/swiftc',str(harness),'-o',str(binary)],capture_output=True,text=True,env=env,timeout=60)
            self.assertEqual(built.returncode,0,built.stderr[-3000:])
            result=subprocess.run([str(binary)],capture_output=True,text=True,env=env,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr[-1000:])
            self.assertIn('synthetic production guard checks:',result.stdout)

    def test_live_agents_gate_fails_before_any_provider_construction(self):
        import atticus
        manager=object.__new__(atticus.Agents);manager.finish=Mock()
        with patch.object(atticus,'CODEX_AGENT_READY',False),patch.object(atticus.codex_provider,'CodexProvider') as provider:
            row={'id':'synthetic-gate','folder':'/synthetic'}
            manager.start_codex(row,'fixture only')
            provider.assert_not_called()
            self.assertEqual(manager.finish.call_args.args[1],'failed')
            self.assertIn('not enabled',manager.finish.call_args.args[2])

if __name__=='__main__':unittest.main()
