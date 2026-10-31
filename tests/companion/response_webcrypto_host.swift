import Foundation
import CryptoKit
struct Fixture:Codable {let publicKey:Data;let response:SignedResponse;let payload:Data}
@main struct Test {
 static func main()throws {
  let key=P256.Signing.PrivateKey(),payload=Data("synthetic".utf8)
  let i=ResponseIntent(hostID:UUID(),deviceID:UUID(),requestID:UUID(),generation:1,action:"status",method:"POST",path:"/v1/tasks/status",status:"running",payloadDigest:Data(SHA256.hash(data:payload)),requestNonce:Data(repeating:7,count:32),expiresAt:1020)
  let item=Fixture(publicKey:key.publicKey.x963Representation,response:try signResponse(i,key:key),payload:payload)
  print(String(decoding:try JSONEncoder().encode(item),as:UTF8.self))
 }
}
