import Foundation
import CryptoKit
@main struct Test {
 static func main() throws {
  let host=UUID(),device=UUID(),key=P256.Signing.PrivateKey();var now=1.0
  let peer=DeviceAuthority(deviceID:device,generation:1,signingKey:key.publicKey.x963Representation,revoked:false)
  var approvals=0
  let server=SyntheticRoutes(hostID:host,expectedHost:"mac.example",expectedOrigin:"https://atlas-desktop.joelr2.chatgpt.site",peer:peer,scope:("project","one"),sessionDeadline:100,clock:{now},wallClock:{1000},ownerConfirm:{_ in approvals += 1;return true})
  let taskID=UUID(),task=try JSONEncoder().encode(SyntheticTask(id:taskID,task:"synthetic"))
  func operation(_ action:String,_ path:String,_ payload:Data)throws->SyntheticOperation {
   let intent=RequestIntent(hostID:host,deviceID:device,generation:1,scopeID:"project",scopeRevision:"one",action:action,method:"POST",path:path,expiresAt:1020,payloadDigest:Data(SHA256.hash(data:payload)))
   let c=try server.challenge(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",intent:intent)
   return SyntheticOperation(challenge:c,signature:try key.signature(for:requestProofMessage(c)).rawRepresentation,payload:payload)
  }
  let secondTask=try JSONEncoder().encode(SyntheticTask(id:UUID(),task:"second synthetic"))
  let second=try operation("submit","/v1/tasks",secondTask)
  let start=try operation("submit","/v1/tasks",task)
  do { _=try server.operation(host:"evil.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",path:"/v1/tasks",value:start);fatalError("host") } catch ProofError.denied {}
  let submitted=try server.operation(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",path:"/v1/tasks",value:start);precondition(submitted.status=="submitted" && approvals==1)
  do { _=try server.operation(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",path:"/v1/tasks",value:second);fatalError("second task accepted") } catch ProofError.invalid {}
  do { _=try server.operation(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",path:"/v1/tasks",value:start);fatalError("replay") } catch ProofError.replay {}
  let statusPayload=try JSONEncoder().encode(SyntheticTask(id:taskID,task:nil)),status=try operation("status","/v1/tasks/status",statusPayload)
  let running=try server.operation(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",path:"/v1/tasks/status",value:status);precondition(running.status=="submitted")
  let stop=try operation("stop","/v1/tasks/stop",statusPayload),stopped=try server.operation(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",path:"/v1/tasks/stop",value:stop);precondition(stopped.status=="stopped")
  do { _=try operation("submit","/v1/tasks",secondTask);fatalError("second task after stop") } catch ProofError.denied {}
  let pending=try operation("status","/v1/tasks/status",statusPayload);try server.revoke(ownerConfirmed:true)
  do { _=try server.operation(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",path:"/v1/tasks/status",value:pending);fatalError("revoked") } catch ProofError.denied {}
  let entered=DispatchSemaphore(value:0),release=DispatchSemaphore(value:0),done=DispatchSemaphore(value:0)
  let blocked=SyntheticRoutes(hostID:host,expectedHost:"mac.example",expectedOrigin:"https://atlas-desktop.joelr2.chatgpt.site",peer:peer,scope:("project","one"),sessionDeadline:100,clock:{now},wallClock:{1000},ownerConfirm:{_ in entered.signal();release.wait();return true})
  let intent=start.challenge.intent,challenge=try blocked.challenge(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",intent:intent)
  let signed=SyntheticOperation(challenge:challenge,signature:try key.signature(for:requestProofMessage(challenge)).rawRepresentation,payload:task)
  DispatchQueue.global().async { defer { done.signal() };do { _=try blocked.operation(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",path:"/v1/tasks",value:signed);fatalError("revoked during approval") } catch ProofError.denied {} catch { fatalError("unexpected error") } }
  precondition(entered.wait(timeout:.now()+2) == .success);try blocked.revoke(ownerConfirmed:true);release.signal();precondition(done.wait(timeout:.now()+2) == .success);precondition(blocked.taskCount==0)
  let stopEntered=DispatchSemaphore(value:0),stopRelease=DispatchSemaphore(value:0),stopDone=DispatchSemaphore(value:0)
  let waiting=SyntheticRoutes(hostID:host,expectedHost:"mac.example",expectedOrigin:"https://atlas-desktop.joelr2.chatgpt.site",peer:peer,scope:("project","one"),sessionDeadline:100,clock:{now},wallClock:{1000},ownerConfirm:{_ in stopEntered.signal();stopRelease.wait();return true})
  let waitingChallenge=try waiting.challenge(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",intent:intent),waitingStart=SyntheticOperation(challenge:waitingChallenge,signature:try key.signature(for:requestProofMessage(waitingChallenge)).rawRepresentation,payload:task)
  DispatchQueue.global().async {defer{stopDone.signal()};do {_=try waiting.operation(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",path:"/v1/tasks",value:waitingStart);fatalError("cancelled task dispatched")}catch ProofError.denied{}catch{fatalError("unexpected")}}
  precondition(stopEntered.wait(timeout:.now()+2) == .success)
  let secondIntent=RequestIntent(hostID:host,deviceID:device,generation:1,scopeID:"project",scopeRevision:"one",action:"submit",method:"POST",path:"/v1/tasks",expiresAt:1020,payloadDigest:Data(SHA256.hash(data:secondTask)))
  do { _=try waiting.challenge(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",intent:secondIntent);fatalError("parallel approval") } catch ProofError.denied {}
  let stopIntent=RequestIntent(hostID:host,deviceID:device,generation:1,scopeID:"project",scopeRevision:"one",action:"stop",method:"POST",path:"/v1/tasks/stop",expiresAt:1020,payloadDigest:Data(SHA256.hash(data:statusPayload)))
  let stopChallenge=try waiting.challenge(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",intent:stopIntent),stopValue=SyntheticOperation(challenge:stopChallenge,signature:try key.signature(for:requestProofMessage(stopChallenge)).rawRepresentation,payload:statusPayload)
  let cancelled=try waiting.operation(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",path:"/v1/tasks/stop",value:stopValue);precondition(cancelled.status=="cancelled");stopRelease.signal();precondition(stopDone.wait(timeout:.now()+2) == .success)
  let denied=SyntheticRoutes(hostID:host,expectedHost:"mac.example",expectedOrigin:"https://atlas-desktop.joelr2.chatgpt.site",peer:peer,scope:("project","one"),sessionDeadline:100,clock:{now},wallClock:{1000},ownerConfirm:{_ in false})
  let deniedChallenge=try denied.challenge(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",intent:intent)
  let deniedSigned=SyntheticOperation(challenge:deniedChallenge,signature:try key.signature(for:requestProofMessage(deniedChallenge)).rawRepresentation,payload:task)
  do { _=try denied.operation(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",path:"/v1/tasks",value:deniedSigned);fatalError("denial") } catch ProofError.denied {}
  do { _=try denied.challenge(host:"mac.example",origin:"https://atlas-desktop.joelr2.chatgpt.site",method:"POST",intent:intent);fatalError("call after denial") } catch ProofError.denied {}
  precondition(denied.taskCount==0)
  now=200;precondition(server.taskCount==1);print("synthetic authenticated routes fixture ok")
 }
}
