// Actual URLSession callbacks through an in-memory catch-all URLProtocol.
// No request can fall through this protocol to the network.
import Foundation

struct DownloadFixtureFailure: Error { let message:String }
private struct FixturePlan {
    let status:Int, headers:[String:String], chunks:[Data], failure:URLError.Code?, hold:Bool, responseURL:URL?
    init(status:Int=200,headers:[String:String]=[:],chunks:[Data]=[],failure:URLError.Code?=nil,hold:Bool=false,responseURL:URL?=nil) {
        self.status=status;self.headers=headers;self.chunks=chunks;self.failure=failure;self.hold=hold;self.responseURL=responseURL
    }
}
private final class MemoryDownloadProtocol:URLProtocol,@unchecked Sendable {
    static let lock=NSLock()
    static var plans:[String:FixturePlan]=[:], requests:[String:URLRequest]=[:], stopped=Set<String>(), missing=0
    static func configure(_ name:String,_ plan:FixturePlan) {
        lock.lock();defer{lock.unlock()};plans[name]=plan;requests[name]=nil;stopped.remove(name)
    }
    static func request(_ name:String)->URLRequest? { lock.lock();defer{lock.unlock()};return requests[name] }
    static func wasStopped(_ name:String)->Bool { lock.lock();defer{lock.unlock()};return stopped.contains(name) }
    override class func canInit(with request:URLRequest)->Bool { true }
    override class func canonicalRequest(for request:URLRequest)->URLRequest { request }
    override func startLoading() {
        let name=request.url?.lastPathComponent ?? "missing-url"
        Self.lock.lock();let plan=Self.plans[name];Self.requests[name]=request;if plan==nil{Self.missing += 1};Self.lock.unlock()
        guard let plan else { client?.urlProtocol(self,didFailWithError:URLError(.unsupportedURL));return }
        if plan.hold{return}
        if let error=plan.failure { client?.urlProtocol(self,didFailWithError:URLError(error));return }
        let response=HTTPURLResponse(url:plan.responseURL ?? request.url!,statusCode:plan.status,httpVersion:"HTTP/1.1",headerFields:plan.headers)!
        client?.urlProtocol(self,didReceive:response,cacheStoragePolicy:.notAllowed)
        for chunk in plan.chunks { client?.urlProtocol(self,didLoad:chunk) }
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {
        Self.lock.lock();Self.stopped.insert(request.url?.lastPathComponent ?? "missing-url");Self.lock.unlock()
    }
}
@main struct DownloadTests {
    static var checks=0
    static func check(_ condition:@autoclosure()->Bool,_ name:String)throws {
        guard condition() else{throw DownloadFixtureFailure(message:name)};checks += 1
    }
    static func url(_ name:String)->URL { URL(string:"https://github.com/jrish11/ATLAS/releases/download/v3.7/"+name)! }
    private static func fetch(_ name:String,_ plan:FixturePlan,maximum:Int=8,expected:Int?=nil) async throws->Data {
        MemoryDownloadProtocol.configure(name,plan)
        return try await BoundedUpdateDownloader(protocolClasses:[MemoryDownloadProtocol.self]).fetch(url(name),maximum:maximum,expectedSize:expected)
    }
    private static func reject(_ name:String,_ plan:FixturePlan,maximum:Int=8,expected:Int?=nil) async throws {
        do { _=try await fetch(name,plan,maximum:maximum,expected:expected) }
        catch { checks += 1;return }
        throw DownloadFixtureFailure(message:"Accepted "+name)
    }
    static func waitStarted(_ name:String) async throws {
        for _ in 0..<200 { if MemoryDownloadProtocol.request(name) != nil{return};try await Task.sleep(nanoseconds:5_000_000) }
        throw DownloadFixtureFailure(message:"Fixture never started "+name)
    }
    static func run() async throws {
        let bytes=Data("fixture".utf8)
        let success=try await fetch("success",FixturePlan(headers:["Content-Length":"7"],chunks:[Data("fix".utf8),Data("ture".utf8)]),expected:7)
        try check(success==bytes,"Exact streamed response")
        let unknown=try await fetch("unknown-length",FixturePlan(chunks:[bytes]),expected:7)
        try check(unknown==bytes,"Unknown Content-Length checked against final size")
        let optional=try await fetch("optional-length",FixturePlan(chunks:[Data("12345678".utf8)]))
        try check(optional.count==8,"Maximum bound inclusive")
        let request=MemoryDownloadProtocol.request("success")!
        try check(request.value(forHTTPHeaderField:"Authorization")==nil,"No Authorization header")
        try check(request.value(forHTTPHeaderField:"Cookie")==nil,"No Cookie header")
        try check(request.value(forHTTPHeaderField:"User-Agent")=="ATLAS-Signed-Updater","Explicit updater agent")
        try check(request.value(forHTTPHeaderField:"Accept")=="application/octet-stream","Binary response request")
        for status in [201,204,206,301,401,404,500] { try await reject("status-\(status)",FixturePlan(status:status,chunks:[bytes])) }
        try await reject("declared-over-limit",FixturePlan(headers:["Content-Length":"9"],chunks:[bytes]))
        try await reject("declared-wrong-expected",FixturePlan(headers:["Content-Length":"6"],chunks:[bytes]),expected:7)
        try await reject("truncated",FixturePlan(headers:["Content-Length":"7"],chunks:[Data("short".utf8)]),expected:7)
        try await reject("unknown-length-truncated",FixturePlan(chunks:[Data("short".utf8)]),expected:7)
        try await reject("overflow-one-chunk",FixturePlan(chunks:[Data("123456789".utf8)]))
        try await reject("overflow-many-chunks",FixturePlan(chunks:[Data("1234".utf8),Data("5678".utf8),Data("9".utf8)]))
        try await reject("empty",FixturePlan(headers:["Content-Length":"0"]))
        try await reject("transport-error",FixturePlan(failure:.cannotConnectToHost))
        try await reject("transport-timeout",FixturePlan(failure:.timedOut))
        try await reject("spoofed-response-url",FixturePlan(chunks:[bytes],responseURL:URL(string:"https://invalid.example/file")!))
        try await reject("unredirected-asset-response",FixturePlan(chunks:[bytes],responseURL:URL(string:"https://objects.githubusercontent.com/github-production-release-asset/test")!))
        for iteration in 0..<5 {
            let name="cancel-\(iteration)";MemoryDownloadProtocol.configure(name,FixturePlan(hold:true))
            let task=Task { try await BoundedUpdateDownloader(protocolClasses:[MemoryDownloadProtocol.self]).fetch(url(name),maximum:8,expectedSize:7) }
            try await waitStarted(name);task.cancel();task.cancel()
            do { _=try await task.value;throw DownloadFixtureFailure(message:"Cancelled request returned bytes") }
            catch is CancellationError { checks += 1 }
            // Native completion/stop delivery is asynchronous after cancellation.
            for _ in 0..<100 { if MemoryDownloadProtocol.wasStopped(name){break};try await Task.sleep(nanoseconds:2_000_000) }
            try check(MemoryDownloadProtocol.wasStopped(name),"Cancelled URLSession stops mock transport")
        }
        // Independent sessions must not share body/cancellation state.
        MemoryDownloadProtocol.configure("parallel-ok",FixturePlan(chunks:[bytes]))
        MemoryDownloadProtocol.configure("parallel-cancel",FixturePlan(hold:true))
        let cancelled=Task { try await BoundedUpdateDownloader(protocolClasses:[MemoryDownloadProtocol.self]).fetch(url("parallel-cancel"),maximum:8,expectedSize:7) }
        try await waitStarted("parallel-cancel")
        let succeeded=Task { try await BoundedUpdateDownloader(protocolClasses:[MemoryDownloadProtocol.self]).fetch(url("parallel-ok"),maximum:8,expectedSize:7) }
        cancelled.cancel()
        do { _=try await cancelled.value;throw DownloadFixtureFailure(message:"Parallel cancellation ignored") } catch is CancellationError { checks += 1 }
        let parallelResult=try await succeeded.value;try check(parallelResult==bytes,"Parallel session remains independent")
        try check(MemoryDownloadProtocol.missing==0,"Every transport request intercepted by exact fixture")
        print("URLSession mock transport passed: \(checks) assertions; no network, credentials or persistent state. Actual redirect delegate and TLS remain untested.")
    }
    static func main() async {
        do {try await run()} catch {fputs("Download fixture failed: \(error)\n",stderr);exit(1)}
    }
}
