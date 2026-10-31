import Foundation
import CryptoKit

// Reference signature for authenticated responses. No transport is enabled.
struct ResponseIntent:Codable {
 let hostID:UUID;let deviceID:UUID;let requestID:UUID;let generation:UInt64
 let action:String;let method:String;let path:String;let status:String
 let payloadDigest:Data;let requestNonce:Data;let expiresAt:Int64
}
struct SignedResponse:Codable { let intent:ResponseIntent;let signature:Data }
private func responseFields(_ fields:[Data])->Data {
 var out=Data();for f in fields { var size=UInt32(f.count).bigEndian;withUnsafeBytes(of:&size){out.append(contentsOf:$0)};out.append(f) };return out
}
func responseProofMessage(_ i:ResponseIntent)->Data {
 responseFields([Data("atlas-response-proof-v1".utf8),Data(i.hostID.uuidString.lowercased().utf8),Data(i.deviceID.uuidString.lowercased().utf8),Data(i.requestID.uuidString.lowercased().utf8),Data(String(i.generation).utf8),Data(i.action.utf8),Data(i.method.utf8),Data(i.path.utf8),Data(i.status.utf8),i.payloadDigest,i.requestNonce,Data(String(i.expiresAt).utf8)])
}
func signResponse(_ i:ResponseIntent,key:P256.Signing.PrivateKey)throws->SignedResponse {
 guard i.payloadDigest.count==32,i.requestNonce.count==32 else {throw ProofError.invalid}
 return SignedResponse(intent:i,signature:try key.signature(for:responseProofMessage(i)).rawRepresentation)
}
func verifyResponse(_ signed:SignedResponse,pinnedMacKey:Data,hostID:UUID,deviceID:UUID,requestID:UUID,generation:UInt64,action:String,method:String,path:String,requestNonce:Data,payload:Data,wallClock:Int64)throws {
 let i=signed.intent;let remaining=i.expiresAt.subtractingReportingOverflow(wallClock)
 guard !remaining.overflow,remaining.partialValue>0,remaining.partialValue<=30,i.hostID==hostID,i.deviceID==deviceID,i.requestID==requestID,i.generation==generation,i.action==action,i.method==method,i.path==path,
       i.requestNonce==requestNonce,requestNonce.count==32,i.payloadDigest==Data(SHA256.hash(data:payload)),
       ["validating","queued","submitted","running","needs-owner","cancelling","stopped","failed","unknown","cancelled","completed-unverified"].contains(i.status),
       let key=try? P256.Signing.PublicKey(x963Representation:pinnedMacKey),let sig=try? P256.Signing.ECDSASignature(rawRepresentation:signed.signature),key.isValidSignature(sig,for:responseProofMessage(i)) else { throw ProofError.denied }
}
