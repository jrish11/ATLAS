import Foundation
import CryptoKit

// This is an isolated persistence adapter, not wired to a UI, listener, or the
// shipped app. Tests inject memory storage only; real Keychain access requires
// a separately approved activation and security review.
struct PairedPhone:Codable,Equatable { let id:UUID;let name:String;let enrollmentBinding:Data;var publicKey:Data;var generation:UInt64;var revoked:Bool }
private struct VaultRecord:Codable { let version:Int;let hostID:UUID;let macPrivate:Data;var phones:[PairedPhone] }
func rotationProofMessage(hostID:UUID,phoneID:UUID,oldGeneration:UInt64,oldPublic:Data,newPublic:Data)->Data {
 let fields=[Data("atlas-rotate-v1".utf8),Data(hostID.uuidString.lowercased().utf8),Data(phoneID.uuidString.lowercased().utf8),Data(String(oldGeneration).utf8),oldPublic,newPublic]
 var out=Data();for field in fields {var count=UInt32(field.count).bigEndian;withUnsafeBytes(of:&count){out.append(contentsOf:$0)};out.append(field)};return out
}
final class MacPairingVault {
 private let lock=NSLock(),storage:SecureDeviceStorage,clock:()->Double
 init(storage:SecureDeviceStorage,clock:@escaping ()->Double) { self.storage=storage;self.clock=clock }
 private func read() throws -> VaultRecord? {
  guard let data=try storage.read() else { return nil }
  let value=try JSONDecoder().decode(VaultRecord.self,from:data)
  guard value.version==1,(try? P256.Signing.PrivateKey(rawRepresentation:value.macPrivate)) != nil,
        Set(value.phones.map(\.id)).count==value.phones.count,
        value.phones.allSatisfy({!$0.name.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty && $0.name.utf8.count<=80 && !$0.name.unicodeScalars.contains(where:{$0.value<32 || $0.value==127}) && $0.enrollmentBinding.count==32 && $0.generation>0 && (try? P256.Signing.PublicKey(x963Representation:$0.publicKey)) != nil}) else { throw DeviceError.invalid }
  return value
 }
 @discardableResult func enroll(_ link:VerifiedLink,macKey:P256.Signing.PrivateKey,ownerConfirmed:Bool)throws->PairingReceipt {
  lock.lock();defer{lock.unlock()}
  guard ownerConfirmed,clock().isFinite,clock()<link.deadline,link.generation==1,link.binding.count==32,link.macPublic==macKey.publicKey.x963Representation,
        (try? P256.Signing.PublicKey(x963Representation:link.phonePublic)) != nil else { throw DeviceError.denied }
  var record=try read() ?? VaultRecord(version:1,hostID:link.hostID,macPrivate:macKey.rawRepresentation,phones:[])
  guard record.hostID==link.hostID,record.macPrivate==macKey.rawRepresentation,!record.phones.contains(where:{$0.id==link.phoneID}) else { throw DeviceError.invalid }
  record.phones.append(PairedPhone(id:link.phoneID,name:link.phoneName,enrollmentBinding:link.binding,publicKey:link.phonePublic,generation:1,revoked:false))
  guard clock()<link.deadline else {throw EnrollmentError.expired}
  try storage.write(JSONEncoder().encode(record))
  let descriptor=RecoveryDescriptor(hostID:link.hostID,phoneID:link.phoneID,phoneName:link.phoneName,generation:link.generation,binding:link.binding,macPublic:link.macPublic,phonePublic:link.phonePublic)
  return PairingReceipt(descriptor:descriptor,signature:try macKey.signature(for:pairingReceiptMessage(descriptor)).rawRepresentation)
 }
 func authority(_ id:UUID)throws->DeviceAuthority? {
  lock.lock();defer{lock.unlock()};guard let phone=try read()?.phones.first(where:{$0.id==id}) else { return nil }
  return DeviceAuthority(deviceID:phone.id,generation:phone.generation,signingKey:phone.publicKey,revoked:phone.revoked)
 }
 func phones()throws->[PairedPhone] { lock.lock();defer{lock.unlock()};return try read()?.phones ?? [] }
 func revoke(_ id:UUID,expectedGeneration:UInt64,ownerConfirmed:Bool)throws {
  lock.lock();defer{lock.unlock()};guard ownerConfirmed else { throw DeviceError.denied }
  guard var record=try read(),let i=record.phones.firstIndex(where:{$0.id==id}) else { throw DeviceError.missing }
  guard !record.phones[i].revoked,record.phones[i].generation==expectedGeneration,expectedGeneration<9_007_199_254_740_991 else { throw DeviceError.stale }
  record.phones[i].revoked=true;record.phones[i].generation += 1
  try storage.write(JSONEncoder().encode(record))
 }
 func rotate(_ id:UUID,expectedGeneration:UInt64,newPublic:Data,oldSignature:Data,newSignature:Data,ownerConfirmed:Bool)throws {
  lock.lock();defer{lock.unlock()};guard ownerConfirmed else { throw DeviceError.denied }
  guard var record=try read(),let i=record.phones.firstIndex(where:{$0.id==id}) else { throw DeviceError.missing }
  let old=record.phones[i]
  guard !old.revoked,old.generation==expectedGeneration,expectedGeneration<9_007_199_254_740_991 else { throw DeviceError.stale }
  guard old.publicKey != newPublic,let oldKey=try? P256.Signing.PublicKey(x963Representation:old.publicKey),let newKey=try? P256.Signing.PublicKey(x963Representation:newPublic),
        let oldProof=try? P256.Signing.ECDSASignature(rawRepresentation:oldSignature),let newProof=try? P256.Signing.ECDSASignature(rawRepresentation:newSignature) else { throw DeviceError.invalid }
  let message=rotationProofMessage(hostID:record.hostID,phoneID:id,oldGeneration:old.generation,oldPublic:old.publicKey,newPublic:newPublic)
  guard oldKey.isValidSignature(oldProof,for:message),newKey.isValidSignature(newProof,for:message) else { throw DeviceError.denied }
  record.phones[i].publicKey=newPublic;record.phones[i].generation += 1
  try storage.write(JSONEncoder().encode(record))
 }
}

struct RecoveryDescriptor:Codable,Equatable {
 let hostID:UUID;let phoneID:UUID;let phoneName:String;let generation:UInt64;let binding:Data;let macPublic:Data;let phonePublic:Data
}
struct PairingReceipt:Codable { let descriptor:RecoveryDescriptor;let signature:Data }
private func receiptFields(_ fields:[Data])->Data {var out=Data();for f in fields{var n=UInt32(f.count).bigEndian;withUnsafeBytes(of:&n){out.append(contentsOf:$0)};out.append(f)};return out}
func pairingReceiptMessage(_ d:RecoveryDescriptor)->Data {
 receiptFields([Data("atlas-pair-receipt-v1".utf8),Data(d.hostID.uuidString.lowercased().utf8),Data(d.phoneID.uuidString.lowercased().utf8),Data(d.phoneName.utf8),Data(String(d.generation).utf8),d.binding,d.macPublic,d.phonePublic])
}
extension MacPairingVault {
 // Called only from local Mac review. It never exposes the private key.
 func inspectRecovery(_ id:UUID)throws->RecoveryDescriptor? {
  lock.lock();defer{lock.unlock()};guard let record=try read(),let p=record.phones.first(where:{$0.id==id}),!p.revoked,p.generation==1 else {return nil}
  let key=try P256.Signing.PrivateKey(rawRepresentation:record.macPrivate)
  return RecoveryDescriptor(hostID:record.hostID,phoneID:p.id,phoneName:p.name,generation:p.generation,binding:p.enrollmentBinding,macPublic:key.publicKey.x963Representation,phonePublic:p.publicKey)
 }
 func recoveryReceipt(_ expected:RecoveryDescriptor)throws->PairingReceipt {
  lock.lock();defer{lock.unlock()};guard let record=try read(),let p=record.phones.first(where:{$0.id==expected.phoneID}),!p.revoked,p.generation==1 else {throw DeviceError.denied}
  let key=try P256.Signing.PrivateKey(rawRepresentation:record.macPrivate)
  let now=RecoveryDescriptor(hostID:record.hostID,phoneID:p.id,phoneName:p.name,generation:p.generation,binding:p.enrollmentBinding,macPublic:key.publicKey.x963Representation,phonePublic:p.publicKey)
  guard now==expected else {throw DeviceError.stale}
  return PairingReceipt(descriptor:now,signature:try key.signature(for:pairingReceiptMessage(now)).rawRepresentation)
 }
}
