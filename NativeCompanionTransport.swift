import Foundation

// Native-only bridge to the existing Agents supervisor's inherited stdin and
// stdout. Network input never receives its capability or calls this directly.
final class NativeCompanionTransport: CompanionRegistryTransport {
    private final class Pending {let signal=DispatchSemaphore(value:0);let id:String;var state:String?;init(id:String){self.id=id}}
    private let lock=NSLock(),send:([String:Any])->Bool,stop:()->Void,timeout:Double
    private var pending:[String:Pending]=[:],closed=false
    init(timeout:Double=65,send:@escaping ([String:Any])->Bool,stop:@escaping ()->Void) {self.timeout=timeout;self.send=send;self.stop=stop}
    func call(action:String,id:UUID,task:String?,deadline:Double?,wallExpiry:Int64?) throws -> String {
        guard ["submit","status","stop","check"].contains(action),(action=="submit") == (task != nil),!Thread.isMainThread else {throw ProofError.denied}
        let call=UUID().uuidString.replacingOccurrences(of:"-",with:"").lowercased(),taskID=id.uuidString.replacingOccurrences(of:"-",with:"").lowercased(),request=Pending(id:taskID)
        lock.lock();guard !closed else {lock.unlock();throw ProofError.denied};pending[call]=request;lock.unlock()
        var body:[String:Any]=["action":"remote-companion-"+action,"call":call,"id":taskID]
        if let task {guard let deadline,let wallExpiry else {lock.lock();pending.removeValue(forKey:call);lock.unlock();throw ProofError.denied};body["task"]=task;body["deadline"]=deadline;body["wallExpires"]=wallExpiry}
        guard send(body) else {lock.lock();pending.removeValue(forKey:call);lock.unlock();throw ProofError.denied}
        let completed=request.signal.wait(timeout:.now()+timeout) == .success
        lock.lock();pending.removeValue(forKey:call);let result=request.state;lock.unlock()
        guard completed,let result else {throw ProofError.denied};return result
    }
    func bindDevice(_ device:[String:Any],id:UUID) -> Bool {
        guard !Thread.isMainThread else{return false};let call=UUID().uuidString.replacingOccurrences(of:"-",with:"").lowercased(),taskID=id.uuidString.replacingOccurrences(of:"-",with:"").lowercased(),request=Pending(id:taskID)
        lock.lock();guard !closed else {lock.unlock();return false};pending[call]=request;lock.unlock()
        guard send(["action":"remote-companion-bind","call":call,"id":taskID,"device":device]) else {lock.lock();pending.removeValue(forKey:call);lock.unlock();return false}
        let completed=request.signal.wait(timeout:.now()+timeout) == .success
        lock.lock();pending.removeValue(forKey:call);let result=request.state;lock.unlock();return completed && result=="bound"
    }
    func recoveryClear() -> Bool {
        (try? call(action:"check",id:UUID(),task:nil,deadline:nil,wallExpiry:nil)) == "clear"
    }
    func receive(_ event:[String:Any]) {
        guard event["event"] as? String == "remote-companion-result",let call=event["call"] as? String,let result=event["result"] as? [String:Any],let state=result["status"] as? String,let id=result["id"] as? String else {return}
        lock.lock();let request=pending[call];if request?.id == id && request?.state == nil {request?.state=state;request?.signal.signal()};lock.unlock()
    }
    func close() {
        lock.lock();guard !closed else {lock.unlock();return};closed=true;let requests=Array(pending.values);pending.removeAll();lock.unlock()
        for item in requests {item.signal.signal()};stop()
    }
}

// The supervisor output reader delivers correlated results off the main UI
// queue, so a native stop or recovery review never waits on its own callback.
final class CompanionEventRouter {
    private let lock=NSLock();private weak var target:NativeCompanionTransport?
    func set(_ value:NativeCompanionTransport?) {lock.lock();target=value;lock.unlock()}
    func deliver(_ event:[String:Any]) {lock.lock();let value=target;lock.unlock();value?.receive(event)}
}
