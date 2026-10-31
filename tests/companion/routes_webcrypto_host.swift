import Foundation
import CryptoKit
struct Bootstrap:Decodable {let hostID:UUID;let deviceID:UUID;let signingPublic:Data;let expectedHost:String}
struct Wire:Decodable {let route:String;let host:String;let origin:String;let method:String;let intent:RequestIntent?;let operation:SyntheticOperation?}
struct SignedWire:Encodable {let signed:SignedResponse;let payload:Data}
func input<T:Decodable>(_ type:T.Type)throws->T {guard let line=readLine(),let data=line.data(using:.utf8) else {throw ProofError.invalid};return try JSONDecoder().decode(type,from:data)}
func output<T:Encodable>(_ value:T)throws {print(String(decoding:try JSONEncoder().encode(value),as:UTF8.self));fflush(stdout)}
@main struct Test {
 static func main()throws {
  let b=try input(Bootstrap.self),mac=P256.Signing.PrivateKey(),peer=DeviceAuthority(deviceID:b.deviceID,generation:1,signingKey:b.signingPublic,revoked:false)
  let server=SyntheticRoutes(hostID:b.hostID,expectedHost:b.expectedHost,expectedOrigin:"https://atlas-desktop.joelr2.chatgpt.site",peer:peer,scope:("project","one"),sessionDeadline:100,clock:{1},wallClock:{1000},ownerConfirm:{_ in true})
  try output(["macPublic":mac.publicKey.x963Representation])
  while let line=readLine(),let data=line.data(using:.utf8) {
   do {
    let w=try JSONDecoder().decode(Wire.self,from:data)
    if w.route=="/test/revoke" {try server.revoke(ownerConfirmed:true);try output(["status":"revoked"]);continue}
    if w.route=="/v1/session/challenge",let intent=w.intent {let c=try server.challenge(host:w.host,origin:w.origin,method:w.method,intent:intent);try output(c);continue}
    guard let op=w.operation else {throw ProofError.invalid}
    let result=try server.operation(host:w.host,origin:w.origin,method:w.method,path:w.route,value:op),payload=try JSONEncoder().encode(result),i=op.challenge.intent
    let response=ResponseIntent(hostID:i.hostID,deviceID:i.deviceID,requestID:result.id,generation:i.generation,action:i.action,method:w.method,path:w.route,status:result.status,payloadDigest:Data(SHA256.hash(data:payload)),requestNonce:op.challenge.nonce,expiresAt:i.expiresAt)
    try output(SignedWire(signed:signResponse(response,key:mac),payload:payload))
   } catch {try output(["error":"rejected"])}
  }
 }
}
