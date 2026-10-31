import Foundation
import CryptoKit

struct ApprovalStatus:Codable { let attemptID:UUID;let state:String }
enum EnrollmentPoll { case pending,denied,expired,approved(PairingEnvelope) }
/// This coordinator is inert until a native Mac UI constructs it after owner
/// activation. Its ownerDecision method must never be routed from HTTP or web
/// content. The server can expose only join/status and encrypted exchange.
final class NativeEnrollmentCoordinator {
 private let lock=NSLock(),host:EnrollmentHost,clock:()->Double,deadline:Double
 private var attempt:UUID?,state=0,approved:ApprovedEnrollment?,approvalEnvelope:PairingEnvelope?
 let challenge:EnrollmentChallenge
 init(hostID:UUID,macPublic:Data,origin:String,macName:String,clock:@escaping ()->Double,ownerStarted:Bool)throws {
  guard ownerStarted else {throw EnrollmentError.denied}
  self.clock=clock;deadline=clock()+120
  host=try EnrollmentHost(hostID:hostID,macSigningPublic:macPublic,origin:origin,macName:macName,clock:clock,lifetime:120)
  challenge=host.challenge
 }
 func canCopyChallenge()->Bool {lock.lock();defer{lock.unlock()};return state==0 && clock()<deadline}
 func join(_ response:EnrollmentResponse)throws->(UUID,EnrollmentComparison) {
  lock.lock();defer{lock.unlock()};guard state==0 else {throw EnrollmentError.replay}
  guard clock()<deadline else {state=3;throw EnrollmentError.expired}
  let comparison=try host.accept(response),id=UUID();attempt=id;state=1;return (id,comparison)
 }
 /// Native-only control: no HTTP body may supply this decision.
 func ownerDecision(attemptID:UUID,displayedCode:String,displayedMacFingerprint:String,ownerConfirmed:Bool)throws {
  lock.lock();defer{lock.unlock()};guard state==1,attempt==attemptID else {throw EnrollmentError.badState}
  guard clock()<deadline else {state=3;host.cancel();throw EnrollmentError.expired}
  guard ownerConfirmed else {state=3;host.cancel();throw EnrollmentError.denied}
  do {
   let value=try host.approve(displayedCode:displayedCode,displayedMacFingerprint:displayedMacFingerprint,ownerConfirmed:true)
   let sealed=try sealPairing(ApprovalStatus(attemptID:attemptID,state:"approved"),role:"approval",binding:value.binding,key:value.channel)
   approved=value;approvalEnvelope=sealed;state=2
  } catch {state=3;host.cancel();throw error}
 }
 func poll(_ id:UUID)->EnrollmentPoll {
  lock.lock();defer{lock.unlock()};guard attempt==id else {return .denied}
  if clock()>=deadline {state=3;approved=nil;approvalEnvelope=nil;host.cancel();return .expired}
  if state==1 {return .pending};if state==2,let sealed=approvalEnvelope {return .approved(sealed)};return .denied
 }
 func takeApproved(_ id:UUID)throws->ApprovedEnrollment {
  lock.lock();defer{lock.unlock()};guard state==2,attempt==id,clock()<deadline,let result=approved else {throw EnrollmentError.denied}
  approved=nil;state=3;return result
 }
 func cancel() {lock.lock();state=3;approved=nil;approvalEnvelope=nil;host.cancel();lock.unlock()}
}
