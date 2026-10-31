import Foundation
import CryptoKit

// Synthetic, disabled completion primitive. It verifies possession of each
// P-256 signing key inside the SAS-confirmed AES-GCM channel. It never writes
// Keychain, IndexedDB, or any network. Durable two-phase recovery is not yet
// implemented, so callers must not activate this as a persistent pairing.
struct PairingEnvelope: Codable { let iv:Data;let ciphertext:Data }
struct IdentityClaim: Codable { let deviceID:UUID;let generation:UInt64;let publicKey:Data;let signature:Data }
struct IdentityAck: Codable { let signature:Data }
struct VerifiedLink {
    let hostID:UUID;let phoneID:UUID;let phoneName:String;let phonePublic:Data;let macPublic:Data;let generation:UInt64;let binding:Data;let deadline:Double
    fileprivate init(hostID:UUID,phoneID:UUID,phoneName:String,phonePublic:Data,macPublic:Data,generation:UInt64,binding:Data,deadline:Double) { self.hostID=hostID;self.phoneID=phoneID;self.phoneName=phoneName;self.phonePublic=phonePublic;self.macPublic=macPublic;self.generation=generation;self.binding=binding;self.deadline=deadline }
}
private func packed(_ fields:[Data])->Data {
    var out=Data();for field in fields { var count=UInt32(field.count).bigEndian;withUnsafeBytes(of:&count) { out.append(contentsOf:$0) };out.append(field) };return out
}
func identityProof(role:String,binding:Data,hostID:UUID,phoneID:UUID,generation:UInt64,macPublic:Data,phonePublic:Data)->Data {
    packed([Data("atlas-identity-proof-v1".utf8),Data(role.utf8),binding,Data(hostID.uuidString.lowercased().utf8),Data(phoneID.uuidString.lowercased().utf8),Data(String(generation).utf8),macPublic,phonePublic])
}
private func associated(_ role:String,_ binding:Data)->Data { packed([Data("atlas-enrollment-aead-v1".utf8),Data(role.utf8),binding]) }
func sealPairing<T:Encodable>(_ value:T,role:String,binding:Data,key:SymmetricKey)throws -> PairingEnvelope {
    guard binding.count==32,["approval","phone","mac","ack","receipt"].contains(role) else { throw EnrollmentError.invalid }
    let sealed=try AES.GCM.seal(JSONEncoder().encode(value),using:key,authenticating:associated(role,binding))
    return PairingEnvelope(iv:Data(sealed.nonce),ciphertext:sealed.ciphertext+sealed.tag)
}
func openPairing<T:Decodable>(_ envelope:PairingEnvelope,as:T.Type,role:String,binding:Data,key:SymmetricKey)throws->T {
    guard binding.count==32,envelope.iv.count==12,envelope.ciphertext.count>=16,envelope.ciphertext.count<=8192,["approval","phone","mac","ack","receipt"].contains(role) else { throw EnrollmentError.invalid }
    let nonce=try AES.GCM.Nonce(data:envelope.iv),payload=envelope.ciphertext.dropLast(16),tag=envelope.ciphertext.suffix(16)
    let box=try AES.GCM.SealedBox(nonce:nonce,ciphertext:payload,tag:tag)
    let plaintext=try AES.GCM.open(box,using:key,authenticating:associated(role,binding))
    let expected:Set<String>
    switch role {
    case "approval":expected=["attemptID","state"]
    case "phone","mac":expected=["deviceID","generation","publicKey","signature"]
    case "ack":expected=["signature"]
    case "receipt":expected=["descriptor","signature"]
    default:throw EnrollmentError.invalid
    }
    let object=try strictJSONObject(plaintext,keys:expected)
    if role=="receipt" {
        guard let descriptor=object["descriptor"] as? [String:Any],Set(descriptor.keys)==Set(["hostID","phoneID","phoneName","generation","binding","macPublic","phonePublic"]) else {throw EnrollmentError.invalid}
    }
    return try JSONDecoder().decode(T.self,from:plaintext)
}
final class PairingCompletionHost {
    private let lock=NSLock(), channel:SymmetricKey,binding:Data,hostID:UUID,phoneName:String,macKey:P256.Signing.PrivateKey,clock:()->Double,deadline:Double
    private var pending:VerifiedLink?;private var state=0
    init(approved:ApprovedEnrollment,macKey:P256.Signing.PrivateKey,clock:@escaping ()->Double,ownerConfirmed:Bool) throws {
        // A denial or invalid/expired attempt also consumes this approval.
        try approved.consume()
        guard ownerConfirmed,approved.binding.count==32,macKey.publicKey.x963Representation==approved.macSigningPublic,clock().isFinite,approved.deadline>clock(),approved.deadline-clock()<=120 else { throw EnrollmentError.denied }
        self.channel=approved.channel;self.binding=approved.binding;self.hostID=approved.hostID;self.phoneName=approved.phoneName;self.macKey=macKey;self.clock=clock;self.deadline=approved.deadline
    }
    func accept(_ envelope:PairingEnvelope)throws->PairingEnvelope {
        lock.lock();defer{lock.unlock()};guard state==0 else { throw EnrollmentError.replay };state=3
        guard clock()<deadline else { throw EnrollmentError.expired }
        let claim=try openPairing(envelope,as:IdentityClaim.self,role:"phone",binding:binding,key:channel)
        guard claim.generation==1,let phone=try? P256.Signing.PublicKey(x963Representation:claim.publicKey),let sig=try? P256.Signing.ECDSASignature(rawRepresentation:claim.signature),
              phone.isValidSignature(sig,for:identityProof(role:"phone",binding:binding,hostID:hostID,phoneID:claim.deviceID,generation:1,macPublic:macKey.publicKey.x963Representation,phonePublic:claim.publicKey)) else { throw EnrollmentError.denied }
        let link=VerifiedLink(hostID:hostID,phoneID:claim.deviceID,phoneName:phoneName,phonePublic:claim.publicKey,macPublic:macKey.publicKey.x963Representation,generation:1,binding:binding,deadline:deadline)
        let signature=try macKey.signature(for:identityProof(role:"mac",binding:binding,hostID:hostID,phoneID:claim.deviceID,generation:1,macPublic:link.macPublic,phonePublic:link.phonePublic))
        let reply=IdentityClaim(deviceID:hostID,generation:1,publicKey:link.macPublic,signature:signature.rawRepresentation)
        let out=try sealPairing(reply,role:"mac",binding:binding,key:channel);pending=link;state=1;return out
    }
    func acknowledge(_ envelope:PairingEnvelope)throws->VerifiedLink {
        lock.lock();defer{lock.unlock()};guard state==1,let link=pending else { throw EnrollmentError.replay };state=3;pending=nil
        guard clock()<deadline else { throw EnrollmentError.expired }
        let ack=try openPairing(envelope,as:IdentityAck.self,role:"ack",binding:binding,key:channel)
        let phone=try P256.Signing.PublicKey(x963Representation:link.phonePublic),signature=try P256.Signing.ECDSASignature(rawRepresentation:ack.signature)
        guard phone.isValidSignature(signature,for:identityProof(role:"ack",binding:binding,hostID:hostID,phoneID:link.phoneID,generation:1,macPublic:link.macPublic,phonePublic:link.phonePublic)),clock()<deadline else { throw EnrollmentError.denied }
        return link
    }
}
