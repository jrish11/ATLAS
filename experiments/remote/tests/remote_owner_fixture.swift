import Cocoa
import Darwin

@main struct Fixture {
    static func main() throws {
        precondition(!webAgentActionAllowed("remote-enable") && !webAgentActionAllowed("remote-review-clear") && !webAgentActionAllowed("remote-stop"))
        precondition(webAgentActionAllowed("codex-start"))
        let root = CommandLine.arguments[1], result = CommandLine.arguments[2], mode = CommandLine.arguments[3]
        try? FileManager.default.removeItem(atPath: result)
        var scale = mach_timebase_info_data_t(); mach_timebase_info(&scale)
        var offset = 0.0
        let clock: () -> Double = { Double(mach_continuous_time()) * Double(scale.numer) / Double(scale.denom) / 1_000_000_000 + offset }
        let expiry = clock() + 30
        let scope = RemoteNativeOwner.Scope(folder:"/tmp/project",id:"fixture",revision:"r1",device:1,inode:2,expires:expiry)
        var requests = 0
        var owner: RemoteNativeOwner!
        owner = RemoteNativeOwner(scope:scope,clock:clock,decide:{ target, reply in
            precondition(target["task"] as? String == "synthetic task")
            requests += 1
            if mode == "stop" { DispatchQueue.main.asyncAfter(deadline:.now()+0.1) { owner.stop() } }
            else if mode == "expiry" { offset = 31 }
            else { reply(mode == "allow") }
        })
        try owner.start(executable:"/usr/bin/python3",arguments:[root+"/tests/remote_owner_worker.py",String(expiry),result,mode])
        let deadline = Date().addingTimeInterval(mode == "stop" || mode == "scope" || mode == "expiry" ? 1 : 5)
        while !FileManager.default.fileExists(atPath:result) && Date() < deadline { RunLoop.current.run(until:Date().addingTimeInterval(0.05)) }
        if mode == "allow" {
            let answer = try String(contentsOfFile:result,encoding:.utf8)
            precondition(requests == 1 && answer == "allow")
        } else { precondition(requests == (mode == "scope" ? 0 : 1)); precondition(!FileManager.default.fileExists(atPath:result)) }
        owner.stop(); print("remote native \(mode) fixture ok")
    }
}
