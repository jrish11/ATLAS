import Foundation
import CryptoKit
@main struct Test {
 static func main()throws {
  let mac=P256.Signing.PrivateKey(),host=UUID(),phone=UUID(),request=UUID(),nonce=Data(repeating:7,count:32),payload=Data("synthetic".utf8)
  let intent=ResponseIntent(hostID:host,deviceID:phone,requestID:request,generation:1,action:"status",method:"POST",path:"/v1/tasks/status",status:"running",payloadDigest:Data(SHA256.hash(data:payload)),requestNonce:nonce,expiresAt:1020)
  let signed=try signResponse(intent,key:mac)
  try verifyResponse(signed,pinnedMacKey:mac.publicKey.x963Representation,hostID:host,deviceID:phone,requestID:request,generation:1,action:"status",method:"POST",path:"/v1/tasks/status",requestNonce:nonce,payload:payload,wallClock:1000)
  do {try verifyResponse(signed,pinnedMacKey:mac.publicKey.x963Representation,hostID:host,deviceID:phone,requestID:UUID(),generation:1,action:"status",method:"POST",path:"/v1/tasks/status",requestNonce:nonce,payload:payload,wallClock:1000);fatalError("wrong request")} catch ProofError.denied {}
  do {try verifyResponse(signed,pinnedMacKey:mac.publicKey.x963Representation,hostID:host,deviceID:phone,requestID:request,generation:1,action:"status",method:"POST",path:"/v1/tasks/status",requestNonce:nonce,payload:Data("changed".utf8),wallClock:1000);fatalError("tampered body")} catch ProofError.denied {}
  do {try verifyResponse(signed,pinnedMacKey:mac.publicKey.x963Representation,hostID:host,deviceID:phone,requestID:request,generation:1,action:"status",method:"POST",path:"/v1/tasks/status",requestNonce:nonce,payload:payload,wallClock:1021);fatalError("expired")} catch ProofError.denied {}
  print("synthetic signed response fixture ok")
 }
}
