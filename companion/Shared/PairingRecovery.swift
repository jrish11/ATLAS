import Foundation
import CryptoKit
import Security
struct RecoveryChallenge:Codable {let descriptor:RecoveryDescriptor;let nonce:Data}
private func recoveryFields(_ fields:[Data])->Data {var out=Data();for f in fields{var n=UInt32(f.count).bigEndian;withUnsafeBytes(of:&n){out.append(contentsOf:$0)};out.append(f)};return out}
func pairingRecoveryMessage(_ c:RecoveryChallenge)->Data {
 let d=c.descriptor
 return recoveryFields([Data("atlas-pair-recovery-v1".utf8),Data(d.hostID.uuidString.lowercased().utf8),Data(d.phoneID.uuidString.lowercased().utf8),Data(String(d.generation).utf8),d.binding,c.nonce])
}
/// Disabled recovery reference. After an uncertain write the owner inspects
/// local state and explicitly approves a fresh challenge. The paired phone must
/// then prove possession of its key. No retry or write happens here.
final class PairingRecovery {
 private let lock=NSLock(),vault:MacPairingVault,clock:()->Double,recoveryCheck:()->Bool
 private var pending:(RecoveryChallenge,Double)?
 init(vault:MacPairingVault,clock:@escaping ()->Double,recoveryCheck:@escaping ()->Bool){self.vault=vault;self.clock=clock;self.recoveryCheck=recoveryCheck}
 func begin(displayed:RecoveryDescriptor,ownerReviewed:Bool)throws->RecoveryChallenge {
  lock.lock();defer{lock.unlock()};pending=nil;guard ownerReviewed,recoveryCheck(),try vault.inspectRecovery(displayed.phoneID)==displayed,clock().isFinite else {throw DeviceError.denied}
  var nonce=Data(count:32);guard nonce.withUnsafeMutableBytes({SecRandomCopyBytes(kSecRandomDefault,32,$0.baseAddress!)})==errSecSuccess else {throw EnrollmentError.entropy}
  let c=RecoveryChallenge(descriptor:displayed,nonce:nonce);pending=(c,clock()+30);return c
 }
 func finish(_ challenge:RecoveryChallenge,signature:Data)throws->PairingReceipt {
  lock.lock();defer{lock.unlock()};guard let saved=pending else {throw EnrollmentError.replay};pending=nil
  guard recoveryCheck(),clock()<saved.1,challenge.nonce==saved.0.nonce,challenge.descriptor==saved.0.descriptor,try vault.inspectRecovery(challenge.descriptor.phoneID)==challenge.descriptor,
        let key=try? P256.Signing.PublicKey(x963Representation:challenge.descriptor.phonePublic),let proof=try? P256.Signing.ECDSASignature(rawRepresentation:signature),key.isValidSignature(proof,for:pairingRecoveryMessage(challenge)) else {throw DeviceError.denied}
  guard clock()<saved.1 else {throw EnrollmentError.expired}
  let receipt=try vault.recoveryReceipt(challenge.descriptor)
  guard clock()<saved.1 else {throw EnrollmentError.expired};return receipt
 }
 func cancel(){lock.lock();pending=nil;lock.unlock()}
}
