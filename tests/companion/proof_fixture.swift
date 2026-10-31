import Foundation
import CryptoKit
@main struct Test {
 static func main() throws {
  var time=1.0;let host=UUID(),device=UUID();let privateKey=P256.Signing.PrivateKey()
  var peer=DeviceAuthority(deviceID:device,generation:1,signingKey:privateKey.publicKey.x963Representation,revoked:false)
  var scope=("project","one")
  let gate=RequestProofGate(hostID:host,sessionDeadline:100,clock:{time},wallClock:{1000},authority:{peer},scope:{scope})
  let intent=RequestIntent(hostID:host,deviceID:device,generation:1,scopeID:"project",scopeRevision:"one",action:"submit",method:"POST",path:"/v1/tasks",expiresAt:1020,payloadDigest:Data(SHA256.hash(data:Data("task".utf8))))
  let c=try gate.issue(intent);let sig=try privateKey.signature(for:requestProofMessage(c));try gate.verify(c,signature:sig.rawRepresentation)
  do { try gate.verify(c,signature:sig.rawRepresentation);fatalError("replay") } catch ProofError.replay {}
  let forged=try gate.issue(intent);let other=P256.Signing.PrivateKey();let bad=try other.signature(for:requestProofMessage(forged))
  do { try gate.verify(forged,signature:bad.rawRepresentation);fatalError("forged") } catch ProofError.denied {}
  let original=try gate.issue(intent);let originalSig=try privateKey.signature(for:requestProofMessage(original))
  let changedIntent=RequestIntent(hostID:host,deviceID:device,generation:1,scopeID:"project",scopeRevision:"one",action:"submit",method:"POST",path:"/v1/tasks/stop",expiresAt:1020,payloadDigest:intent.payloadDigest)
  do { try gate.verify(RequestChallenge(nonce:original.nonce,intent:changedIntent),signature:originalSig.rawRepresentation);fatalError("path tampering") } catch ProofError.denied {}
  let stale=try gate.issue(intent);let staleSig=try privateKey.signature(for:requestProofMessage(stale));peer=DeviceAuthority(deviceID:device,generation:2,signingKey:privateKey.publicKey.x963Representation,revoked:false)
  do { try gate.verify(stale,signature:staleSig.rawRepresentation);fatalError("old generation") } catch ProofError.denied {}
  peer=DeviceAuthority(deviceID:device,generation:1,signingKey:privateKey.publicKey.x963Representation,revoked:false)
  let changed=try gate.issue(intent);let changedSig=try privateKey.signature(for:requestProofMessage(changed));scope=("project","two")
  do { try gate.verify(changed,signature:changedSig.rawRepresentation);fatalError("scope changed") } catch ProofError.denied {}
  scope=("project","one");let expired=try gate.issue(intent);let expiredSig=try privateKey.signature(for:requestProofMessage(expired));time=32
  do { try gate.verify(expired,signature:expiredSig.rawRepresentation);fatalError("sleep expiry") } catch ProofError.expired {}
  peer=DeviceAuthority(deviceID:device,generation:1,signingKey:privateKey.publicKey.x963Representation,revoked:true)
  do { _=try gate.issue(intent);fatalError("revoked") } catch ProofError.denied {}
  print("synthetic request proof fixture ok")
 }
}
