import Foundation
import CryptoKit

// This private transport is supplied only by the native supervisor owner. It
// must correlate calls, report uncertain replies as unknown and never retry.
protocol CompanionRegistryTransport: AnyObject {
    func call(action:String,id:UUID,task:String?,deadline:Double?,wallExpiry:Int64?) throws -> String
    func close()
}
protocol CompanionTaskRoutes: AnyObject {
    func challenge(host:String,origin:String,method:String,intent:RequestIntent)throws->RequestChallenge
    func operation(host:String,origin:String,method:String,path:String,value:SyntheticOperation)throws->SyntheticResult
    func revoke(ownerConfirmed:Bool)throws
    func quiesce()->Bool
    func shutdown()
}
extension SyntheticRoutes: CompanionTaskRoutes {
    func quiesce()->Bool {try? revoke(ownerConfirmed:true);return false}
    func shutdown() {}
}

final class RegistryRoutes: CompanionTaskRoutes {
    private let lock=NSLock(),hostID:UUID,expectedHost:String,expectedOrigin:String,clock:()->Double,wallClock:()->Int64,sessionDeadline:Double,transport:CompanionRegistryTransport
    private var peer:DeviceAuthority,scopeValue:(String,String),active:UUID?,revoked=false,inflight=0
    private lazy var gate=RequestProofGate(hostID:hostID,sessionDeadline:sessionDeadline,clock:clock,wallClock:wallClock,authority:{[weak self] in self?.peer},scope:{[weak self] in self?.scopeValue})
    init(hostID:UUID,expectedHost:String,expectedOrigin:String,peer:DeviceAuthority,scope:(String,String),sessionDeadline:Double,clock:@escaping ()->Double,wallClock:@escaping ()->Int64,transport:CompanionRegistryTransport) {
        self.hostID=hostID;self.expectedHost=expectedHost;self.expectedOrigin=expectedOrigin;self.peer=peer;self.scopeValue=scope;self.sessionDeadline=sessionDeadline;self.clock=clock;self.wallClock=wallClock;self.transport=transport
    }
    private func validTransport(_ host:String,_ origin:String,_ method:String)->Bool {host==expectedHost && origin==expectedOrigin && method=="POST"}
    func challenge(host:String,origin:String,method:String,intent:RequestIntent)throws->RequestChallenge {
        lock.lock();defer{lock.unlock()}
        guard !revoked,validTransport(host,origin,method),intent.action != "submit" || active == nil else {throw ProofError.denied}
        return try gate.issue(intent)
    }
    func operation(host:String,origin:String,method:String,path:String,value:SyntheticOperation)throws->SyntheticResult {
        lock.lock();var held=true
        defer {if held {lock.unlock()}}
        do {
            guard !revoked,validTransport(host,origin,method),value.payload.count<=8192,value.challenge.intent.method==method,value.challenge.intent.path==path,Data(SHA256.hash(data:value.payload))==value.challenge.intent.payloadDigest else {throw ProofError.denied}
            try gate.verify(value.challenge,signature:value.signature)
            let task=try JSONDecoder().decode(SyntheticTask.self,from:value.payload),action=value.challenge.intent.action
            if action=="submit" {
                guard active==nil,let text=task.task,!text.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty,text.count<=4000,!text.contains("\0") else {throw ProofError.denied}
                active=task.id
            } else {guard task.task==nil,active==task.id else {throw ProofError.denied}}
            let remaining=value.challenge.intent.expiresAt.subtractingReportingOverflow(wallClock())
            guard !remaining.overflow,remaining.partialValue>0,remaining.partialValue<=30 else {throw ProofError.expired}
            let requestDeadline=min(sessionDeadline,clock()+Double(remaining.partialValue)),wallExpiry=value.challenge.intent.expiresAt
            inflight += 1;held=false;lock.unlock()
            // An IPC failure has an unknown result and must never be retried.
            let state=(try? transport.call(action:action,id:task.id,task:task.task,deadline:action=="submit" ? requestDeadline : nil,wallExpiry:action=="submit" ? wallExpiry : nil)) ?? "unknown"
            lock.lock();inflight -= 1;let current = !revoked && gate.stillCurrent(value.challenge.intent);lock.unlock()
            guard current else {throw ProofError.denied}
            let allowed:Set<String>=["submitted","validating","reserving","dispatching","cancelled","failed","unknown","queued","running","needs-owner","completed-unverified","stopped","cancelling","review-required"]
            return SyntheticResult(id:task.id,status:allowed.contains(state) ? state : "unknown")
        } catch {throw error}
    }
    func quiesce()->Bool {
        lock.lock();defer{lock.unlock()};revoked=true
        peer=DeviceAuthority(deviceID:peer.deviceID,generation:peer.generation,signingKey:peer.signingKey,revoked:true)
        return inflight==0
    }
    func shutdown(){transport.close()}
    func revoke(ownerConfirmed:Bool)throws {guard ownerConfirmed else {throw ProofError.denied};_=quiesce();shutdown()}
}
