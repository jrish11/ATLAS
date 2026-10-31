import Foundation

// Separate device-local durable store; never place it in the same Keychain
// item as the pairing vault. Missing or malformed records fail closed whenever
// an existing paired phone is present. Real storage has not been activated.
struct RevocationMarker:Codable,Equatable {
 let version:Int;let hostID:UUID;let state:String;let phoneID:String;let generation:UInt64
}
final class RevocationJournal {
 private let lock=NSLock(),storage:SecureDeviceStorage,hostID:UUID
 init(storage:SecureDeviceStorage,hostID:UUID){self.storage=storage;self.hostID=hostID}
 private func clean()->RevocationMarker {RevocationMarker(version:1,hostID:hostID,state:"clear",phoneID:"",generation:0)}
 private func readLocked()throws->RevocationMarker {
  guard let data=try storage.read() else {throw DeviceError.invalid}
  _=try strictJSONObject(data,keys:["version","hostID","state","phoneID","generation"])
  let m=try JSONDecoder().decode(RevocationMarker.self,from:data)
  guard m.version==1,m.hostID==hostID else {throw DeviceError.invalid}
  if m.state=="clear" {guard m.phoneID.isEmpty,m.generation==0 else {throw DeviceError.invalid}}
  else {guard ["active","stopped","revoking"].contains(m.state),UUID(uuidString:m.phoneID) != nil,m.generation>0 else {throw DeviceError.invalid}}
  return m
 }
 private func writeLocked(_ m:RevocationMarker)throws {
  try storage.write(JSONEncoder().encode(m))
  guard try readLocked()==m else {throw DeviceError.invalid}
 }
 func prepare(fresh:Bool)throws {
  lock.lock();defer{lock.unlock()}
  if try storage.read()==nil {guard fresh else {throw DeviceError.invalid};try writeLocked(clean())}
  else {_=try readLocked()}
 }
 func read()throws->RevocationMarker {lock.lock();defer{lock.unlock()};return try readLocked()}
 func beginSession(_ peer:DeviceAuthority)throws {
  lock.lock();defer{lock.unlock()};guard try readLocked().state=="clear",!peer.revoked,peer.generation>0 else {throw DeviceError.denied}
  try writeLocked(RevocationMarker(version:1,hostID:hostID,state:"active",phoneID:peer.deviceID.uuidString.lowercased(),generation:peer.generation))
 }
 // Only a quiesced native route may mark an intentional Stop. It does not
 // clear the task barrier or authorize reconnection without local review.
 func markStopped(expected:RevocationMarker)throws->RevocationMarker {
  lock.lock();defer{lock.unlock()};guard expected.state=="active",try readLocked()==expected else {throw DeviceError.stale}
  let stopped=RevocationMarker(version:1,hostID:hostID,state:"stopped",phoneID:expected.phoneID,generation:expected.generation)
  try writeLocked(stopped);return stopped
 }
 func beginRevocation(_ peer:DeviceAuthority)throws {
  lock.lock();defer{lock.unlock()};let m=try readLocked()
  guard !peer.revoked,(m.state=="clear" || (m.state=="active" && m.phoneID==peer.deviceID.uuidString.lowercased() && m.generation==peer.generation)) else {throw DeviceError.denied}
  try writeLocked(RevocationMarker(version:1,hostID:hostID,state:"revoking",phoneID:peer.deviceID.uuidString.lowercased(),generation:peer.generation))
 }
 func clear(expected:RevocationMarker)throws {
  lock.lock();defer{lock.unlock()};guard try readLocked()==expected else {throw DeviceError.stale};try writeLocked(clean())
 }
}
