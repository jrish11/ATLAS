import Foundation
import CryptoKit

// Disabled test-mode reference, not a listener or production HTTP parser. The
// caller must strictly parse JSON, enforce CORS/Host/TLS, and authenticate Mac
// responses before any live use. Dispatch below writes only to in-memory rows.
struct SyntheticOperation: Codable { let challenge:RequestChallenge;let signature:Data;let payload:Data }
struct SyntheticTask: Codable { let id:UUID;let task:String? }
struct SyntheticResult: Codable { let id:UUID;let status:String }
final class SyntheticRoutes {
    private let lock=NSLock(),hostID:UUID,expectedHost:String,expectedOrigin:String,clock:()->Double,wallClock:()->Int64,sessionDeadline:Double
    private var peer:DeviceAuthority,scopeValue:(String,String),rows:[UUID:SyntheticResult]=[:],pending:[UUID:Bool]=[:],active:UUID?
    private let ownerConfirm:(String)->Bool
    private lazy var gate=RequestProofGate(hostID:hostID,sessionDeadline:sessionDeadline,clock:clock,wallClock:wallClock,authority:{[weak self] in self?.peer},scope:{[weak self] in self?.scopeValue})
    init(hostID:UUID,expectedHost:String,expectedOrigin:String,peer:DeviceAuthority,scope:(String,String),sessionDeadline:Double,clock:@escaping ()->Double,wallClock:@escaping ()->Int64,ownerConfirm:@escaping (String)->Bool) {
        self.hostID=hostID;self.expectedHost=expectedHost;self.expectedOrigin=expectedOrigin;self.peer=peer;self.scopeValue=scope;self.sessionDeadline=sessionDeadline;self.clock=clock;self.wallClock=wallClock;self.ownerConfirm=ownerConfirm
    }
    private func transport(_ host:String,_ origin:String,_ method:String)->Bool { host==expectedHost && origin==expectedOrigin && method=="POST" }
    func challenge(host:String,origin:String,method:String,intent:RequestIntent)throws->RequestChallenge {
        lock.lock();defer{lock.unlock()};guard transport(host,origin,method),intent.action != "submit" || active == nil else { throw ProofError.denied };return try gate.issue(intent)
    }
    func operation(host:String,origin:String,method:String,path:String,value:SyntheticOperation)throws->SyntheticResult {
        lock.lock()
        do {
            guard transport(host,origin,method),value.payload.count<=8192,value.challenge.intent.method==method,value.challenge.intent.path==path,
                  Data(SHA256.hash(data:value.payload))==value.challenge.intent.payloadDigest else { throw ProofError.denied }
            try gate.verify(value.challenge,signature:value.signature)
        } catch { lock.unlock();throw error }
        let action=value.challenge.intent.action
        let task: SyntheticTask
        do { task=try JSONDecoder().decode(SyntheticTask.self,from:value.payload) } catch { lock.unlock();throw ProofError.invalid }
        if action=="submit" {
            guard let text=task.task,!text.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,text.count<=4000,!text.contains("\0"),active==nil,rows[task.id]==nil,pending[task.id]==nil else { lock.unlock();throw ProofError.invalid }
            // Conservatively retain the session-wide barrier through Stop and
            // unknown outcomes; a new session requires owner reconciliation.
            active=task.id
            pending[task.id]=false
            lock.unlock();let approved=ownerConfirm(text);lock.lock()
            let cancelled=pending.removeValue(forKey:task.id) ?? true
            guard approved else { peer=DeviceAuthority(deviceID:peer.deviceID,generation:peer.generation,signingKey:peer.signingKey,revoked:true);lock.unlock();throw ProofError.denied }
            guard !cancelled,gate.stillCurrent(value.challenge.intent),rows[task.id]==nil else { lock.unlock();throw ProofError.denied }
            let row=SyntheticResult(id:task.id,status:"submitted");rows[task.id]=row;lock.unlock();return row
        }
        defer{lock.unlock()}
        guard task.task==nil,gate.stillCurrent(value.challenge.intent) else {throw ProofError.denied}
        if action=="stop",pending[task.id] != nil {pending[task.id]=true;let stopped=SyntheticResult(id:task.id,status:"cancelled");rows[task.id]=stopped;return stopped}
        if action=="status",pending[task.id] != nil {return SyntheticResult(id:task.id,status:"validating")}
        guard let row=rows[task.id] else { throw ProofError.denied }
        if action=="status" { return row }
        guard action=="stop" else { throw ProofError.denied }
        let stopped=SyntheticResult(id:row.id,status:"stopped");rows[row.id]=stopped;return stopped
    }
    func revoke(ownerConfirmed:Bool)throws {
        lock.lock();defer{lock.unlock()};guard ownerConfirmed else { throw ProofError.denied }
        peer=DeviceAuthority(deviceID:peer.deviceID,generation:peer.generation,signingKey:peer.signingKey,revoked:true)
    }
    var taskCount:Int { lock.lock();defer{lock.unlock()};return rows.count }
}
