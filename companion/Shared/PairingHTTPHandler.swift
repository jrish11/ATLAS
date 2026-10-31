import Foundation
import CryptoKit

struct CompanionHTTPReply {let code:Int;let headers:[String:String];let body:Data}
private struct Attempt:Codable {let attemptID:UUID}
private struct JoinReply:Codable {let attemptID:UUID;let state:String}
private struct ErrorReply:Codable {let error:String}
private struct ChallengeBody:Codable {let intent:RequestIntent}
private struct RecoveryLookup:Codable {let phoneID:UUID}
private struct RecoveryFinish:Codable {let challenge:RecoveryChallenge;let signature:Data}
private struct SignedWire:Codable {let signed:SignedResponse;let payload:Data}

/// Disabled HTTP handler. It opens no socket, creates no persistent identity,
/// and requires injected storage. Only its local owner* methods may approve
/// enrollment or sessions. The caller must bind loopback only after explicit
/// owner activation and must pass one complete bounded request to handle().
/// A production caller must inject RegistryRoutes and its private supervisor
/// transport. The default route is synthetic and cannot dispatch tasks.
final class PairingHTTPHandler {
 private let routeFactory: ((UUID,String,String,DeviceAuthority,(String,String),Double,@escaping ()->Double,@escaping ()->Int64)->CompanionTaskRoutes)?
 private let lock=NSLock(),parser:StrictHTTP,coordinator:NativeEnrollmentCoordinator,vault:MacPairingVault,journal:RevocationJournal,macKey:P256.Signing.PrivateKey,hostID:UUID,clock:()->Double,wallClock:()->Int64,ownerConfirm:(String)->Bool,recoveryCheck:()->Bool
 private lazy var recovery=PairingRecovery(vault:vault,clock:clock,recoveryCheck:{[weak self] in guard let self else{return false};return (try? self.journal.read().state)=="clear" && self.recoveryCheck()})
 private var recoveryChallenge:RecoveryChallenge?,recoveryCompletedID:UUID?
 private var attempt:UUID?,comparison:EnrollmentComparison?,approved:ApprovedEnrollment?,completion:PairingCompletionHost?,phoneID:UUID?,routes:CompanionTaskRoutes?,uncertain=false,restartReviewed=false
 init(hostID:UUID,macKey:P256.Signing.PrivateKey,expectedHost:String,expectedOrigin:String,privateOrigin:String,macName:String,storage:SecureDeviceStorage,journalStorage:SecureDeviceStorage,clock:@escaping ()->Double,wallClock:@escaping ()->Int64,ownerStarted:Bool,routeFactory:((UUID,String,String,DeviceAuthority,(String,String),Double,@escaping ()->Double,@escaping ()->Int64)->CompanionTaskRoutes)? = nil,recoveryCheck:@escaping ()->Bool,ownerConfirm:@escaping (String)->Bool)throws {
  guard ownerStarted,storage.storageIdentifier != journalStorage.storageIdentifier,expectedOrigin=="https://atlas-desktop.joelr2.chatgpt.site",let origin=URLComponents(string:privateOrigin),let host=origin.host,
        expectedHost==host+(origin.port.map{":"+String($0)} ?? "") else {throw EnrollmentError.denied}
  self.routeFactory=routeFactory;self.hostID=hostID;self.macKey=macKey;self.clock=clock;self.wallClock=wallClock;self.ownerConfirm=ownerConfirm;self.recoveryCheck=recoveryCheck
  parser=StrictHTTP(expectedHost:expectedHost,expectedOrigin:expectedOrigin)
  vault=MacPairingVault(storage:storage,clock:clock)
  journal=RevocationJournal(storage:journalStorage,hostID:hostID)
  try journal.prepare(fresh:try vault.phones().isEmpty)
  coordinator=try NativeEnrollmentCoordinator(hostID:hostID,macPublic:macKey.publicKey.x963Representation,origin:privateOrigin,macName:macName,clock:clock,ownerStarted:true)
 }
 var challenge:EnrollmentChallenge {coordinator.challenge}
 func ownerCanCopyChallenge()->Bool {lock.lock();defer{lock.unlock()};return !uncertain && coordinator.canCopyChallenge()}
 // Native-only. HTTP has no corresponding endpoint or boolean approval field.
 func ownerApprove(attemptID:UUID,code:String,fingerprint:String,confirmed:Bool)throws {
  lock.lock();defer{lock.unlock()};try coordinator.ownerDecision(attemptID:attemptID,displayedCode:code,displayedMacFingerprint:fingerprint,ownerConfirmed:confirmed)
 }
 func ownerPairingUncertain()->Bool {lock.lock();defer{lock.unlock()};return uncertain}
 func ownerRecoveryDescriptor(_ id:UUID)throws->RecoveryDescriptor? {lock.lock();defer{lock.unlock()};return try vault.inspectRecovery(id)}
 func ownerPrepareRecovery(_ descriptor:RecoveryDescriptor,confirmed:Bool)throws {
  lock.lock();defer{lock.unlock()};guard confirmed,restartReviewed,!uncertain,routes==nil,descriptor.hostID==hostID else {throw DeviceError.denied}
  recoveryChallenge=nil;recoveryCompletedID=nil;recoveryChallenge=try recovery.begin(displayed:descriptor,ownerReviewed:true)
 }
 func ownerCancelRecovery(){lock.lock();recovery.cancel();recoveryChallenge=nil;recoveryCompletedID=nil;lock.unlock()}
 func ownerRecoveryCompleted()->UUID? {lock.lock();defer{lock.unlock()};return recoveryCompletedID}
 func ownerCurrentPhone()->UUID? {lock.lock();defer{lock.unlock()};return phoneID}
 func ownerPhones()throws->[PairedPhone] {lock.lock();defer{lock.unlock()};return try vault.phones()}
 func ownerComparison()->(UUID,EnrollmentComparison)? {lock.lock();defer{lock.unlock()};guard let id=attempt,let c=comparison else{return nil};return(id,c)}
 func ownerStartSession(scope:(String,String),deadline:Double,confirmed:Bool)throws {
  lock.lock();defer{lock.unlock()};guard confirmed,restartReviewed,!uncertain,routes==nil,let id=phoneID,let peer=try vault.authority(id),!peer.revoked,deadline>clock(),deadline-clock()<=3600 else {throw ProofError.denied}
  try journal.beginSession(peer)
  if let routeFactory {routes=routeFactory(hostID,parser.expectedHost,parser.expectedOrigin,peer,scope,deadline,clock,wallClock);return}
  routes=SyntheticRoutes(hostID:hostID,expectedHost:parser.expectedHost,expectedOrigin:parser.expectedOrigin,peer:peer,scope:scope,sessionDeadline:deadline,clock:clock,wallClock:wallClock,ownerConfirm:ownerConfirm)
 }
 func ownerSelectPhone(_ id:UUID,confirmed:Bool)throws {
  lock.lock();defer{lock.unlock()};guard confirmed,restartReviewed,!uncertain,routes==nil,try journal.read().state=="clear",let peer=try vault.authority(id),!peer.revoked else {throw DeviceError.denied};phoneID=id
 }
 // Stop new verified requests before inspecting the real task barrier. A
 // quiet, barrier-free stop preserves pairing; anything uncertain retains the
 // durable active marker and is conservatively revoked during restart review.
 func ownerEndSession() {
  lock.lock();guard let current=routes else {lock.unlock();return};routes=nil
  let quiet=current.quiesce()
  if quiet,!uncertain,let marker=try? journal.read(),marker.state=="active",let stopped=try? journal.markStopped(expected:marker),recoveryCheck() {try? journal.clear(expected:stopped)}
  lock.unlock();current.shutdown()
 }
 // Persist a conservative active marker before presenting an idle-phone
 // revoke confirmation. If storage is unavailable, do not ask for or accept
 // that confirmation: otherwise a failed write could lose the owner's intent.
 func ownerPrepareRevocation(_ id:UUID)throws {
  lock.lock();defer{lock.unlock()};guard restartReviewed,!uncertain,routes==nil,let peer=try vault.authority(id),!peer.revoked else {throw DeviceError.denied}
  try journal.beginSession(peer);phoneID=id
 }
 func ownerCancelPreparedRevocation()throws {
  lock.lock();defer{lock.unlock()};guard !uncertain,routes==nil,let id=phoneID else {throw DeviceError.denied}
  let marker=try journal.read();guard marker.state=="active",marker.phoneID==id.uuidString.lowercased() else {throw DeviceError.denied};try journal.clear(expected:marker)
 }
 func ownerRevoke(expectedGeneration:UInt64,confirmed:Bool)throws {
  lock.lock();defer{lock.unlock()};guard confirmed,let id=phoneID,let peer=try vault.authority(id),!peer.revoked,peer.generation==expectedGeneration else {throw DeviceError.denied}
  let marker=try journal.read();guard marker.state=="active",marker.phoneID==id.uuidString.lowercased(),marker.generation==expectedGeneration else {throw DeviceError.denied}
  try routes?.revoke(ownerConfirmed:true);routes=nil;uncertain=true
  try journal.beginRevocation(peer)
  try vault.revoke(id,expectedGeneration:expectedGeneration,ownerConfirmed:true)
  let completed=try journal.read();try journal.clear(expected:completed);uncertain=false
 }
 // Native-only. A caller must inspect the durable task receipt and confirm;
 // `recoveryCheck` must independently reject an unresolved task barrier.
 func ownerReviewRestart(confirmed:Bool,taskOutcomeReviewed:Bool)throws {
  lock.lock();defer{lock.unlock()};guard confirmed,taskOutcomeReviewed,routes==nil,recoveryCheck() else {throw DeviceError.denied}
  let marker=try journal.read()
  if marker.state=="revoking" || marker.state=="active" {
   guard let id=UUID(uuidString:marker.phoneID),let peer=try vault.authority(id) else {throw DeviceError.invalid}
   if !peer.revoked && peer.generation==marker.generation {try vault.revoke(id,expectedGeneration:marker.generation,ownerConfirmed:true)}
   else {guard peer.revoked,marker.generation<UInt64.max,peer.generation==marker.generation+1 else {throw DeviceError.stale}}
  }
  if marker.state != "clear" {try journal.clear(expected:marker)}
  uncertain=false;restartReviewed=true
 }
 private func exact<T:Decodable>(_ type:T.Type,_ data:Data,_ keys:Set<String>)throws->T {
  _=try strictJSONObject(data,keys:keys)
  return try JSONDecoder().decode(type,from:data)
 }
 private var intentKeys:Set<String> { ["hostID","deviceID","generation","scopeID","scopeRevision","action","method","path","expiresAt","payloadDigest"] }
 private func validateIntent(_ object:Any?)throws {
  guard let value=object as? [String:Any],Set(value.keys)==intentKeys else {throw StrictHTTPError.invalid}
 }
 private func reply<T:Encodable>(_ value:T,_ code:Int=200)throws->CompanionHTTPReply {
  var headers=parser.preflightHeaders();headers["Content-Type"]="application/json";return CompanionHTTPReply(code:code,headers:headers,body:try JSONEncoder().encode(value))
 }
 private func taskOperation(_ req:StrictHTTPRequest)throws->CompanionHTTPReply {
  lock.lock();let current=routes;lock.unlock();guard let routes=current else {throw ProofError.denied}
  let outer=try strictJSONObject(req.body,keys:["challenge","signature","payload"])
  guard let challenge=outer["challenge"] as? [String:Any],Set(challenge.keys)==Set(["nonce","intent"]) else {throw StrictHTTPError.invalid};try validateIntent(challenge["intent"])
  let op=try exact(SyntheticOperation.self,req.body,["challenge","signature","payload"])
  let payloadKeys:Set<String> = op.challenge.intent.action == "submit" ? ["id","task"] : ["id"]
  _=try strictJSONObject(op.payload,keys:payloadKeys)
  let result=try routes.operation(host:parser.expectedHost,origin:parser.expectedOrigin,method:req.method,path:req.path,value:op),payload=try JSONEncoder().encode(result),i=op.challenge.intent
  let response=ResponseIntent(hostID:i.hostID,deviceID:i.deviceID,requestID:result.id,generation:i.generation,action:i.action,method:req.method,path:req.path,status:result.status,payloadDigest:Data(SHA256.hash(data:payload)),requestNonce:op.challenge.nonce,expiresAt:i.expiresAt)
  return try reply(SignedWire(signed:signResponse(response,key:macKey),payload:payload))
 }
 func handle(_ raw:Data)->CompanionHTTPReply {
  do {
   let req=try parser.parse(raw)
   if req.method=="OPTIONS" {return CompanionHTTPReply(code:204,headers:parser.preflightHeaders(),body:Data())}
   if ["/v1/tasks","/v1/tasks/status","/v1/tasks/stop"].contains(req.path) {return try taskOperation(req)}
   lock.lock();defer{lock.unlock()}
   switch req.path {
   case "/v1/enrollment/join":
    guard attempt==nil,!uncertain,try journal.read().state=="clear",recoveryCheck(),(try restartReviewed || vault.phones().isEmpty) else {throw EnrollmentError.replay}
    let response=try exact(EnrollmentResponse.self,req.body,["phoneName","nonce","phoneEphemeral"]),joined=try coordinator.join(response)
    attempt=joined.0;comparison=joined.1;return try reply(JoinReply(attemptID:joined.0,state:"pending"))
   case "/v1/enrollment/status":
    let value=try exact(Attempt.self,req.body,["attemptID"])
    switch coordinator.poll(value.attemptID) {
    case .pending:return try reply(JoinReply(attemptID:value.attemptID,state:"pending"))
    case .approved(let envelope):return try reply(envelope)
    case .denied,.expired:throw EnrollmentError.denied
    }
   case "/v1/enrollment/finish":
    guard let id=attempt,completion==nil,!uncertain else {throw EnrollmentError.denied}
    let envelope=try exact(PairingEnvelope.self,req.body,["iv","ciphertext"]),value=try coordinator.takeApproved(id)
    approved=value;let worker=try PairingCompletionHost(approved:value,macKey:macKey,clock:clock,ownerConfirmed:true);completion=worker
    return try reply(worker.accept(envelope))
   case "/v1/enrollment/ack":
    guard let worker=completion,let value=approved,!uncertain else {throw EnrollmentError.denied}
    let envelope=try exact(PairingEnvelope.self,req.body,["iv","ciphertext"]),link=try worker.acknowledge(envelope)
    completion=nil
    do {
     let receipt=try vault.enroll(link,macKey:macKey,ownerConfirmed:true);phoneID=link.phoneID;restartReviewed=true
     return try reply(sealPairing(receipt,role:"receipt",binding:value.binding,key:value.channel))
    } catch {uncertain=true;return try reply(ErrorReply(error:"outcome-unknown"),409)}
   case "/v1/enrollment/recovery/challenge":
    let value=try exact(RecoveryLookup.self,req.body,["phoneID"])
    guard restartReviewed,!uncertain,routes==nil,let challenge=recoveryChallenge,challenge.descriptor.phoneID==value.phoneID else {throw DeviceError.denied}
    return try reply(challenge)
   case "/v1/enrollment/recovery/finish":
    let outer=try strictJSONObject(req.body,keys:["challenge","signature"])
    guard let c=outer["challenge"] as? [String:Any],Set(c.keys)==Set(["descriptor","nonce"]),let d=c["descriptor"] as? [String:Any],Set(d.keys)==Set(["hostID","phoneID","phoneName","generation","binding","macPublic","phonePublic"]) else {throw StrictHTTPError.invalid}
    let value=try exact(RecoveryFinish.self,req.body,["challenge","signature"])
    guard restartReviewed,!uncertain,routes==nil,recoveryChallenge != nil else {throw DeviceError.denied}
    recoveryChallenge=nil;let receipt=try recovery.finish(value.challenge,signature:value.signature);phoneID=receipt.descriptor.phoneID;recoveryCompletedID=receipt.descriptor.phoneID
    return try reply(receipt)
   case "/v1/session/challenge":
    guard let routes=routes else {throw ProofError.denied}
    let outer=try strictJSONObject(req.body,keys:["intent"]);try validateIntent(outer["intent"])
    let value=try exact(ChallengeBody.self,req.body,["intent"])
    return try reply(routes.challenge(host:parser.expectedHost,origin:parser.expectedOrigin,method:req.method,intent:value.intent))
   default:throw StrictHTTPError.invalid
   }
  } catch {return CompanionHTTPReply(code:403,headers:["Cache-Control":"no-store"],body:(try? JSONEncoder().encode(ErrorReply(error:"rejected"))) ?? Data())}
 }
}
