import Foundation
import CryptoKit
struct ProofBootstrap:Decodable { let hostID:UUID;let deviceID:UUID;let signingPublic:Data }
struct BrowserSignature:Decodable { let signature:Data }
func output<T:Encodable>(_ value:T)throws {print(String(decoding:try JSONEncoder().encode(value),as:UTF8.self));fflush(stdout)}
func input<T:Decodable>(_ type:T.Type)throws->T {guard let line=readLine(),let data=line.data(using:.utf8) else {throw ProofError.invalid};return try JSONDecoder().decode(type,from:data)}
@main struct Test {
 static func main() throws {
  let b=try input(ProofBootstrap.self)
  var peer=DeviceAuthority(deviceID:b.deviceID,generation:1,signingKey:b.signingPublic,revoked:false)
  let gate=RequestProofGate(hostID:b.hostID,sessionDeadline:100,clock:{1},wallClock:{1000},authority:{peer},scope:{("project","one")})
  let intent=RequestIntent(hostID:b.hostID,deviceID:b.deviceID,generation:1,scopeID:"project",scopeRevision:"one",action:"submit",method:"POST",path:"/v1/tasks",expiresAt:1020,payloadDigest:Data(SHA256.hash(data:Data("synthetic".utf8))))
  let c=try gate.issue(intent);try output(c);let sig=try input(BrowserSignature.self);try gate.verify(c,signature:sig.signature)
  do { try gate.verify(c,signature:sig.signature);fatalError("replay") } catch ProofError.replay {}
  peer=DeviceAuthority(deviceID:b.deviceID,generation:1,signingKey:b.signingPublic,revoked:true)
  do { _=try gate.issue(intent);fatalError("revoked") } catch ProofError.denied {}
  try output(["status":"verified-then-revoked"])
 }
}
