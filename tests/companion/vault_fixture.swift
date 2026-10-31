import Foundation
import CryptoKit
final class MemoryStorage:SecureDeviceStorage {let storageIdentifier=UUID().uuidString; var data:Data?;var fail=false,failAfterWrite=false;func read()throws->Data?{data};func write(_ value:Data)throws{if fail{throw DeviceError.invalid};data=value;if failAfterWrite{throw DeviceError.invalid}};func delete()throws{data=nil} }
@main struct Test {
 static func main() throws {
  let storage=MemoryStorage(),vault=MacPairingVault(storage:storage,clock:{1}),host=UUID(),phoneID=UUID(),mac=P256.Signing.PrivateKey(),phone=P256.Signing.PrivateKey()
  let clock={1.0},macPub=mac.publicKey.x963Representation,phonePub=phone.publicKey.x963Representation
  let enrollment=try EnrollmentHost(hostID:host,macSigningPublic:macPub,origin:"https://atlas.example",macName:"Mac",clock:clock)
  let client=try EnrollmentPhone(challenge:enrollment.challenge,expectedOrigin:"https://atlas.example",expectedMacFingerprint:try signingFingerprint(macPub),phoneName:"Phone")
  let compared=try enrollment.accept(client.response),approved=try enrollment.approve(displayedCode:compared.code,displayedMacFingerprint:try signingFingerprint(macPub),ownerConfirmed:true)
  let finish=try PairingCompletionHost(approved:approved,macKey:mac,clock:clock,ownerConfirmed:true)
  let phoneProof=try phone.signature(for:identityProof(role:"phone",binding:approved.binding,hostID:host,phoneID:phoneID,generation:1,macPublic:macPub,phonePublic:phonePub))
  let claim=IdentityClaim(deviceID:phoneID,generation:1,publicKey:phonePub,signature:phoneProof.rawRepresentation)
  _=try finish.accept(sealPairing(claim,role:"phone",binding:approved.binding,key:client.channel))
  let ackProof=try phone.signature(for:identityProof(role:"ack",binding:approved.binding,hostID:host,phoneID:phoneID,generation:1,macPublic:macPub,phonePublic:phonePub))
  let link=try finish.acknowledge(sealPairing(IdentityAck(signature:ackProof.rawRepresentation),role:"ack",binding:approved.binding,key:client.channel))
  let expiredStorage=MemoryStorage(),expiredVault=MacPairingVault(storage:expiredStorage,clock:{200})
  do {try expiredVault.enroll(link,macKey:mac,ownerConfirmed:true);fatalError("expired commit")} catch DeviceError.denied {};precondition(expiredStorage.data==nil)
  let uncertain=MemoryStorage(),first=MacPairingVault(storage:uncertain,clock:{1});uncertain.failAfterWrite=true
  do {try first.enroll(link,macKey:mac,ownerConfirmed:true);fatalError("lost acknowledgement")} catch DeviceError.invalid {}
  precondition(uncertain.data != nil);uncertain.failAfterWrite=false
  var recoveryTime=1.0
  let restarted=MacPairingVault(storage:uncertain,clock:{1}),descriptor=try restarted.inspectRecovery(phoneID)!,recovery=PairingRecovery(vault:restarted,clock:{recoveryTime},recoveryCheck:{true})
  do {_=try recovery.begin(displayed:descriptor,ownerReviewed:false);fatalError("unreviewed recovery")} catch DeviceError.denied {}
  let rejected=try recovery.begin(displayed:descriptor,ownerReviewed:true),other=P256.Signing.PrivateKey(),bad=try other.signature(for:pairingRecoveryMessage(rejected))
  do {_=try recovery.finish(rejected,signature:bad.rawRepresentation);fatalError("forged recovery")} catch DeviceError.denied {}
  let recovered=try recovery.begin(displayed:descriptor,ownerReviewed:true),good=try phone.signature(for:pairingRecoveryMessage(recovered)),receipt=try recovery.finish(recovered,signature:good.rawRepresentation)
  let receiptSig=try P256.Signing.ECDSASignature(rawRepresentation:receipt.signature);precondition(mac.publicKey.isValidSignature(receiptSig,for:pairingReceiptMessage(receipt.descriptor)))
  do {_=try recovery.finish(recovered,signature:good.rawRepresentation);fatalError("replayed recovery")} catch EnrollmentError.replay {}
  let expiring=try recovery.begin(displayed:descriptor,ownerReviewed:true),expiringSig=try phone.signature(for:pairingRecoveryMessage(expiring));recoveryTime=32
  do {_=try recovery.finish(expiring,signature:expiringSig.rawRepresentation);fatalError("expired recovery")} catch DeviceError.denied {}
  recoveryTime=1;let cancelled=try recovery.begin(displayed:descriptor,ownerReviewed:true),cancelledSig=try phone.signature(for:pairingRecoveryMessage(cancelled));recovery.cancel()
  do {_=try recovery.finish(cancelled,signature:cancelledSig.rawRepresentation);fatalError("cancelled recovery")} catch EnrollmentError.replay {}
  do { try vault.enroll(link,macKey:mac,ownerConfirmed:false);fatalError("unapproved") } catch DeviceError.denied {};precondition(storage.data==nil)
  storage.fail=true;do { try vault.enroll(link,macKey:mac,ownerConfirmed:true);fatalError("write failure") } catch DeviceError.invalid {};precondition(storage.data==nil)
  storage.fail=false;try vault.enroll(link,macKey:mac,ownerConfirmed:true);let active=try vault.authority(phoneID);precondition(active?.revoked==false)
  let devices=try vault.phones();precondition(devices.count==1 && devices[0].name=="Phone")
  let proofGate=RequestProofGate(hostID:host,sessionDeadline:100,clock:{1},wallClock:{1000},authority:{try? vault.authority(phoneID)},scope:{("project","one")})
  let intent=RequestIntent(hostID:host,deviceID:phoneID,generation:1,scopeID:"project",scopeRevision:"one",action:"submit",method:"POST",path:"/v1/tasks",expiresAt:1020,payloadDigest:Data(SHA256.hash(data:Data("test".utf8))))
  let challenge=try proofGate.issue(intent),signature=try phone.signature(for:requestProofMessage(challenge))
  let replacement=P256.Signing.PrivateKey(),newPublic=replacement.publicKey.x963Representation,rotation=rotationProofMessage(hostID:host,phoneID:phoneID,oldGeneration:1,oldPublic:phonePub,newPublic:newPublic)
  let oldProof=try phone.signature(for:rotation),newProof=try replacement.signature(for:rotation)
  do { try vault.rotate(phoneID,expectedGeneration:1,newPublic:newPublic,oldSignature:oldProof.rawRepresentation,newSignature:oldProof.rawRepresentation,ownerConfirmed:true);fatalError("invalid rotation proof") } catch DeviceError.denied {}
  try vault.rotate(phoneID,expectedGeneration:1,newPublic:newPublic,oldSignature:oldProof.rawRepresentation,newSignature:newProof.rawRepresentation,ownerConfirmed:true)
  do { try proofGate.verify(challenge,signature:signature.rawRepresentation);fatalError("old generation") } catch ProofError.denied {}
  let current=RequestIntent(hostID:host,deviceID:phoneID,generation:2,scopeID:"project",scopeRevision:"one",action:"submit",method:"POST",path:"/v1/tasks",expiresAt:1020,payloadDigest:intent.payloadDigest)
  let currentChallenge=try proofGate.issue(current),currentSignature=try replacement.signature(for:requestProofMessage(currentChallenge))
  do { try vault.revoke(phoneID,expectedGeneration:1,ownerConfirmed:false);fatalError("unapproved revoke") } catch DeviceError.denied {}
  try vault.revoke(phoneID,expectedGeneration:2,ownerConfirmed:true);let revoked=try vault.authority(phoneID);precondition(revoked?.revoked==true && revoked?.generation==3)
  do { try proofGate.verify(currentChallenge,signature:currentSignature.rawRepresentation);fatalError("revoked session") } catch ProofError.denied {}
  do { try vault.revoke(phoneID,expectedGeneration:1,ownerConfirmed:true);fatalError("stale revoke") } catch DeviceError.stale {}
  print("synthetic pairing vault fixture ok")
 }
}
