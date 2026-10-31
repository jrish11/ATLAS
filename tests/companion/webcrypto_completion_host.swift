import Foundation
import CryptoKit
func output<T:Encodable>(_ v:T) throws { print(String(decoding:try JSONEncoder().encode(v),as:UTF8.self));fflush(stdout) }
func input<T:Decodable>(_ type:T.Type)throws->T { guard let line=readLine(),let data=line.data(using:.utf8) else { throw EnrollmentError.invalid };return try JSONDecoder().decode(type,from:data) }
@main struct Test {
 static func main() throws {
  let key=P256.Signing.PrivateKey(),id=UUID(),clock={1.0}
  let host=try EnrollmentHost(hostID:id,macSigningPublic:key.publicKey.x963Representation,origin:"https://atlas.example",macName:"Synthetic Mac",clock:clock)
  try output(host.challenge);let response=try input(EnrollmentResponse.self);let comparison=try host.accept(response)
  try output(["code":comparison.code,"fingerprint":try signingFingerprint(host.challenge.macSigningPublic)])
  let approved=try host.approve(displayedCode:comparison.code,displayedMacFingerprint:try signingFingerprint(host.challenge.macSigningPublic),ownerConfirmed:true)
  let completion=try PairingCompletionHost(approved:approved,macKey:key,clock:clock,ownerConfirmed:true)
  let phone=try input(PairingEnvelope.self);try output(completion.accept(phone));let ack=try input(PairingEnvelope.self);_=try completion.acknowledge(ack)
  try output(["status":"verified-in-memory"])
 }
}
