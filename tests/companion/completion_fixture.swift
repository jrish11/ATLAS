import Foundation
import CryptoKit
@main struct Test {
 static func main() throws {
  var now=1.0;let hostID=UUID(),phoneID=UUID(),mac=P256.Signing.PrivateKey(),phone=P256.Signing.PrivateKey()
  let host=try EnrollmentHost(hostID:hostID,macSigningPublic:mac.publicKey.x963Representation,origin:"https://atlas.example",macName:"Mac",clock:{now})
  let client=try EnrollmentPhone(challenge:host.challenge,expectedOrigin:"https://atlas.example",expectedMacFingerprint:try signingFingerprint(host.challenge.macSigningPublic),phoneName:"Phone");let compare=try host.accept(client.response)
  let approved=try host.approve(displayedCode:compare.code,displayedMacFingerprint:try signingFingerprint(host.challenge.macSigningPublic),ownerConfirmed:true),binding=approved.binding,macPub=mac.publicKey.x963Representation,phonePub=phone.publicKey.x963Representation
  let approval=try sealPairing(["state":"approved"],role:"approval",binding:binding,key:approved.channel)
  do { _=try openPairing(approval,as:[String:String].self,role:"mac",binding:binding,key:client.channel);fatalError("cross-role envelope") } catch {}
  func packed(_ fields:[Data])->Data {var out=Data();for f in fields{var n=UInt32(f.count).bigEndian;withUnsafeBytes(of:&n){out.append(contentsOf:$0)};out.append(f)};return out}
  let aad=packed([Data("atlas-enrollment-aead-v1".utf8),Data("ack".utf8),binding]),duplicate=Data("{\"signature\":\"AA==\",\"signature\":\"AA==\"}".utf8)
  let badBox=try AES.GCM.seal(duplicate,using:client.channel,authenticating:aad),badEnvelope=PairingEnvelope(iv:Data(badBox.nonce),ciphertext:badBox.ciphertext+badBox.tag)
  do { _=try openPairing(badEnvelope,as:IdentityAck.self,role:"ack",binding:binding,key:approved.channel);fatalError("duplicate encrypted JSON") } catch is StrictHTTPError {}
  let finalizer=try PairingCompletionHost(approved:approved,macKey:mac,clock:{now},ownerConfirmed:true)
  let proof=try phone.signature(for:identityProof(role:"phone",binding:binding,hostID:hostID,phoneID:phoneID,generation:1,macPublic:macPub,phonePublic:phonePub))
  let claim=IdentityClaim(deviceID:phoneID,generation:1,publicKey:phonePub,signature:proof.rawRepresentation)
  let sealed=try sealPairing(claim,role:"phone",binding:binding,key:client.channel),reply=try finalizer.accept(sealed)
  let macClaim=try openPairing(reply,as:IdentityClaim.self,role:"mac",binding:binding,key:client.channel)
  let macSig=try P256.Signing.ECDSASignature(rawRepresentation:macClaim.signature)
  precondition(mac.publicKey.isValidSignature(macSig,for:identityProof(role:"mac",binding:binding,hostID:hostID,phoneID:phoneID,generation:1,macPublic:macPub,phonePublic:phonePub)))
  let ackSig=try phone.signature(for:identityProof(role:"ack",binding:binding,hostID:hostID,phoneID:phoneID,generation:1,macPublic:macPub,phonePublic:phonePub))
  let ack=try sealPairing(IdentityAck(signature:ackSig.rawRepresentation),role:"ack",binding:binding,key:client.channel),link=try finalizer.acknowledge(ack)
  precondition(link.phoneID==phoneID && link.macPublic==macPub)
  do { _=try finalizer.acknowledge(ack);fatalError("replay") } catch EnrollmentError.replay {}
  do { _=try PairingCompletionHost(approved:approved,macKey:mac,clock:{now},ownerConfirmed:true);fatalError("reused approval") } catch EnrollmentError.replay {}
  let fresh=try EnrollmentHost(hostID:hostID,macSigningPublic:macPub,origin:"https://atlas.example",macName:"Mac",clock:{now})
  let freshClient=try EnrollmentPhone(challenge:fresh.challenge,expectedOrigin:"https://atlas.example",expectedMacFingerprint:try signingFingerprint(macPub),phoneName:"Phone"),freshCompare=try fresh.accept(freshClient.response)
  let freshApproval=try fresh.approve(displayedCode:freshCompare.code,displayedMacFingerprint:try signingFingerprint(macPub),ownerConfirmed:true)
  let other=try PairingCompletionHost(approved:freshApproval,macKey:mac,clock:{now},ownerConfirmed:true)
  let freshSealed=try sealPairing(claim,role:"phone",binding:freshApproval.binding,key:freshClient.channel)
  var corrupted=freshSealed.ciphertext;corrupted[corrupted.startIndex] ^= 1
  do { _=try other.accept(PairingEnvelope(iv:freshSealed.iv,ciphertext:corrupted));fatalError("tampered") } catch {}
  let lapse=try EnrollmentHost(hostID:hostID,macSigningPublic:macPub,origin:"https://atlas.example",macName:"Mac",clock:{now})
  let lapseClient=try EnrollmentPhone(challenge:lapse.challenge,expectedOrigin:"https://atlas.example",expectedMacFingerprint:try signingFingerprint(macPub),phoneName:"Phone"),lapseCompare=try lapse.accept(lapseClient.response)
  let lapseApproval=try lapse.approve(displayedCode:lapseCompare.code,displayedMacFingerprint:try signingFingerprint(macPub),ownerConfirmed:true)
  do { _=try PairingCompletionHost(approved:lapseApproval,macKey:mac,clock:{now},ownerConfirmed:false);fatalError("denial") } catch EnrollmentError.denied {}
  do { _=try PairingCompletionHost(approved:lapseApproval,macKey:mac,clock:{now},ownerConfirmed:true);fatalError("denial replay") } catch EnrollmentError.replay {}
  print("synthetic pairing completion fixture ok")
 }
}
