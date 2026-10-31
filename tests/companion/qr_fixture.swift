import Foundation
import CryptoKit
@main struct Test {
 static func main() throws {
  let host=try EnrollmentHost(hostID:UUID(),macSigningPublic:P256.Signing.PrivateKey().publicKey.x963Representation,origin:"https://atlas.example",macName:"Synthetic Mac",clock:{1.0})
  let image=try enrollmentQR(host.challenge);precondition(image.width>100 && image.height==image.width)
  let bytes=try JSONEncoder().encode(host.challenge);let decoded=try JSONDecoder().decode(EnrollmentChallenge.self,from:bytes)
  precondition(decoded.nonce==host.challenge.nonce && decoded.macEphemeral==host.challenge.macEphemeral)
  print("synthetic enrollment QR fixture ok")
 }
}
