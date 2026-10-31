import Foundation
import CryptoKit
import Security

enum ProofError: Error { case invalid, expired, replay, denied, stale, capacity, entropy }
struct DeviceAuthority: Equatable {
    let deviceID: UUID
    let generation: UInt64
    let signingKey: Data
    let revoked: Bool
}
struct RequestIntent: Codable {
    let hostID: UUID
    let deviceID: UUID
    let generation: UInt64
    let scopeID: String
    let scopeRevision: String
    let action: String
    let method: String
    let path: String
    let expiresAt: Int64 // Unix seconds; server also enforces a continuous deadline
    let payloadDigest: Data
}
struct RequestChallenge: Codable {
    let nonce: Data
    let intent: RequestIntent
}
private func proofBytes(_ fields: [Data]) -> Data {
    var result=Data();for f in fields { var size=UInt32(f.count).bigEndian;withUnsafeBytes(of:&size) { result.append(contentsOf:$0) };result.append(f) };return result
}
func requestProofMessage(_ challenge: RequestChallenge) -> Data {
    let i=challenge.intent
    return proofBytes([Data("atlas-request-proof-v1".utf8),Data(i.hostID.uuidString.lowercased().utf8),Data(i.deviceID.uuidString.lowercased().utf8),Data(String(i.generation).utf8),Data(i.scopeID.utf8),Data(i.scopeRevision.utf8),Data(i.action.utf8),Data(i.method.utf8),Data(i.path.utf8),Data(String(i.expiresAt).utf8),i.payloadDigest,challenge.nonce])
}

/// Synthetic foundation only: the authenticated transport and native action
/// approval must invoke this at their final dispatch boundary. This object
/// itself never opens a listener, persists a key, or dispatches a command.
final class RequestProofGate {
    private struct Pending { let challenge:RequestChallenge;let expires:Double }
    private let lock=NSLock(),clock:()->Double,wallClock:()->Int64,authority:()->DeviceAuthority?,scope:()->(String,String)?
    private let hostID:UUID,sessionDeadline:Double
    private var pending:[Data:Pending]=[:]
    init(hostID:UUID,sessionDeadline:Double,clock:@escaping ()->Double,wallClock:@escaping ()->Int64,authority:@escaping ()->DeviceAuthority?,scope:@escaping ()->(String,String)?) {
        self.hostID=hostID;self.sessionDeadline=sessionDeadline;self.clock=clock;self.wallClock=wallClock;self.authority=authority;self.scope=scope
    }
    private func current(_ intent:RequestIntent) -> Bool {
        let routes=["submit":"/v1/tasks","status":"/v1/tasks/status","stop":"/v1/tasks/stop"]
        let remaining=intent.expiresAt.subtractingReportingOverflow(wallClock())
        guard !remaining.overflow,remaining.partialValue>0,remaining.partialValue<=30,clock()<sessionDeadline,intent.generation<=9_007_199_254_740_991,intent.method=="POST",routes[intent.action]==intent.path,intent.hostID==hostID,let peer=authority(),!peer.revoked,peer.deviceID==intent.deviceID,peer.generation==intent.generation,
              peer.signingKey.count==65,let selected=scope(),selected.0==intent.scopeID,selected.1==intent.scopeRevision,
              ["submit","status","stop"].contains(intent.action),intent.payloadDigest.count==32,!intent.scopeID.isEmpty,intent.scopeID.utf8.count<=256,!intent.scopeRevision.isEmpty,intent.scopeRevision.utf8.count<=256 else { return false }
        return true
    }
    func issue(_ intent:RequestIntent) throws -> RequestChallenge {
        lock.lock();defer{lock.unlock()};let now=clock();pending=pending.filter{$0.value.expires>now}
        guard current(intent) else { throw ProofError.denied };guard pending.count<64 else { throw ProofError.capacity }
        var nonce=Data(count:32);guard nonce.withUnsafeMutableBytes({SecRandomCopyBytes(kSecRandomDefault,32,$0.baseAddress!)})==errSecSuccess else { throw ProofError.entropy }
        guard pending[nonce]==nil else { throw ProofError.entropy }
        let challenge=RequestChallenge(nonce:nonce,intent:intent);pending[nonce]=Pending(challenge:challenge,expires:min(now+30,sessionDeadline));return challenge
    }
    func verify(_ challenge:RequestChallenge,signature:Data) throws {
        lock.lock();defer{lock.unlock()}
        guard let stored=pending.removeValue(forKey:challenge.nonce) else { throw ProofError.replay }
        guard clock()<stored.expires else { throw ProofError.expired }
        guard requestProofMessage(stored.challenge)==requestProofMessage(challenge),current(challenge.intent),let peer=authority(),
              let key=try? P256.Signing.PublicKey(x963Representation:peer.signingKey),let proof=try? P256.Signing.ECDSASignature(rawRepresentation:signature),key.isValidSignature(proof,for:requestProofMessage(challenge)) else { throw ProofError.denied }
        guard clock()<stored.expires,current(challenge.intent),authority()==peer else { throw ProofError.expired }
    }
    func stillCurrent(_ intent:RequestIntent) -> Bool {
        lock.lock();defer{lock.unlock()};return current(intent)
    }
}
