import Foundation
import CryptoKit
@main struct Test {
 static func main() throws {
  let a=UUID(),b=UUID(),keyA=P256.Signing.PrivateKey().publicKey.x963Representation,keyB=P256.Signing.PrivateKey().publicKey.x963Representation,keyC=P256.Signing.PrivateKey().publicKey.x963Representation;var registry=DeviceRegistry()
  try registry.add(LinkedComputer(id:a,name:"Mac A",origin:"https://a.example",publicKey:keyA,generation:1,revoked:false,online:true))
  try registry.add(LinkedComputer(id:b,name:"Mac B",origin:"https://b.example",publicKey:keyB,generation:1,revoked:false,online:true))
  do { _=try registry.target(a);fatalError("implicit target") } catch DeviceError.missing {}
  try registry.select(a);precondition(tryTarget(registry,a));do { _=try registry.target(b);fatalError("fallback") } catch DeviceError.missing {}
  let restored=try JSONDecoder().decode(DeviceRegistry.self,from:JSONEncoder().encode(registry));precondition(restored.selected == nil && restored.computers.allSatisfy { !$0.online })
  try registry.setOnline(a,false);do { _=try registry.target(a);fatalError("offline") } catch DeviceError.offline {}
  do { try registry.revoke(a,ownerConfirmed:false);fatalError("unapproved revoke") } catch DeviceError.denied {}
  try registry.revoke(a,ownerConfirmed:true);do { _=try registry.target(b);fatalError("silent fallback") } catch DeviceError.missing {}
  try registry.select(b);do { try registry.rotate(b,expectedGeneration:2,publicKey:keyC,ownerConfirmed:true);fatalError("stale rotation") } catch DeviceError.stale {}
  try registry.rotate(b,expectedGeneration:1,publicKey:keyC,ownerConfirmed:true)
  do { _=try registry.target(b);fatalError("rotation incorrectly online") } catch DeviceError.offline {}
  print("synthetic device registry fixture ok")
 }
 static func tryTarget(_ registry:DeviceRegistry,_ id:UUID)->Bool { (try? registry.target(id)) != nil }
}
