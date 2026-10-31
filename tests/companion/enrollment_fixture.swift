import Foundation
import CryptoKit
@main struct Test {
 static func main() throws {
  var time=10.0;let host=try EnrollmentHost(hostID:UUID(),macSigningPublic:P256.Signing.PrivateKey().publicKey.x963Representation,origin:"https://atlas.example",macName:"Test Mac",clock:{time})
  do { _=try EnrollmentPhone(challenge:host.challenge,expectedOrigin:"https://attacker.example",expectedMacFingerprint:try signingFingerprint(host.challenge.macSigningPublic),phoneName:"Phone");fatalError("QR origin injection") } catch EnrollmentError.invalid {}
  do { _=try EnrollmentPhone(challenge:host.challenge,expectedOrigin:"https://atlas.example",expectedMacFingerprint:String(repeating:"0",count:64),phoneName:"Phone");fatalError("fingerprint mismatch") } catch EnrollmentError.invalid {}
  let phone=try EnrollmentPhone(challenge:host.challenge,expectedOrigin:"https://atlas.example",expectedMacFingerprint:try signingFingerprint(host.challenge.macSigningPublic),phoneName:"Test phone")
  let compare=try host.accept(phone.response);precondition(compare.code==phone.code && compare.phoneName=="Test phone")
  do { _=try host.accept(phone.response);fatalError("replay accepted") } catch EnrollmentError.replay {}
  let macKey=try host.approve(displayedCode:compare.code,displayedMacFingerprint:try signingFingerprint(host.challenge.macSigningPublic),ownerConfirmed:true)
  let message=Data("synthetic".utf8);let sealed=try ChaChaPoly.seal(message,using:macKey.channel);let opened=try ChaChaPoly.open(sealed,using:phone.channel);precondition(opened==message)
  do { _=try host.approve(displayedCode:compare.code,displayedMacFingerprint:try signingFingerprint(host.challenge.macSigningPublic),ownerConfirmed:true);fatalError("reused") } catch EnrollmentError.badState {}
  let expired=try EnrollmentHost(hostID:UUID(),macSigningPublic:P256.Signing.PrivateKey().publicKey.x963Representation,origin:"https://atlas.example",macName:"Test Mac",clock:{time},lifetime:5);let p=try EnrollmentPhone(challenge:expired.challenge,expectedOrigin:"https://atlas.example",expectedMacFingerprint:try signingFingerprint(expired.challenge.macSigningPublic),phoneName:"Phone");let c=try expired.accept(p.response);time=16
  do { _=try expired.approve(displayedCode:c.code,displayedMacFingerprint:try signingFingerprint(expired.challenge.macSigningPublic),ownerConfirmed:true);fatalError("expiry ignored") } catch EnrollmentError.expired {}
  let denied=try EnrollmentHost(hostID:UUID(),macSigningPublic:P256.Signing.PrivateKey().publicKey.x963Representation,origin:"https://atlas.example",macName:"Test Mac",clock:{time});let d=try EnrollmentPhone(challenge:denied.challenge,expectedOrigin:"https://atlas.example",expectedMacFingerprint:try signingFingerprint(denied.challenge.macSigningPublic),phoneName:"Phone");let dc=try denied.accept(d.response)
  do { _=try denied.approve(displayedCode:dc.code,displayedMacFingerprint:try signingFingerprint(denied.challenge.macSigningPublic),ownerConfirmed:false);fatalError("denial ignored") } catch EnrollmentError.denied {}
  do { _=try denied.approve(displayedCode:dc.code,displayedMacFingerprint:try signingFingerprint(denied.challenge.macSigningPublic),ownerConfirmed:true);fatalError("denial replay") } catch EnrollmentError.badState {}
  do { _=try EnrollmentHost(hostID:UUID(),macSigningPublic:P256.Signing.PrivateKey().publicKey.x963Representation,origin:"http://public.example",macName:"Mac",clock:{time});fatalError("insecure origin") } catch EnrollmentError.invalid {}
  do { _=try EnrollmentHost(hostID:UUID(),macSigningPublic:P256.Signing.PrivateKey().publicKey.x963Representation,origin:"https://127.0.0.1",macName:"Mac",clock:{time});fatalError("literal IP") } catch EnrollmentError.invalid {}
  print("synthetic enrollment fixture ok")
 }
}
