import Foundation
import Darwin

struct TestFailure: Error { let message: String }
@main struct UpdateTransactionTests {
    static var checks = 0
    static func check(_ value: @autoclosure () throws -> Bool, _ message: String) throws {
        guard try value() else { throw TestFailure(message:message) }; checks += 1
    }
    static func rejects(_ name: String, _ body: () throws -> Void) throws {
        do { try body() } catch { checks += 1; return }; throw TestFailure(message:"Accepted " + name)
    }
    final class Fixture {
        let root: URL, parent: URL, state: URL, target: URL, staged: URL, outside: URL
        let store: UpdateTransactionStore
        let old: UpdateBundleIdentity, new: UpdateBundleIdentity
        init() throws {
            root = FileManager.default.temporaryDirectory.appendingPathComponent("atlas-transaction-test-" + UUID().uuidString)
            // /var is a system symlink on macOS; resolve the freshly-created
            // fixture root before handing it to the no-symlink module.
            try FileManager.default.createDirectory(at:root,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
            guard let canonical = realpath(root.path,nil) else { throw TestFailure(message:"fixture realpath") }; defer { free(canonical) }
            let resolved = URL(fileURLWithPath:String(cString:canonical))
            parent=resolved.appendingPathComponent("installation"); state=resolved.appendingPathComponent("state"); outside=resolved.appendingPathComponent("untouched")
            target=parent.appendingPathComponent("ATLAS.app"); staged=parent.appendingPathComponent("Candidate.app")
            for url in [parent,state,outside] { try FileManager.default.createDirectory(at:url,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700]) }
            try Data("private fixture sentinel".utf8).write(to:outside.appendingPathComponent("profile"))
            try Self.app(target,1); try Self.app(staged,2)
            old=try UpdateFileTree.identity(app:target); new=try UpdateFileTree.identity(app:staged)
            store=try UpdateTransactionStore(installationParent:parent,stateDirectory:state,verifyBundle:UpdateFileTree.identity)
        }
        deinit { try? FileManager.default.removeItem(at:root) }
        static func app(_ url: URL,_ build: Int) throws {
            let contents=url.appendingPathComponent("Contents"), executable=contents.appendingPathComponent("MacOS")
            try FileManager.default.createDirectory(at:executable,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
            let plist:[String:Any]=["CFBundleIdentifier":"fixture.atlas", "CFBundleVersion":String(build), "ATLASUpdateEpoch":1]
            try PropertyListSerialization.data(fromPropertyList:plist,format:.xml,options:0).write(to:contents.appendingPathComponent("Info.plist"))
            try Data("not an executable; fixture version \(build)".utf8).write(to:executable.appendingPathComponent("ATLAS"))
        }
        func prepare() throws -> UpdateTransactionRecord { try store.prepare(stagedApp:staged,targetApp:target,expectedOld:old,expectedNew:new,order:UpdateTransactionOrder(version:"1.2",sequence:2,epoch:1,build:2)) }
        func disposition() throws -> String { try store.recover().first!.disposition }
        func untouched() throws { try check(try String(contentsOf:outside.appendingPathComponent("profile"),encoding:.utf8)=="private fixture sentinel","Unrelated profile preserved") }
    }
    static func main() throws {
        if CommandLine.arguments.count == 5 && CommandLine.arguments[1] == "--crash" {
            let root = URL(fileURLWithPath:CommandLine.arguments[2])
            let store = try UpdateTransactionStore(installationParent:root.appendingPathComponent("installation"),stateDirectory:root.appendingPathComponent("state"),verifyBundle:UpdateFileTree.identity)
            store.fault = { name in if name == CommandLine.arguments[4] { _exit(73) } }
            _ = try store.activate(id:CommandLine.arguments[3]); _exit(74)
        }
        do {
            let f=try Fixture(), record=try f.prepare()
            try check(try f.disposition()=="prepared","Prepared inspection")
            let active=try f.store.activate(id:record.id)
            try check(active.phase=="active","Activation receipt")
            try check(try UpdateFileTree.identity(app:f.target)==f.new,"New app at stable name")
            try check(try UpdateFileTree.identity(app:f.parent.appendingPathComponent(active.backup))==f.old,"Previous app preserved")
            try check(!FileManager.default.fileExists(atPath:f.staged.path),"Staged name no longer occupied")
            try check(try f.disposition()=="activeNeedsLaunchConfirmation","No invented launch success")
            try check(try f.store.markLaunched(id:record.id).phase=="launched","Explicit launch receipt")
            try rejects("double activation") { _=try f.store.activate(id:record.id) }
            try rejects("double launch receipt") { _=try f.store.markLaunched(id:record.id) }
            try f.untouched()
        }
        do {
            let f=try Fixture(), r=try f.prepare(); _=try f.store.activate(id:r.id)
            let rolled=try f.store.rollback(id:r.id)
            try check(rolled.phase=="rolledBack","Failed launch rollback receipt")
            try check(try UpdateFileTree.identity(app:f.target)==f.old,"Original app restored atomically")
            try check(try UpdateFileTree.identity(app:f.parent.appendingPathComponent(r.backup))==f.new,"Failed new app retained for inspection")
            try rejects("double rollback") { _=try f.store.rollback(id:r.id) }
            try check(try f.disposition()=="rolledBack","Rollback inspected")
            try f.untouched()
        }
        for point in ["beforeSwap","afterSwap","beforeBackup","afterBackup","beforeReceipt","afterReceipt"] {
            let f=try Fixture(), r=try f.prepare()
            f.store.fault={ name in if name==point { throw TestFailure(message:"injected " + point) } }
            try rejects("fault " + point) { _=try f.store.activate(id:r.id) }
            f.store.fault=nil
            let fresh=try UpdateTransactionStore(installationParent:f.parent,stateDirectory:f.state,verifyBundle:UpdateFileTree.identity)
            let before=try FileManager.default.contentsOfDirectory(atPath:f.parent.path).sorted()
            let inspection=try fresh.recover().first!
            let expected = point=="beforeSwap" ? "notSwappedNeedsReview" : (["afterSwap","beforeBackup"].contains(point) ? "swappedBackupPending" : "activeNeedsLaunchConfirmation")
            try check(inspection.disposition==expected,"Crash classification " + point)
            try check(try FileManager.default.contentsOfDirectory(atPath:f.parent.path).sorted()==before,"Recovery has no filesystem mutation " + point)
            try rejects("uncertain activation retry " + point) { _=try fresh.activate(id:r.id) }
            if point != "beforeSwap" { _=try fresh.rollback(id:r.id); try check(try UpdateFileTree.identity(app:f.target)==f.old,"Explicit rollback after " + point) }
            try f.untouched()
        }
        for point in ["beforeRollback","afterRollback"] {
            let f=try Fixture(), r=try f.prepare(); _=try f.store.activate(id:r.id)
            f.store.fault={ name in if name==point { throw TestFailure(message:"rollback fault") } }
            try rejects("rollback fault") { _=try f.store.rollback(id:r.id) }; f.store.fault=nil
            try check(try f.disposition()==(point=="beforeRollback" ? "rollbackNotAppliedNeedsReview" : "rollbackAppliedNeedsReview"),"Interrupted rollback classified")
            if point=="beforeRollback" { _=try f.store.rollback(id:r.id); try check(try UpdateFileTree.identity(app:f.target)==f.old,"Fresh explicit rollback of proven not-applied transaction") }
        }
        do {
            let f=try Fixture(),r=try f.prepare()
            try rejects("cancel before swap") { _=try f.store.activate(id:r.id,cancelled:{ true }) }
            try check(try UpdateFileTree.identity(app:f.target)==f.old,"Cancelled activation preserves installed app")
            try check(try f.disposition()=="cancelled","Durable cancellation")
            try rejects("retry cancelled transaction") { _=try f.store.activate(id:r.id) }
            let retry=try f.prepare(); try check(retry.id != r.id,"Fresh explicit attempt after pre-swap cancellation")
        }
        do {
            let f=try Fixture(),r=try f.prepare(); var calls=0
            try rejects("late cancellation before boundary") { _=try f.store.activate(id:r.id,cancelled:{ calls += 1; return calls==2 }) }
            try check(calls==2 && (try UpdateFileTree.identity(app:f.target))==f.old,"Last boundary cancellation checked")
        }
        do {
            let f=try Fixture(),r=try f.prepare(); _=try f.store.activate(id:r.id)
            try rejects("rollback cancellation") { _=try f.store.rollback(id:r.id,cancelled:{ true }) }
            try check(try UpdateFileTree.identity(app:f.target)==f.new,"Cancelled rollback preserves active app")
        }
        do {
            let f=try Fixture(),r=try f.prepare()
            try Data("modified".utf8).write(to:f.staged.appendingPathComponent("Contents/MacOS/ATLAS"))
            try rejects("changed staged bytes") { _=try f.store.activate(id:r.id) }
            try check(try f.disposition()=="conflict","Changed staged app reported")
            try check(try UpdateFileTree.identity(app:f.target)==f.old,"Changed stage never installed")
        }
        do {
            let f=try Fixture(),r=try f.prepare(); let moved=f.parent.appendingPathComponent("Original.app")
            try FileManager.default.moveItem(at:f.target,to:moved); try Fixture.app(f.target,1)
            try rejects("replaced installed inode") { _=try f.store.activate(id:r.id) }
        }
        do {
            let f=try Fixture(),r=try f.prepare()
            try FileManager.default.createDirectory(at:f.parent.appendingPathComponent(r.backup),withIntermediateDirectories:false)
            try rejects("backup collision") { _=try f.store.activate(id:r.id) }
        }
        do {
            let f=try Fixture(),r=try f.prepare(); let lock=open(f.parent.appendingPathComponent(".atlas-update.lock").path,O_RDWR)
            guard lock>=0 else { throw TestFailure(message:"fixture lock unavailable") }; defer { close(lock) }
            guard flock(lock,LOCK_EX|LOCK_NB)==0 else { throw TestFailure(message:"fixture lock acquisition") }
            try rejects("concurrent transaction lock") { _=try f.store.activate(id:r.id) }; flock(lock,LOCK_UN)
            _=try f.store.activate(id:r.id)
        }
        do {
            let f=try Fixture(); _=try f.prepare()
            try rejects("second pending transaction") { _=try f.prepare() }
            try rejects("invalid id traversal") { _=try f.store.activate(id:"../other") }
        }
        do {
            let f=try Fixture(),r=try f.prepare(); _=try f.store.activate(id:r.id); _=try f.store.markLaunched(id:r.id)
            let next=f.parent.appendingPathComponent("Next.app"); try Fixture.app(next,3)
            let n=try UpdateFileTree.identity(app:next)
            try rejects("stale sequence") { _=try f.store.prepare(stagedApp:next,targetApp:f.target,expectedOld:f.new,expectedNew:n,order:UpdateTransactionOrder(version:"1.3",sequence:2,epoch:1,build:3)) }
            let second=try f.store.prepare(stagedApp:next,targetApp:f.target,expectedOld:f.new,expectedNew:n,order:UpdateTransactionOrder(version:"1.3",sequence:3,epoch:1,build:3))
            _=try f.store.activate(id:second.id)
            try check(try UpdateFileTree.identity(app:f.target)==n,"Later monotonic update succeeds")
            try check(try f.store.recover().first(where: { $0.record.id==r.id })!.disposition=="historicalCompleted","Historical receipt does not become a false current conflict")
        }
        do {
            let f=try Fixture(); let link=f.staged.appendingPathComponent("Contents/secret-link")
            try FileManager.default.createSymbolicLink(at:link,withDestinationURL:f.outside.appendingPathComponent("profile"))
            try rejects("app symlink") { _=try UpdateFileTree.identity(app:f.staged) }
        }
        do {
            let f=try Fixture(); let hard=f.staged.appendingPathComponent("Contents/hard")
            try FileManager.default.linkItem(at:f.staged.appendingPathComponent("Contents/MacOS/ATLAS"),to:hard)
            try rejects("hard linked app file") { _=try UpdateFileTree.identity(app:f.staged) }
        }
        do {
            let f=try Fixture(); let fifo=f.staged.appendingPathComponent("Contents/fifo")
            guard mkfifo(fifo.path,0o600)==0 else { throw TestFailure(message:"mkfifo fixture") }
            try rejects("special file without blocking") { _=try UpdateFileTree.identity(app:f.staged) }
        }
        do {
            let f=try Fixture(); let path=f.staged.appendingPathComponent("Contents/MacOS/ATLAS").path
            let value="fixture"
            let result=value.withCString { setxattr(path,"user.atlas.fixture",$0,value.utf8.count,0,0) }
            guard result==0 else { throw TestFailure(message:"setxattr fixture") }
            try check(try UpdateFileTree.identity(app:f.staged) != f.new,"Extended attribute bound by digest")
        }
        do {
            let f=try Fixture(),r=try f.prepare()
            let moved=f.parent.deletingLastPathComponent().appendingPathComponent("moved-installation")
            try FileManager.default.moveItem(at:f.parent,to:moved)
            try FileManager.default.createDirectory(at:f.parent,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
            try rejects("replaced installation parent") { _=try f.store.activate(id:r.id) }
        }
        do {
            let f=try Fixture(),r=try f.prepare(); let journal=f.state.appendingPathComponent(r.id+".json")
            try FileManager.default.removeItem(at:journal); try FileManager.default.createSymbolicLink(at:journal,withDestinationURL:f.outside.appendingPathComponent("profile"))
            try rejects("symlink journal") { _=try f.store.recover() }
            try f.untouched()
        }
        do {
            let f=try Fixture(); let chmod=Process(); chmod.executableURL=URL(fileURLWithPath:"/bin/chmod")
            chmod.arguments=["+a","everyone deny write",f.staged.appendingPathComponent("Contents/MacOS/ATLAS").path]
            try chmod.run(); chmod.waitUntilExit(); try check(chmod.terminationStatus==0,"Fixture file ACL created")
            try check(try UpdateFileTree.identity(app:f.staged) != f.new,"ACL bound to app digest")
        }
        do {
            let f=try Fixture(); let chmod=Process(); chmod.executableURL=URL(fileURLWithPath:"/bin/chmod")
            chmod.arguments=["+a","everyone allow add_file",f.parent.path]
            try chmod.run(); chmod.waitUntilExit(); try check(chmod.terminationStatus==0,"Fixture unsafe directory ACL created")
            try rejects("Installation parent allow ACL") { _=try UpdateTransactionStore(installationParent:f.parent,stateDirectory:f.state,verifyBundle:UpdateFileTree.identity) }
        }
        do {
            let f=try Fixture(),r=try f.prepare(); let journal=f.state.appendingPathComponent(r.id+".json")
            try Data("malformed".utf8).write(to:journal)
            try rejects("Malformed journal") { _=try f.store.recover() }
            try check(try UpdateFileTree.identity(app:f.target)==f.old,"Malformed journal does not change target")
        }
        do {
            let f=try Fixture()
            try rejects("Wrong expected identifier") { _=try f.store.prepare(stagedApp:f.staged,targetApp:f.target,expectedOld:f.old,expectedNew:UpdateBundleIdentity(bundleIdentifier:"other",build:2,epoch:1,digest:f.new.digest),order:UpdateTransactionOrder(version:"1.2",sequence:2,epoch:1,build:2)) }
            try rejects("Wrong release build") { _=try f.store.prepare(stagedApp:f.staged,targetApp:f.target,expectedOld:f.old,expectedNew:f.new,order:UpdateTransactionOrder(version:"1.3",sequence:2,epoch:1,build:3)) }
            try rejects("Staged bundle outside parent") { _=try f.store.prepare(stagedApp:f.outside.appendingPathComponent("Other.app"),targetApp:f.target,expectedOld:f.old,expectedNew:f.new,order:UpdateTransactionOrder(version:"1.2",sequence:2,epoch:1,build:2)) }
        }
        for point in ["beforeSwap","afterSwap","beforeBackup","afterBackup","beforeReceipt","afterReceipt"] {
            let f=try Fixture(), r=try f.prepare(), child=Process()
            child.executableURL=URL(fileURLWithPath:CommandLine.arguments[0])
            child.arguments=["--crash",f.parent.deletingLastPathComponent().path,r.id,point]
            try child.run(); child.waitUntilExit()
            try check(child.terminationStatus==73,"Actual subprocess fault reached " + point)
            let fresh=try UpdateTransactionStore(installationParent:f.parent,stateDirectory:f.state,verifyBundle:UpdateFileTree.identity)
            let expected = point=="beforeSwap" ? "notSwappedNeedsReview" : (["afterSwap","beforeBackup"].contains(point) ? "swappedBackupPending" : "activeNeedsLaunchConfirmation")
            try check(try fresh.recover().first!.disposition==expected,"Durable subprocess crash recovery " + point)
            try rejects("Crash replay " + point) { _=try fresh.activate(id:r.id) }
            try f.untouched()
        }
        do {
            let f=try Fixture(),r=try f.prepare()
            try check(try f.store.cancelPrepared(id:r.id).phase=="cancelled","Explicit owner discard marks unstarted receipt")
            try check(try f.disposition()=="cancelled","Cancelled transaction inspection")
            try check(try UpdateFileTree.identity(app:f.target)==f.old,"Discard does not swap app")
            try check(try UpdateFileTree.identity(app:f.staged)==f.new,"Discard keeps candidate for inspection")
            try rejects("Repeated pending discard"){_=try f.store.cancelPrepared(id:r.id)}
            try rejects("Activate discarded transaction"){_=try f.store.activate(id:r.id)}
            try f.untouched()
        }
        do {
            let f=try Fixture(),r=try f.prepare();_=try f.store.activate(id:r.id)
            try rejects("Discard active update"){_=try f.store.cancelPrepared(id:r.id)}
            try check(try UpdateFileTree.identity(app:f.target)==f.new,"Active update not silently discarded")
        }
        do {
            let f=try Fixture(),r=try f.prepare()
            try Data("changed".utf8).write(to:f.staged.appendingPathComponent("new-file"))
            try rejects("Discard changed pending input"){_=try f.store.cancelPrepared(id:r.id)}
        }
        print("Update transaction tests passed: \(checks) assertions; temporary fake bundles only; no app launch, profile access, Keychain, network or signing keys.")
    }
}
