import Foundation
import CryptoKit
final class MemoryStorage:SecureDeviceStorage {let storageIdentifier=UUID().uuidString;var data:Data?;var failAfterWrite=false;var failBeforeWrite=false;func read()throws->Data?{data};func write(_ d:Data)throws{if failBeforeWrite{throw DeviceError.invalid};data=d;if failAfterWrite{throw DeviceError.invalid}};func delete()throws{data=nil}}
struct WireReply:Decodable {let signed:SignedResponse;let payload:Data}
struct AttemptReply:Decodable {let attemptID:UUID;let state:String}
@main struct Test {
 static func main()throws {try run(false);try run(true);try run(false,stopDuringApproval:true);try run(false,revokeFailure:1);try run(false,revokeFailure:2);try run(false,revokeFailure:3);try run(false,revokeFailure:4);try run(false,revokeFailure:5);try denied();try expired();print("strict HTTP pairing, fake task and lost-ack recovery fixture ok")}
 static func expired()throws {
  var now=1.0;let mac=P256.Signing.PrivateKey(),store=MemoryStorage(),h=try PairingHTTPHandler(hostID:UUID(),macKey:mac,expectedHost:"atlas.example",expectedOrigin:"https://atlas-desktop.joelr2.chatgpt.site",privateOrigin:"https://atlas.example",macName:"Mac",storage:store,journalStorage:MemoryStorage(),clock:{now},wallClock:{1000},ownerStarted:true,recoveryCheck:{true},ownerConfirm:{_ in true})
  let client=try EnrollmentPhone(challenge:h.challenge,expectedOrigin:"https://atlas.example",expectedMacFingerprint:try signingFingerprint(mac.publicKey.x963Representation),phoneName:"Phone")
  func request<T:Encodable>(_ path:String,_ value:T)throws->CompanionHTTPReply {let data=try JSONEncoder().encode(value),head="POST \(path) HTTP/1.1\r\nHost: atlas.example\r\nOrigin: https://atlas-desktop.joelr2.chatgpt.site\r\nContent-Type: application/json\r\nContent-Length: \(data.count)\r\n\r\n";return h.handle(Data(head.utf8)+data)}
  let join=try request("/v1/enrollment/join",client.response),attempt=try JSONDecoder().decode(AttemptReply.self,from:join.body);now=122
  let status=try request("/v1/enrollment/status",["attemptID":attempt.attemptID.uuidString]);precondition(status.code==403 && store.data==nil)
 }
 static func denied()throws {
  let mac=P256.Signing.PrivateKey(),store=MemoryStorage(),h=try PairingHTTPHandler(hostID:UUID(),macKey:mac,expectedHost:"atlas.example",expectedOrigin:"https://atlas-desktop.joelr2.chatgpt.site",privateOrigin:"https://atlas.example",macName:"Mac",storage:store,journalStorage:MemoryStorage(),clock:{1},wallClock:{1000},ownerStarted:true,recoveryCheck:{true},ownerConfirm:{_ in false})
  let client=try EnrollmentPhone(challenge:h.challenge,expectedOrigin:"https://atlas.example",expectedMacFingerprint:try signingFingerprint(mac.publicKey.x963Representation),phoneName:"Phone")
  func request<T:Encodable>(_ path:String,_ value:T)throws->CompanionHTTPReply {let data=try JSONEncoder().encode(value),head="POST \(path) HTTP/1.1\r\nHost: atlas.example\r\nOrigin: https://atlas-desktop.joelr2.chatgpt.site\r\nContent-Type: application/json\r\nContent-Length: \(data.count)\r\n\r\n";return h.handle(Data(head.utf8)+data)}
  let join=try request("/v1/enrollment/join",client.response),attempt=try JSONDecoder().decode(AttemptReply.self,from:join.body)
  do {try h.ownerApprove(attemptID:attempt.attemptID,code:client.code,fingerprint:try signingFingerprint(mac.publicKey.x963Representation),confirmed:false);fatalError("denial ignored")} catch EnrollmentError.denied {}
  let status=try request("/v1/enrollment/status",["attemptID":attempt.attemptID.uuidString]);precondition(status.code==403 && store.data==nil)
 }
 static func run(_ loseAck:Bool,stopDuringApproval:Bool=false,revokeFailure:Int=0)throws {
  let host=UUID(),phoneID=UUID(),mac=P256.Signing.PrivateKey(),phone=P256.Signing.PrivateKey(),store=MemoryStorage(),journal=MemoryStorage(),clock={1.0},wall={Int64(1000)}
  let expectedHost="atlas.example",origin="https://atlas-desktop.joelr2.chatgpt.site",macPub=mac.publicKey.x963Representation,phonePub=phone.publicKey.x963Representation
  var approvals=0
  let approvalEntered=DispatchSemaphore(value:0),approvalRelease=DispatchSemaphore(value:0),submissionDone=DispatchSemaphore(value:0)
  let h=try PairingHTTPHandler(hostID:host,macKey:mac,expectedHost:expectedHost,expectedOrigin:origin,privateOrigin:"https://atlas.example",macName:"Mac",storage:store,journalStorage:journal,clock:clock,wallClock:wall,ownerStarted:true,recoveryCheck:{true},ownerConfirm:{_ in approvals += 1;if stopDuringApproval {approvalEntered.signal();approvalRelease.wait()};return true})
  func request<T:Encodable>(_ path:String,_ value:T,extra:String="")throws->CompanionHTTPReply {
   let data=try JSONEncoder().encode(value),head="POST \(path) HTTP/1.1\r\nHost: \(expectedHost)\r\nOrigin: \(origin)\r\nContent-Type: application/json\r\nContent-Length: \(data.count)\r\n\(extra)\r\n"
   return h.handle(Data(head.utf8)+data)
  }
  let client=try EnrollmentPhone(challenge:h.challenge,expectedOrigin:"https://atlas.example",expectedMacFingerprint:try signingFingerprint(macPub),phoneName:"Phone")
  let join=try request("/v1/enrollment/join",client.response);precondition(join.code==200);let attempt=try JSONDecoder().decode(AttemptReply.self,from:join.body)
  let pending=try request("/v1/enrollment/status",["attemptID":attempt.attemptID.uuidString]);precondition(pending.code==200 && h.ownerComparison()?.1.code==client.code)
  try h.ownerApprove(attemptID:attempt.attemptID,code:client.code,fingerprint:try signingFingerprint(macPub),confirmed:true)
  let status=try request("/v1/enrollment/status",["attemptID":attempt.attemptID.uuidString]),envelope=try JSONDecoder().decode(PairingEnvelope.self,from:status.body),binding=enrollmentBinding(h.challenge,client.response)
  let approved=try openPairing(envelope,as:ApprovalStatus.self,role:"approval",binding:binding,key:client.channel);precondition(approved.state=="approved" && approved.attemptID==attempt.attemptID)
  let phoneProof=try phone.signature(for:identityProof(role:"phone",binding:binding,hostID:host,phoneID:phoneID,generation:1,macPublic:macPub,phonePublic:phonePub)),claim=IdentityClaim(deviceID:phoneID,generation:1,publicKey:phonePub,signature:phoneProof.rawRepresentation)
  let finish=try request("/v1/enrollment/finish",sealPairing(claim,role:"phone",binding:binding,key:client.channel));precondition(finish.code==200)
  let macEnvelope=try JSONDecoder().decode(PairingEnvelope.self,from:finish.body),macClaim=try openPairing(macEnvelope,as:IdentityClaim.self,role:"mac",binding:binding,key:client.channel)
  let macProof=try P256.Signing.ECDSASignature(rawRepresentation:macClaim.signature);precondition(mac.publicKey.isValidSignature(macProof,for:identityProof(role:"mac",binding:binding,hostID:host,phoneID:phoneID,generation:1,macPublic:macPub,phonePublic:phonePub)))
  let ackSignature=try phone.signature(for:identityProof(role:"ack",binding:binding,hostID:host,phoneID:phoneID,generation:1,macPublic:macPub,phonePublic:phonePub)),ack=try sealPairing(IdentityAck(signature:ackSignature.rawRepresentation),role:"ack",binding:binding,key:client.channel)
  store.failAfterWrite=loseAck
  let result=try request("/v1/enrollment/ack",ack)
  if loseAck {
   precondition(result.code==409 && store.data != nil);store.failAfterWrite=false
   let restarted=MacPairingVault(storage:store,clock:clock),descriptor=try restarted.inspectRecovery(phoneID)!,recovery=PairingRecovery(vault:restarted,clock:clock,recoveryCheck:{true})
   let c=try recovery.begin(displayed:descriptor,ownerReviewed:true),proof=try phone.signature(for:pairingRecoveryMessage(c)),receipt=try recovery.finish(c,signature:proof.rawRepresentation)
   let sig=try P256.Signing.ECDSASignature(rawRepresentation:receipt.signature);precondition(mac.publicKey.isValidSignature(sig,for:pairingReceiptMessage(receipt.descriptor)))
   let replayedAck=try request("/v1/enrollment/ack",ack);precondition(replayedAck.code==403)
   let beforeReview=try request("/v1/enrollment/recovery/challenge",["phoneID":phoneID.uuidString]);precondition(beforeReview.code==403)
   try h.ownerReviewRestart(confirmed:true,taskOutcomeReviewed:true)
   let inspected=try h.ownerRecoveryDescriptor(phoneID)!
   do {try h.ownerPrepareRecovery(inspected,confirmed:false);fatalError("unapproved recovery accepted")} catch {}
   try h.ownerPrepareRecovery(inspected,confirmed:true);precondition(h.ownerRecoveryCompleted()==nil)
   let challengeReply=try request("/v1/enrollment/recovery/challenge",["phoneID":phoneID.uuidString]);precondition(challengeReply.code==200)
   let challenge=try JSONDecoder().decode(RecoveryChallenge.self,from:challengeReply.body),signature=try phone.signature(for:pairingRecoveryMessage(challenge))
   struct Finish:Encodable {let challenge:RecoveryChallenge;let signature:Data}
   let finish=Finish(challenge:challenge,signature:signature.rawRepresentation),finished=try request("/v1/enrollment/recovery/finish",finish);precondition(finished.code==200)
   precondition(h.ownerRecoveryCompleted()==phoneID)
   let recovered=try JSONDecoder().decode(PairingReceipt.self,from:finished.body),recoveredSig=try P256.Signing.ECDSASignature(rawRepresentation:recovered.signature);precondition(mac.publicKey.isValidSignature(recoveredSig,for:pairingReceiptMessage(recovered.descriptor)))
   let replay=try request("/v1/enrollment/recovery/finish",finish);precondition(replay.code==403);return
  }
  precondition(result.code==200);let receiptEnvelope=try JSONDecoder().decode(PairingEnvelope.self,from:result.body),receipt=try openPairing(receiptEnvelope,as:PairingReceipt.self,role:"receipt",binding:binding,key:client.channel)
  let sig=try P256.Signing.ECDSASignature(rawRepresentation:receipt.signature);precondition(mac.publicKey.isValidSignature(sig,for:pairingReceiptMessage(receipt.descriptor)))
  if revokeFailure==4 || revokeFailure==5 {
   if revokeFailure==5 {journal.failBeforeWrite=true;do {try h.ownerPrepareRevocation(phoneID);fatalError("failed marker accepted")} catch {};journal.failBeforeWrite=false;do {try h.ownerRevoke(expectedGeneration:1,confirmed:true);fatalError("unprepared revoke accepted")} catch {};return}
   try h.ownerPrepareRevocation(phoneID);journal.failBeforeWrite=true
   do {try h.ownerRevoke(expectedGeneration:1,confirmed:true);fatalError("failed revocation write accepted")} catch {};journal.failBeforeWrite=false
   let restarted=try PairingHTTPHandler(hostID:host,macKey:mac,expectedHost:expectedHost,expectedOrigin:origin,privateOrigin:"https://atlas.example",macName:"Mac",storage:store,journalStorage:journal,clock:clock,wallClock:wall,ownerStarted:true,recoveryCheck:{true},ownerConfirm:{_ in true})
   try restarted.ownerReviewRestart(confirmed:true,taskOutcomeReviewed:true)
   do {try restarted.ownerSelectPhone(phoneID,confirmed:true);fatalError("failed idle revoke was lost")} catch {};return
  }
  do {try h.ownerStartSession(scope:("project","one"),deadline:100,confirmed:false);fatalError("session not approved")} catch ProofError.denied {}
  try h.ownerStartSession(scope:("project","one"),deadline:100,confirmed:true)
  do {try h.ownerStartSession(scope:("other","two"),deadline:100,confirmed:true);fatalError("scope replaced within session")} catch ProofError.denied {}
  let taskID=UUID(),payload=try JSONEncoder().encode(SyntheticTask(id:taskID,task:"synthetic"))
  let badPayload=Data("{\"id\":\"\(UUID().uuidString)\",\"task\":\"one\",\"task\":\"two\"}".utf8)
  let badIntent=RequestIntent(hostID:host,deviceID:phoneID,generation:1,scopeID:"project",scopeRevision:"one",action:"submit",method:"POST",path:"/v1/tasks",expiresAt:1020,payloadDigest:Data(SHA256.hash(data:badPayload)))
  let badChallengeReply=try request("/v1/session/challenge",["intent":badIntent]);let badChallenge=try JSONDecoder().decode(RequestChallenge.self,from:badChallengeReply.body)
  let badOperation=SyntheticOperation(challenge:badChallenge,signature:try phone.signature(for:requestProofMessage(badChallenge)).rawRepresentation,payload:badPayload)
  let rejectedPayload=try request("/v1/tasks",badOperation);precondition(rejectedPayload.code==403 && approvals==0)
  func op(_ action:String,_ path:String,_ payload:Data)throws->(CompanionHTTPReply,SyntheticOperation) {
   let intent=RequestIntent(hostID:host,deviceID:phoneID,generation:1,scopeID:"project",scopeRevision:"one",action:action,method:"POST",path:path,expiresAt:1020,payloadDigest:Data(SHA256.hash(data:payload)))
   let cReply=try request("/v1/session/challenge",["intent":intent]);precondition(cReply.code==200);let c=try JSONDecoder().decode(RequestChallenge.self,from:cReply.body)
   let value=SyntheticOperation(challenge:c,signature:try phone.signature(for:requestProofMessage(c)).rawRepresentation,payload:payload)
   return (try request(path,value),value)
  }
  if stopDuringApproval {
   DispatchQueue.global().async {defer{submissionDone.signal()};do {let result=try op("submit","/v1/tasks",payload);precondition(result.0.code==403)}catch{fatalError("submission failed unexpectedly")}}
   precondition(approvalEntered.wait(timeout:.now()+2) == .success)
   let stopPayload=try JSONEncoder().encode(SyntheticTask(id:taskID,task:nil)),(stopped,_)=try op("stop","/v1/tasks/stop",stopPayload)
   precondition(stopped.code==200);let stopWire=try JSONDecoder().decode(WireReply.self,from:stopped.body);precondition(stopWire.signed.intent.status=="cancelled")
   approvalRelease.signal();precondition(submissionDone.wait(timeout:.now()+2) == .success);return
  }
  let (sent,value)=try op("submit","/v1/tasks",payload);precondition(sent.code==200)
  let wire=try JSONDecoder().decode(WireReply.self,from:sent.body);try verifyResponse(wire.signed,pinnedMacKey:macPub,hostID:host,deviceID:phoneID,requestID:taskID,generation:1,action:"submit",method:"POST",path:"/v1/tasks",requestNonce:value.challenge.nonce,payload:wire.payload,wallClock:1000)
  let replayedTask=try request("/v1/tasks",value);precondition(replayedTask.code==403)
  let stopPayload=try JSONEncoder().encode(SyntheticTask(id:taskID,task:nil)),(stop,_)=try op("stop","/v1/tasks/stop",stopPayload);precondition(stop.code==200)
  if revokeFailure != 0 {
   store.failBeforeWrite = revokeFailure == 1;store.failAfterWrite = revokeFailure == 2;journal.failBeforeWrite = revokeFailure == 3
   do {try h.ownerRevoke(expectedGeneration:1,confirmed:true);fatalError("storage failure accepted")} catch {}
   store.failBeforeWrite=false;store.failAfterWrite=false;journal.failBeforeWrite=false
   let restarted=try PairingHTTPHandler(hostID:host,macKey:mac,expectedHost:expectedHost,expectedOrigin:origin,privateOrigin:"https://atlas.example",macName:"Mac",storage:store,journalStorage:journal,clock:clock,wallClock:wall,ownerStarted:true,recoveryCheck:{true},ownerConfirm:{_ in true})
   do {try restarted.ownerSelectPhone(phoneID,confirmed:true);fatalError("restart reconnected before review")} catch {}
   do {try restarted.ownerReviewRestart(confirmed:true,taskOutcomeReviewed:false);fatalError("unreviewed outcome accepted")} catch {}
   try restarted.ownerReviewRestart(confirmed:true,taskOutcomeReviewed:true)
   do {try restarted.ownerSelectPhone(phoneID,confirmed:true);fatalError("revoked phone reconnected")} catch {}
   return
  }
  try h.ownerRevoke(expectedGeneration:1,confirmed:true)
  let intent=RequestIntent(hostID:host,deviceID:phoneID,generation:1,scopeID:"project",scopeRevision:"one",action:"status",method:"POST",path:"/v1/tasks/status",expiresAt:1020,payloadDigest:Data(SHA256.hash(data:stopPayload)))
  let revokedChallenge=try request("/v1/session/challenge",["intent":intent]);precondition(revokedChallenge.code==403)
 }
}
