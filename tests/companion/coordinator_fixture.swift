import Foundation
import CryptoKit
@main struct Test {
 static func main()throws {
  var now=1.0;let mac=P256.Signing.PrivateKey(),hostID=UUID(),pub=mac.publicKey.x963Representation
  let coordinator=try NativeEnrollmentCoordinator(hostID:hostID,macPublic:pub,origin:"https://atlas.example",macName:"Mac",clock:{now},ownerStarted:true)
  precondition(coordinator.canCopyChallenge())
  var clipboard="",writes=0
  precondition(copyEnrollmentChallenge(coordinator.challenge,allowed:{coordinator.canCopyChallenge()},write:{clipboard=$0;writes += 1;return true}))
  let copied=clipboard,object=try JSONSerialization.jsonObject(with:Data(copied.utf8)) as! [String:Any]
  precondition(Set(object.keys)==Set(["version","hostID","origin","macName","nonce","macEphemeral","macSigningPublic"]))
  let decoded=try JSONDecoder().decode(EnrollmentChallenge.self,from:Data(copied.utf8));precondition(decoded.nonce==coordinator.challenge.nonce && decoded.macSigningPublic==pub && decoded.hostID==hostID)
  let phone=try EnrollmentPhone(challenge:coordinator.challenge,expectedOrigin:"https://atlas.example",expectedMacFingerprint:try signingFingerprint(pub),phoneName:"Phone")
  let (id,compare)=try coordinator.join(phone.response);precondition(!coordinator.canCopyChallenge());precondition(!copyEnrollmentChallenge(coordinator.challenge,allowed:{coordinator.canCopyChallenge()},write:{_ in writes += 1;return true}) && writes==1);if case .pending=coordinator.poll(id) {} else {fatalError("not pending")}
  do {try coordinator.ownerDecision(attemptID:UUID(),displayedCode:compare.code,displayedMacFingerprint:try signingFingerprint(pub),ownerConfirmed:true);fatalError("wrong attempt")} catch EnrollmentError.badState {}
  try coordinator.ownerDecision(attemptID:id,displayedCode:compare.code,displayedMacFingerprint:try signingFingerprint(pub),ownerConfirmed:true)
  guard case .approved(let envelope)=coordinator.poll(id) else {fatalError("no approval")}
  let binding=enrollmentBinding(coordinator.challenge,phone.response),status=try openPairing(envelope,as:ApprovalStatus.self,role:"approval",binding:binding,key:phone.channel)
  precondition(status.attemptID==id && status.state=="approved")
  _=try coordinator.takeApproved(id);do {_=try coordinator.takeApproved(id);fatalError("approval replay")} catch EnrollmentError.denied {}
  let denied=try NativeEnrollmentCoordinator(hostID:hostID,macPublic:pub,origin:"https://atlas.example",macName:"Mac",clock:{now},ownerStarted:true)
  let p=try EnrollmentPhone(challenge:denied.challenge,expectedOrigin:"https://atlas.example",expectedMacFingerprint:try signingFingerprint(pub),phoneName:"Phone"),pair=try denied.join(p.response)
  do {try denied.ownerDecision(attemptID:pair.0,displayedCode:pair.1.code,displayedMacFingerprint:try signingFingerprint(pub),ownerConfirmed:false);fatalError("denial")} catch EnrollmentError.denied {}
  if case .denied=denied.poll(pair.0) {} else {fatalError("denied approval leaked")}
  let unjoined=try NativeEnrollmentCoordinator(hostID:hostID,macPublic:pub,origin:"https://atlas.example",macName:"Mac",clock:{now},ownerStarted:true)
  precondition(unjoined.canCopyChallenge());now=500;precondition(!unjoined.canCopyChallenge());precondition(!copyEnrollmentChallenge(unjoined.challenge,allowed:{unjoined.canCopyChallenge()},write:{_ in writes += 1;return true}) && writes==1);if case .expired=denied.poll(pair.0) {} else {fatalError("expiry")}
  print("synthetic native approval status fixture ok")
 }
}
