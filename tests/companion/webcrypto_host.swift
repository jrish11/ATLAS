import Foundation
import CryptoKit
struct BrowserReply:Decodable { let response:EnrollmentResponse;let signingPublic:Data;let signature:Data }
@main struct Test {
 static func main() throws {
  let host=try EnrollmentHost(hostID:UUID(),macSigningPublic:P256.Signing.PrivateKey().publicKey.x963Representation,origin:"https://atlas.example",macName:"Synthetic Mac",clock:{1})
  let challenge=try JSONEncoder().encode(host.challenge);print(String(decoding:challenge,as:UTF8.self));fflush(stdout)
  guard let line=readLine(),let data=line.data(using:.utf8) else { throw EnrollmentError.invalid }
  let browser=try JSONDecoder().decode(BrowserReply.self,from:data)
  let comparison=try host.accept(browser.response);_=try host.approve(displayedCode:comparison.code,displayedMacFingerprint:try signingFingerprint(host.challenge.macSigningPublic),ownerConfirmed:true)
  let publicKey=try P256.Signing.PublicKey(x963Representation:browser.signingPublic)
  let signature=try P256.Signing.ECDSASignature(rawRepresentation:browser.signature)
  guard publicKey.isValidSignature(signature,for:Data("atlas-webcrypto-interop-v1".utf8)) else { throw EnrollmentError.invalid }
  print(comparison.code);fflush(stdout)
 }
}
