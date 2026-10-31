import Foundation
import CryptoKit
import Darwin

@main struct InstallerTests {
    static var checks=0
    static func check(_ b:@autoclosure ()throws->Bool,_ why:String)throws{guard try b() else{throw SignedUpdateError.rejected("Test: "+why)};checks+=1}
    static func reject(_ why:String,_ action:()throws->Void)throws{do{try action()}catch{checks+=1;return};throw SignedUpdateError.rejected("Unexpected acceptance: "+why)}
    static func bundle(_ app:URL,build:Int,mode:String="exit")throws {
        let fm=FileManager.default
        try fm.createDirectory(at:app.appendingPathComponent("Contents/MacOS"),withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        try fm.createDirectory(at:app.appendingPathComponent("Contents/Resources"),withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
        let info:[String:Any]=["CFBundleIdentifier":UpdateLimits.bundleID,"CFBundleVersion":String(build),"CFBundleShortVersionString":"1.\(build)","CFBundleExecutable":"Atticus","CFBundlePackageType":"APPL","ATLASUpdateEpoch":1,"ATLASUpdateInstallerProtocol":1]
        try PropertyListSerialization.data(fromPropertyList:info,format:.xml,options:0).write(to:app.appendingPathComponent("Contents/Info.plist"))
        for name in ["Atticus","PersonalKeychain","ATLASUpdateInstaller"] {try fm.copyItem(at:URL(fileURLWithPath:CommandLine.arguments[0]),to:app.appendingPathComponent("Contents/MacOS/"+name))}
        try Data(mode.utf8).write(to:app.appendingPathComponent("Contents/Resources/mode"))
        _=try UpdateProcess.run(URL(fileURLWithPath:"/usr/bin/codesign"),["--force","--sign","-","--timestamp=none",app.path])
    }
    static func main()throws {
        if ProcessInfo.processInfo.environment["ATLAS_UPDATE_ACK_NONCE"] != nil {
            let path=try UpdateInstallerIO.processPath(getpid())
            let app=URL(fileURLWithPath:path).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
            let mode=try String(contentsOf:app.appendingPathComponent("Contents/Resources/mode"),encoding:.utf8)
            if mode=="ack" {UpdateInstallerAcknowledgement.captureAtStartup();precondition(getenv("ATLAS_UPDATE_ACK_NONCE")==nil && ProcessInfo.processInfo.environment["ATLAS_UPDATE_ACK_NONCE"]==nil);let first=try UpdateInstallerAcknowledgement.sendIfRequested(),second=try UpdateInstallerAcknowledgement.sendIfRequested();precondition(first && !second);usleep(900_000);return}
            if mode=="wrongAck" {try UpdateInstallerIO.write(UpdateInstallerEvent(status:"startupReady",nonce:String(repeating:"0",count:64),transaction:UUID().uuidString),to:1);usleep(900_000);return}
            if mode=="unknown" {usleep(900_000);return}
            return
        }
        let fm=FileManager.default
        let location=fm.temporaryDirectory.appendingPathComponent("atlas-installer-fixture-"+UUID().uuidString)
        try fm.createDirectory(at:location,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        let resolved=realpath(location.path,nil)!;let root=URL(fileURLWithPath:String(cString:resolved));free(resolved)
        defer{try? fm.removeItem(at:root)}
        try check(UpdatePublisherTrust.keys.isEmpty,"Production trust stays empty")
        try reject("nonpipe stdin"){try UpdateInstallerIO.privatePipe(open("/dev/null",O_RDONLY))}
        let pipe=Pipe();try UpdateInstallerIO.privatePipe(pipe.fileHandleForReading.fileDescriptor);checks+=1
        try UpdateInstallerIO.write(UpdateInstallerEvent(status:"fixture",nonce:"x",transaction:nil),to:pipe.fileHandleForWriting.fileDescriptor)
        let event=try JSONDecoder().decode(UpdateInstallerEvent.self,from:UpdateInstallerIO.readLine(pipe.fileHandleForReading.fileDescriptor,maximum:500,timeout:0.2))
        try check(event.status=="fixture","bounded inherited pipe roundtrip")
        try reject("pipe timeout"){_=try UpdateInstallerIO.readLine(pipe.fileHandleForReading.fileDescriptor,maximum:500,timeout:0.02)}
        try UpdateInstallerIO.write(UpdateInstallerEvent(status:String(repeating:"x",count:200),nonce:"x",transaction:nil),to:pipe.fileHandleForWriting.fileDescriptor)
        try reject("oversized pipe message"){_=try UpdateInstallerIO.readLine(pipe.fileHandleForReading.fileDescriptor,maximum:30,timeout:0.2)}
        let secret=root.appendingPathComponent("archive.zip")
        try Data("fixture".utf8).write(to:secret);try fm.setAttributes([.posixPermissions:0o600],ofItemAtPath:secret.path)
        try check(try UpdateInstallerIO.regularFile(secret,maximum:100)==Data("fixture".utf8),"bounded private archive read")
        try reject("archive too large"){_=try UpdateInstallerIO.regularFile(secret,maximum:3)}
        let linked=root.appendingPathComponent("link.zip");try fm.createSymbolicLink(at:linked,withDestinationURL:secret)
        try reject("symlink archive"){_=try UpdateInstallerIO.regularFile(linked,maximum:100)}
        try fm.setAttributes([.posixPermissions:0o644],ofItemAtPath:secret.path)
        try reject("nonprivate archive"){_=try UpdateInstallerIO.regularFile(secret,maximum:100)}
        try fm.setAttributes([.posixPermissions:0o600],ofItemAtPath:secret.path)
        try check(!(try UpdateInstallerIO.processPath(getpid())).isEmpty,"kernel executable path")
        try reject("wrong process executable"){try UpdateInstallerIO.verifyProcess(getpid(),executable:URL(fileURLWithPath:"/bin/false"))}
        // A real kernel exit event, not a polling mock, gates the parent handoff.
        let sleeper=Process();sleeper.executableURL=URL(fileURLWithPath:"/bin/sleep");sleeper.arguments=["0.15"];try sleeper.run()
        let watch=try UpdateParentExitWatch(pid:sleeper.processIdentifier);try watch.wait(timeout:2);sleeper.waitUntilExit();checks+=1
        try reject("already absent parent"){_=try UpdateParentExitWatch(pid:999_999)}
        let alive=Process();alive.executableURL=URL(fileURLWithPath:"/bin/sleep");alive.arguments=["1"];try alive.run()
        let pending=try UpdateParentExitWatch(pid:alive.processIdentifier)
        try reject("live parent prevents swap"){try pending.wait(timeout:0)}
        alive.terminate();alive.waitUntilExit()
        let brokenPipe=Pipe();try brokenPipe.fileHandleForReading.close()
        try reject("closed private pipe does not terminate caller"){try UpdateInstallerIO.write(UpdateInstallerEvent(status:"closed",nonce:"x",transaction:nil),to:brokenPipe.fileHandleForWriting.fileDescriptor)}
        let snapshotApp=root.appendingPathComponent("Snapshot.app");try bundle(snapshotApp,build:1)
        let resources=snapshotApp.appendingPathComponent("Contents/Resources/Updater")
        try fm.createDirectory(at:resources,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        try Data("import os,sys\nsys.path.insert(0,os.path.dirname(__file__))\nfrom update_verify import fixture\nprint(fixture)\n".utf8).write(to:resources.appendingPathComponent("extract_update.py"))
        try Data("fixture = 'sibling dependency verified'\n".utf8).write(to:resources.appendingPathComponent("update_verify.py"))
        _=try UpdateProcess.run(URL(fileURLWithPath:"/usr/bin/codesign"),["--force","--sign","-","--timestamp=none",snapshotApp.path])
        let snapshotIdentity=try UpdateBundleValidation.verify(snapshotApp)
        var snapshotPath:URL?
        let snapshotResult=try UpdateInstallerRuntime.withExtractorSnapshot(target:snapshotApp,expected:snapshotIdentity,installationParent:root,source:resources.appendingPathComponent("extract_update.py")){copy in
            snapshotPath=copy.deletingLastPathComponent()
            try check(fm.fileExists(atPath:copy.deletingLastPathComponent().appendingPathComponent("update_verify.py").path),"snapshot includes imported verifier")
            return try UpdateProcess.run(URL(fileURLWithPath:"/usr/bin/python3"),["-I","-B",copy.path])
        }
        try check(String(data:snapshotResult,encoding:.utf8)?.contains("sibling dependency verified")==true,"snapshotted extractor executes with sibling dependency")
        try check(!fm.fileExists(atPath:snapshotPath!.path),"owned extractor snapshot removed")
        let lockTarget=root.appendingPathComponent("LockFixture.app");try bundle(lockTarget,build:1)
        let lockState=root.appendingPathComponent("lock-state")
        var shared:UpdateInstallationInterlock?=try UpdateInstallationInterlock.fixtureShared(target:lockTarget,state:lockState)
        try reject("running app excludes installer"){_=try UpdateInstallationInterlock.exclusive(target:lockTarget,state:lockState)}
        shared?.release();shared=nil
        let exclusive=try UpdateInstallationInterlock.exclusive(target:lockTarget,state:lockState)
        try reject("installer excludes startup"){_=try UpdateInstallationInterlock.fixtureShared(target:lockTarget,state:lockState)}
        exclusive.release()
        shared=try UpdateInstallationInterlock.fixtureShared(target:lockTarget,state:lockState);try check(shared != nil,"startup resumes after release");shared=nil
        let key=Curve25519.Signing.PrivateKey(),now=Date(),iso=ISO8601DateFormatter()
        let object:[String:Any]=["schema":2,"product":"ATLAS","repository":"jrish11/ATLAS","version":"v1.2","sequence":2,"channel":"stable","update_epoch":1,"build":2,"published_at":iso.string(from:now.addingTimeInterval(-60)),"expires_at":iso.string(from:now.addingTimeInterval(3600)),"minimum_macos":"26.0","architecture":"arm64","bundle_id":UpdateLimits.bundleID,"archive":["url":"https://github.com/jrish11/ATLAS/releases/download/v1.2/ATLAS-v1.2-macOS-arm64-PUBLIC.zip","sha256":SHA256.hash(data:Data("fixture".utf8)).map{String(format:"%02x",$0)}.joined(),"size":7],"changelog":"Ephemeral installer fixture."]
        let raw=try JSONSerialization.data(withJSONObject:object,options:.sortedKeys)
        let signature=try JSONSerialization.data(withJSONObject:["key_id":"fixture","algorithm":"Ed25519","signature":key.signature(for:raw).base64EncodedString()])
        for mode in ["ack","exit","wrongAck","unknown","parentBlocked","readyDenied","launchThrows","replayed"] {
            let area=root.appendingPathComponent(mode);try fm.createDirectory(at:area,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
            let target=area.appendingPathComponent("ATLAS.app"),state=area.appendingPathComponent("state")
            try bundle(target,build:1,mode:mode=="exit" ? "ack" : "exit")
            let old=try UpdateBundleValidation.verify(target)
            let request=UpdateInstallerRequest(schema:1,parentPID:getpid(),target:target.path,stateDirectory:state.path,expectedTarget:old,archive:secret.path,manifest:raw,signature:signature,includePrereleases:false,nonce:try UpdateInstallerIO.nonce())
            var ready=false,parentDone=false,launched=false
            if mode=="replayed" {try UpdateReceiptStore(directory:state).save(sequence:2,now:now)}
            let hooks=UpdateInstallerHooks(verifyBundle:{try UpdateBundleValidation.verify($0,release:$1)},verifyRelease:{r,i,receipt in try UpdateManifestVerifier.fixtureVerify(raw:r.manifest,signature:r.signature,keys:["fixture":key.publicKey.rawRepresentation],installed:i,receipt:receipt,machine:"arm64",macOS:"26.6",includePrereleases:false,now:now)},stage:{_,release,parent,_ in
                let stage=parent.appendingPathComponent("fresh.app");try bundle(stage,build:2,mode:mode)
                let result=PreparedSignedUpdate(release:release,app:stage,identity:try UpdateBundleValidation.verify(stage),archive:secret,ownedContainer:parent);result.relinquish();return result
            },parentExited:{guard mode != "parentBlocked" else{throw SignedUpdateError.rejected("fixture parent remains live")};parentDone=true},ready:{_ in ready=true;if mode=="readyDenied"{throw SignedUpdateError.rejected("fixture quit denied")}},launch:{target,record,nonce,expected in
                try check(parentDone,"launch requires parent exit");launched=true
                if mode=="launchThrows" {throw SignedUpdateError.rejected("unknown spawn result")}
                return try UpdateInstallerRuntime.launchChild(target:target,record:record,nonce:nonce,expectedIdentity:expected,acknowledgementTimeout:mode=="unknown" ? 0.02 : 5)
            })
            if mode=="ack" {
                for (field,value) in [("schema",2 as Any),("parentPID",0 as Any),("nonce","bad" as Any)] {
                    var altered=try JSONSerialization.jsonObject(with:JSONEncoder().encode(request)) as! [String:Any];altered[field]=value
                    let bad=try JSONDecoder().decode(UpdateInstallerRequest.self,from:JSONSerialization.data(withJSONObject:altered))
                    try reject("malformed installer request "+field){_=try UpdateInstallerEngine.perform(request:bad,extractor:secret,hooks:hooks)}
                    try check(!ready && !launched,"malformed input performs no handoff")
                }
                try reject("production roots reject fixture without installation access"){_=try UpdateInstallerRuntime.install(request:request)}
            }
            if mode=="replayed" {
                try reject("independently loaded replay receipt"){_=try UpdateInstallerEngine.perform(request:request,extractor:secret,hooks:hooks)}
                try check(!ready && !launched && (try UpdateBundleValidation.verify(target))==old,"replay does not dispatch")
            }else if mode=="parentBlocked" || mode=="readyDenied" {
                try reject("blocked parent"){_=try UpdateInstallerEngine.perform(request:request,extractor:secret,hooks:hooks)}
                try check(ready && !launched && (try UpdateBundleValidation.verify(target))==old,"no replacement while parent live")
                let before=try UpdateFileTree.identity(app:target)
                let pending=try UpdateInstallerRuntime.inspect(target:target,stateDirectory:state)
                try check(pending.count==1 && pending[0].record.phase=="prepared","interrupted handoff is inspect-only")
                try check(try UpdateFileTree.identity(app:target)==before,"inspection does not replay swap")
            }else{
                let result=try UpdateInstallerEngine.perform(request:request,extractor:secret,hooks:hooks)
                try check(ready && launched,"handoff sequence exercised")
                let expected=mode=="ack" ? "launched" : mode=="exit" ? "restoredStarted" : "needsInspection"
                try check(result.status==expected,"true child outcome: "+mode)
                let identity=try UpdateBundleValidation.verify(target)
                try check(identity.build==(mode=="exit" ? 1 : 2),"correct swap/rollback: "+mode)
                let store=try UpdateTransactionStore(installationParent:area,stateDirectory:state.appendingPathComponent("transactions"),verifyBundle:{try UpdateBundleValidation.verify($0)})
                let inspection=try store.recover();try check(inspection.count==1,"one dispatch receipt")
                try check(inspection[0].record.phase==(mode=="ack" ? "launched" : mode=="exit" ? "rolledBack" : "active"),"durable true outcome")
                try reject("replay after activation"){_=try UpdateInstallerEngine.perform(request:request,extractor:secret,hooks:hooks)}
                if mode=="ack" {
                    usleep(1_000_000) // confirmed synthetic new app has ended; no owner process involved
                    let restore=UpdateInstallerRequest(schema:1,parentPID:getpid(),target:target.path,stateDirectory:state.path,expectedTarget:identity,archive:"",manifest:Data(),signature:Data(),includePrereleases:false,nonce:try UpdateInstallerIO.nonce(),restoreTransaction:result.transaction)
                    var holder:UpdateInstallationInterlock?=try UpdateInstallationInterlock.fixtureShared(target:target,state:state)
                    try reject("explicit restore refuses a live startup holder"){_=try UpdateInstallerEngine.restore(request:restore,hooks:hooks)}
                    try check(try UpdateBundleValidation.verify(target)==identity,"blocked restore preserves current app")
                    holder?.release();holder=nil
                    let restored=try UpdateInstallerEngine.restore(request:restore,hooks:hooks)
                    try check(restored.status=="rolledBackNeedsLaunch","failed old startup does not claim restart")
                    try check(try UpdateBundleValidation.verify(target)==old,"explicit restore uses exact previously installed digest")
                    try check(try UpdateReceiptStore(directory:state).read().highestSequence==2,"restore never rolls anti-replay receipt backwards")
                    try reject("explicit restore cannot replay"){_=try UpdateInstallerEngine.restore(request:restore,hooks:hooks)}
                    let afterRestore=try store.recover()
                    try check(afterRestore[0].record.phase=="rolledBack","explicit restore leaves auditable rolledBack receipt")
                }
            }
            usleep(1_000_000) // bounded cleanup of the synthetic short-lived child
        }
        print("installer: \(checks) assertions passed; ephemeral signatures and real temporary child processes; production roots empty")
    }
}
