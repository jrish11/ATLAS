import Foundation
import Darwin
import Security
import CryptoKit

// This component has no network client and accepts no trust keys or credentials.
// Compiling it into the app does not enable updates: publisher roots remain empty.
struct UpdateInstallerRequest: Codable {
    let schema: Int
    let parentPID: Int32
    let target: String
    let stateDirectory: String
    let expectedTarget: UpdateBundleIdentity
    let archive: String
    let manifest: Data
    let signature: Data
    let includePrereleases: Bool
    let nonce: String
    var restoreTransaction:String? = nil
}

struct UpdateInstallerEvent: Codable, Equatable {
    let status: String
    let nonce: String
    let transaction: String?
}

enum UpdateInstallerIO {
    static func reject(_ message: String) -> SignedUpdateError { .rejected(message) }
    static func canonicalPath(_ path:String)throws->String {
        guard let pointer=realpath(path,nil) else{throw reject("Cannot resolve installer path.")}
        defer{free(pointer)};return String(cString:pointer)
    }
    static func privatePipe(_ fd: Int32) throws {
        var s=stat()
        guard fstat(fd,&s)==0,s.st_mode&S_IFMT==S_IFIFO,s.st_uid==geteuid(),s.st_nlink==0 else {throw reject("Installer requires private inherited pipes.")}
    }
    static func readLine(_ fd:Int32,maximum:Int,timeout:TimeInterval) throws -> Data {
        let end=ProcessInfo.processInfo.systemUptime+timeout
        var data=Data()
        while ProcessInfo.processInfo.systemUptime<end {
            var p=pollfd(fd:fd,events:Int16(POLLIN),revents:0)
            let result=poll(&p,1,100)
            if result<0 {if errno==EINTR {continue};throw reject("Installer pipe failed.")}
            if result==0 {continue}
            var byte:UInt8=0;let count=Darwin.read(fd,&byte,1)
            guard count==1 else {throw reject("Installer pipe closed before acknowledgement.")}
            if byte==10 {guard !data.isEmpty else{throw reject("Empty installer message.")};return data}
            data.append(byte)
            guard data.count<=maximum else {throw reject("Installer message is too large.")}
        }
        throw reject("Installer acknowledgement timed out.")
    }
    static func write<T:Encodable>(_ value:T,to fd:Int32) throws {
        guard fcntl(fd,F_SETNOSIGPIPE,1)==0 else{throw reject("Cannot secure installer pipe writes.")}
        var bytes=try JSONEncoder().encode(value);bytes.append(10)
        try bytes.withUnsafeBytes { raw in
            var done=0
            while done<raw.count {
                let n=Darwin.write(fd,raw.baseAddress!.advanced(by:done),raw.count-done)
                if n<0 && errno==EINTR {continue}
                guard n>0 else {throw reject("Installer pipe write failed.")};done+=n
            }
        }
    }
    static func processPath(_ pid:pid_t)throws->String {
        var bytes=[CChar](repeating:0,count:4 * Int(MAXPATHLEN))
        guard proc_pidpath(pid,&bytes,UInt32(bytes.count))>0 else {throw reject("Cannot verify installer peer process.")}
        return String(cString:bytes)
    }
    static func verifyProcess(_ pid:pid_t,executable:URL)throws {
        guard try processPath(pid)==executable.path else {throw reject("Installer peer executable differs.")}
        var guest:SecCode?
        let attributes=[kSecGuestAttributePid as String:NSNumber(value:pid)] as CFDictionary
        guard SecCodeCopyGuestWithAttributes(nil,attributes,SecCSFlags(),&guest)==errSecSuccess,let guest,
              SecCodeCheckValidity(guest,SecCSFlags(rawValue:kSecCSStrictValidate),nil)==errSecSuccess else {throw reject("Installer peer code signature is invalid.")}
        var staticCode:SecStaticCode?,path:CFURL?
        guard SecCodeCopyStaticCode(guest,SecCSFlags(),&staticCode)==errSecSuccess,let staticCode,
              SecCodeCopyPath(staticCode,SecCSFlags(),&path)==errSecSuccess,let path,
              [(try canonicalPath(executable.path)),(try canonicalPath(executable.deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().path))].contains(try canonicalPath((path as URL).path)) else {throw reject("Installer peer code identity differs.")}
    }
    static func regularFile(_ url:URL,maximum:Int,requirePrivate:Bool=true)throws->Data {
        guard url.isFileURL,try canonicalPath(url.path)==url.path else{throw reject("Unsafe installer input path.")}
        let fd=open(url.path,O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC)
        guard fd>=0 else{throw reject("Cannot open installer input.")};defer{close(fd)}
        var before=stat()
        guard fstat(fd,&before)==0,before.st_mode&S_IFMT==S_IFREG,before.st_uid==geteuid(),before.st_nlink==1,before.st_mode&0o022==0,(!requirePrivate || before.st_mode&0o077==0),before.st_size>0,before.st_size<=maximum else{throw reject("Unsafe installer input file.")}
        var data=Data(),buffer=[UInt8](repeating:0,count:65536)
        while true {
            let n=Darwin.read(fd,&buffer,min(buffer.count,maximum-data.count+1))
            if n<0 && errno==EINTR {continue}
            guard n>=0 else{throw reject("Cannot read installer input.")}
            if n==0 {break};data.append(contentsOf:buffer.prefix(n))
            guard data.count<=maximum else{throw reject("Installer input grew beyond its bound.")}
        }
        var after=stat()
        guard data.count==before.st_size,fstat(fd,&after)==0,before.st_ino==after.st_ino,before.st_dev==after.st_dev,before.st_size==after.st_size,before.st_mtimespec.tv_sec==after.st_mtimespec.tv_sec,before.st_mtimespec.tv_nsec==after.st_mtimespec.tv_nsec,before.st_ctimespec.tv_sec==after.st_ctimespec.tv_sec,before.st_ctimespec.tv_nsec==after.st_ctimespec.tv_nsec else{throw reject("Installer input changed while reading.")}
        return data
    }
    static func validNonce(_ nonce:String)->Bool {nonce.count==64 && nonce.allSatisfy({$0.isASCII && $0.isHexDigit})}
    static func nonce()throws->String {
        var bytes=[UInt8](repeating:0,count:32)
        guard SecRandomCopyBytes(kSecRandomDefault,bytes.count,&bytes)==errSecSuccess else{throw reject("Cannot create installer challenge.")}
        return bytes.map{String(format:"%02x",$0)}.joined()
    }
}

// Cooperating releases acquire a shared lock before profile/bootstrap. The
// helper takes exclusive ownership only after its verified parent exits. First
// adoption requires a manual install: both old and new bundles need marker 1.
final class UpdateInstallationInterlock {
    private let fd:Int32
    private static var running:UpdateInstallationInterlock?
    private var held=true
    func release(){if held{flock(fd,LOCK_UN);held=false}}
    private init(target:URL,state:URL,exclusive:Bool)throws {
        _ = try UpdateReceiptStore(directory:state)
        guard try UpdateInstallerIO.canonicalPath(target.path)==target.path else{throw UpdateInstallerIO.reject("Unsafe startup interlock target.")}
        let key=SHA256.hash(data:Data(target.path.utf8)).map{String(format:"%02x",$0)}.joined()
        let path=state.appendingPathComponent("running-"+key+".lock")
        fd=open(path.path,O_RDWR|O_CREAT|O_NOFOLLOW|O_CLOEXEC,0o600)
        guard fd>=0 else{throw UpdateInstallerIO.reject("Cannot open startup interlock.")}
        var before=stat()
        guard fstat(fd,&before)==0,before.st_mode&S_IFMT==S_IFREG,before.st_uid==geteuid(),before.st_nlink==1,before.st_mode&0o077==0 else{close(fd);throw UpdateInstallerIO.reject("Unsafe startup interlock.")}
        guard flock(fd,(exclusive ? LOCK_EX : LOCK_SH)|LOCK_NB)==0 else{close(fd);throw UpdateInstallerIO.reject("Another application or update holds the startup interlock.")}
        var after=stat()
        guard lstat(path.path,&after)==0,before.st_dev==after.st_dev,before.st_ino==after.st_ino else{flock(fd,LOCK_UN);close(fd);throw UpdateInstallerIO.reject("Startup interlock changed.")}
    }
    deinit{release();close(fd)}
    static func acquireForRunningApp(target:URL)throws {
        guard running==nil else{return}
        running=try UpdateInstallationInterlock(target:target,state:UpdateInstallerRuntime.stateDirectory(),exclusive:false)
    }
    static func exclusive(target:URL,state:URL)throws->UpdateInstallationInterlock {try .init(target:target,state:state,exclusive:true)}
    #if UPDATER_TESTING
    static func fixtureShared(target:URL,state:URL)throws->UpdateInstallationInterlock {try .init(target:target,state:state,exclusive:false)}
    #endif
    static func requireProtocol(_ target:URL)throws {
        let info=try PropertyListSerialization.propertyList(from:Data(contentsOf:target.appendingPathComponent("Contents/Info.plist")),format:nil) as? [String:Any]
        guard let n=info?["ATLASUpdateInstallerProtocol"] as? NSNumber,CFGetTypeID(n) != CFBooleanGetTypeID(),n.intValue==1,n.doubleValue==1 else{throw UpdateInstallerIO.reject("This installation needs a manual updater-protocol upgrade first.")}
    }
}

// Register while the verified parent is still running, so PID reuse cannot turn
// a different process into the process whose exit authorizes replacement.
final class UpdateParentExitWatch {
    private let queue:Int32
    init(pid:pid_t)throws {
        queue=kqueue();guard queue>=0 else{throw UpdateInstallerIO.reject("Cannot watch parent exit.")}
        guard fcntl(queue,F_SETFD,FD_CLOEXEC)==0 else{close(queue);throw UpdateInstallerIO.reject("Cannot secure parent exit watch.")}
        var change=kevent(ident:UInt(pid),filter:Int16(EVFILT_PROC),flags:UInt16(EV_ADD|EV_ENABLE|EV_ONESHOT),fflags:UInt32(NOTE_EXIT),data:0,udata:nil)
        guard kevent(queue,&change,1,nil,0,nil)==0 else {close(queue);throw UpdateInstallerIO.reject("Parent exited before installer handshake.")}
    }
    deinit{close(queue)}
    func wait(timeout:TimeInterval)throws {
        var event=kevent(),limit=timespec(tv_sec:Int(timeout),tv_nsec:0)
        let n=kevent(queue,nil,0,&event,1,&limit)
        guard n==1,event.filter==Int16(EVFILT_PROC),event.fflags&UInt32(NOTE_EXIT) != 0,event.flags&UInt16(EV_ERROR)==0 else{throw UpdateInstallerIO.reject("Parent exit was not confirmed; installation remains pending inspection.")}
    }
}

// The state machine is shared with synthetic tests. Hooks are internal; the
// executable entry point always constructs the production verification hooks.
struct UpdateInstallerHooks {
    var verifyBundle:(URL,AuthenticatedUpdate?)throws->UpdateBundleIdentity
    var verifyRelease:(UpdateInstallerRequest,UpdateInstalledVersion,UpdateReplayReceipt)throws->AuthenticatedUpdate
    var stage:(Data,AuthenticatedUpdate,URL,URL)throws->PreparedSignedUpdate
    var parentExited:()throws->Void
    var ready:(String)throws->Void
    var launch:(URL,UpdateTransactionRecord,String,UpdateBundleIdentity)throws->UpdateChildOutcome
}
enum UpdateChildOutcome:Equatable {case acknowledged, exited, unknown}
struct UpdateInstallerResult {let status:String;let transaction:String}

enum UpdateInstallerEngine {
    static func perform(request:UpdateInstallerRequest,extractor:URL,hooks:UpdateInstallerHooks)throws->UpdateInstallerResult {
        guard request.schema==1,request.parentPID>1,UpdateInstallerIO.validNonce(request.nonce),request.manifest.count<=UpdateLimits.manifest,request.signature.count<=UpdateLimits.signature else{throw UpdateInstallerIO.reject("Malformed installer request.")}
        let target=URL(fileURLWithPath:request.target),parent=target.deletingLastPathComponent(),state=URL(fileURLWithPath:request.stateDirectory)
        guard try UpdateInstallerIO.canonicalPath(target.path)==target.path,target.pathExtension=="app" else{throw UpdateInstallerIO.reject("Unsafe installation target.")}
        try UpdateInstallationInterlock.requireProtocol(target)
        let old=try hooks.verifyBundle(target,nil)
        guard old==request.expectedTarget else{throw UpdateInstallerIO.reject("Installed app changed before handoff.")}
        let info=try PropertyListSerialization.propertyList(from:Data(contentsOf:target.appendingPathComponent("Contents/Info.plist")),format:nil) as? [String:Any]
        guard let version=info?["CFBundleShortVersionString"] as? String else{throw UpdateInstallerIO.reject("Installed version is missing.")}
        let installed=UpdateInstalledVersion(version:version.hasPrefix("v") ? version : "v"+version,build:old.build,epoch:old.epoch)
        let receipts=try UpdateReceiptStore(directory:state)
        let release=try hooks.verifyRelease(request,installed,receipts.read())
        let bytes=try UpdateInstallerIO.regularFile(URL(fileURLWithPath:request.archive),maximum:UpdateLimits.archive,requirePrivate:false)
        let prepared=try hooks.stage(bytes,release,parent,extractor)
        // Extraction is repeated by this process. The UI's staged app is never
        // installed. Move the newly authenticated tree beside the target so the
        // transaction's pinned-directory exchange can operate on siblings.
        let candidate=parent.appendingPathComponent(".atlas-candidate-"+UUID().uuidString+".app")
        guard renameatx_np(AT_FDCWD,prepared.app.path,AT_FDCWD,candidate.path,UInt32(RENAME_EXCL))==0 else{try? prepared.discard();throw UpdateInstallerIO.reject("Cannot place verified update beside the app.")}
        try prepared.discard()
        let transactionDirectory=state.appendingPathComponent("transactions",isDirectory:true)
        _ = try UpdateReceiptStore(directory:transactionDirectory)
        let store=try UpdateTransactionStore(installationParent:parent,stateDirectory:transactionDirectory,verifyBundle:{try hooks.verifyBundle($0,nil)})
        try UpdateInstallationInterlock.requireProtocol(candidate)
        let new=try hooks.verifyBundle(candidate,release)
        let record=try store.prepare(stagedApp:candidate,targetApp:target,expectedOld:old,expectedNew:new,order:.init(version:release.version,sequence:release.sequence,epoch:release.epoch,build:release.build))
        try hooks.ready(record.id)
        try hooks.parentExited()
        // No swap occurs before the verified parent exit. The transaction
        // rechecks every identity immediately before its atomic exchange.
        guard release.expires>Date() else{throw UpdateInstallerIO.reject("Signed release expired while waiting for parent exit.")}
        _ = try hooks.verifyRelease(request,installed,receipts.read())
        let interlock=try UpdateInstallationInterlock.exclusive(target:target,state:state)
        let active=try store.activate(id:record.id)
        do {try receipts.save(sequence:release.sequence,now:Date())}
        catch { _ = try store.rollback(id:active.id);throw error }
        interlock.release() // new app must acquire shared ownership at startup
        let outcome:UpdateChildOutcome
        do {outcome=try hooks.launch(target,active,request.nonce,active.new)}
        catch { // Launch errors may have happened after spawn: never infer exit.
            return UpdateInstallerResult(status:"needsInspection",transaction:active.id)
        }
        switch outcome {
        case .acknowledged:
            _ = try store.markLaunched(id:active.id)
            return UpdateInstallerResult(status:"launched",transaction:active.id)
        case .exited:
            guard let restoreLock=try? UpdateInstallationInterlock.exclusive(target:target,state:state) else{return UpdateInstallerResult(status:"needsInspection",transaction:active.id)}
            _ = try store.rollback(id:active.id)
            restoreLock.release()
            let restored=try? hooks.launch(target,active,request.nonce,active.old)
            return UpdateInstallerResult(status:restored == .acknowledged ? "restoredStarted" : "rolledBackNeedsLaunch",transaction:active.id)
        case .unknown:
            return UpdateInstallerResult(status:"needsInspection",transaction:active.id)
        }
    }
    static func restore(request:UpdateInstallerRequest,hooks:UpdateInstallerHooks)throws->UpdateInstallerResult {
        guard request.schema==1,request.parentPID>1,UpdateInstallerIO.validNonce(request.nonce),let id=request.restoreTransaction,UUID(uuidString:id) != nil else{throw UpdateInstallerIO.reject("Malformed local-backup restore request.")}
        let target=URL(fileURLWithPath:request.target),parent=target.deletingLastPathComponent(),state=URL(fileURLWithPath:request.stateDirectory)
        guard try UpdateInstallerIO.canonicalPath(target.path)==target.path else{throw UpdateInstallerIO.reject("Unsafe local-backup restore target.")}
        try UpdateInstallationInterlock.requireProtocol(target)
        let current=try hooks.verifyBundle(target,nil)
        guard current==request.expectedTarget else{throw UpdateInstallerIO.reject("Current app changed before restore confirmation.")}
        let store=try UpdateTransactionStore(installationParent:parent,stateDirectory:state.appendingPathComponent("transactions"),verifyBundle:{try hooks.verifyBundle($0,nil)})
        func selected()throws->UpdateTransactionRecord {
            guard let item=try store.recover().first(where:{$0.record.id==id}),["launched","activeNeedsLaunchConfirmation"].contains(item.disposition),item.record.target==target.lastPathComponent,item.record.new==current else{throw UpdateInstallerIO.reject("The selected local backup is no longer restorable.")}
            let backup=parent.appendingPathComponent(item.record.backup)
            try UpdateInstallationInterlock.requireProtocol(backup)
            guard try hooks.verifyBundle(backup,nil)==item.record.old else{throw UpdateInstallerIO.reject("Saved local backup identity changed.")}
            return item.record
        }
        let record=try selected()
        try hooks.ready(record.id);try hooks.parentExited()
        let lock=try UpdateInstallationInterlock.exclusive(target:target,state:state)
        guard try selected()==record else{throw UpdateInstallerIO.reject("Local backup changed during quit handshake.")}
        _ = try store.rollback(id:id)
        lock.release()
        let outcome=try? hooks.launch(target,record,request.nonce,record.old)
        return UpdateInstallerResult(status:outcome == .acknowledged ? "restoredStarted" : "rolledBackNeedsLaunch",transaction:id)
    }

}

enum UpdateInstallerAcknowledgement {
    private static var captured:[String:String]?
    static func captureAtStartup() {
        guard captured==nil else{return}
        let names=["ATLAS_UPDATE_ACK_NONCE","ATLAS_UPDATE_ACK_TRANSACTION","ATLAS_UPDATE_ACK_TARGET","ATLAS_UPDATE_ACK_PARENT_PID"]
        var values=[String:String]()
        for name in names {if let pointer=getenv(name){values[name]=String(cString:pointer)};unsetenv(name)}
        captured=values
    }
    // Call after successful application startup, never at main() entry. This is
    // only a liveness/identity receipt, not proof that every app feature works.
    @discardableResult static func sendIfRequested()throws->Bool {
        if captured==nil {captureAtStartup()}
        let env=captured ?? [:];captured=[:]
        guard let nonce=env["ATLAS_UPDATE_ACK_NONCE"] else{return false}
        guard UpdateInstallerIO.validNonce(nonce),let transaction=env["ATLAS_UPDATE_ACK_TRANSACTION"],UUID(uuidString:transaction) != nil,
              let targetPath=env["ATLAS_UPDATE_ACK_TARGET"],let parentText=env["ATLAS_UPDATE_ACK_PARENT_PID"],let parent=Int32(parentText),getppid()==parent else{throw UpdateInstallerIO.reject("Invalid startup acknowledgement request.")}
        let target=URL(fileURLWithPath:targetPath)
        guard try UpdateInstallerIO.processPath(getpid())==target.appendingPathComponent("Contents/MacOS/Atticus").path else{throw UpdateInstallerIO.reject("Startup acknowledgement target differs.")}
        try UpdateInstallerIO.privatePipe(STDOUT_FILENO)
        // A new child cannot mint authority via its environment. The receiver
        // also owns this inherited pipe and verifies this exact child PID.
        try UpdateInstallerIO.write(UpdateInstallerEvent(status:"startupReady",nonce:nonce,transaction:transaction),to:STDOUT_FILENO)
        let sink=open("/dev/null",O_WRONLY|O_CLOEXEC)
        if sink>=0 { _=dup2(sink,STDOUT_FILENO);close(sink) }
        return true
    }
}

enum UpdateInstallerRuntime {
    static func stateDirectory()->URL {
        FileManager.default.urls(for:.applicationSupportDirectory,in:.userDomainMask)[0].resolvingSymlinksInPath().appendingPathComponent("ATLAS Updates",isDirectory:true)
    }
    static func launchChild(target:URL,record:UpdateTransactionRecord,nonce:String,expectedIdentity:UpdateBundleIdentity?=nil,acknowledgementTimeout:TimeInterval=30)throws->UpdateChildOutcome {
        let child=Process(),ack=Pipe(),exited=DispatchSemaphore(value:0)
        child.terminationHandler={_ in exited.signal()}
        func confirmedExit()->Bool{if !child.isRunning{return true};return exited.wait(timeout:.now()+0.25) == .success}
        child.executableURL=target.appendingPathComponent("Contents/MacOS/Atticus")
        child.arguments=[];child.currentDirectoryURL=target.deletingLastPathComponent()
        // No old API environment, profile, browser session or auth material is
        // transferred. The app resolves its existing per-device stores itself.
        child.environment=["PATH":"/usr/bin:/bin:/usr/sbin:/sbin","HOME":NSHomeDirectory(),"ATLAS_UPDATE_ACK_NONCE":nonce,"ATLAS_UPDATE_ACK_TRANSACTION":record.id,"ATLAS_UPDATE_ACK_TARGET":target.path,"ATLAS_UPDATE_ACK_PARENT_PID":String(getpid())]
        child.standardOutput=ack;child.standardInput=FileHandle.nullDevice;child.standardError=FileHandle.nullDevice
        do{try child.run()}catch{return .exited} // Process.run throwing means no child was launched.
        try? ack.fileHandleForWriting.close()
        do {
            let bytes=try UpdateInstallerIO.readLine(ack.fileHandleForReading.fileDescriptor,maximum:4096,timeout:acknowledgementTimeout)
            let event=try JSONDecoder().decode(UpdateInstallerEvent.self,from:bytes)
            guard event==UpdateInstallerEvent(status:"startupReady",nonce:nonce,transaction:record.id),child.isRunning else{return confirmedExit() ? .exited : .unknown}
            try UpdateInstallerIO.verifyProcess(child.processIdentifier,executable:target.appendingPathComponent("Contents/MacOS/Atticus"))
            guard try UpdateBundleValidation.verify(target)==(expectedIdentity ?? record.new) else{return .unknown}
            return .acknowledged
        }catch{return confirmedExit() ? .exited : .unknown}
    }
    static func withExtractorSnapshot<T>(target:URL,expected:UpdateBundleIdentity,installationParent:URL,source:URL,body:(URL)throws->T)throws->T {
        let script=try UpdateInstallerIO.regularFile(source,maximum:1_048_576,requirePrivate:false)
        let verifier=try UpdateInstallerIO.regularFile(source.deletingLastPathComponent().appendingPathComponent("update_verify.py"),maximum:1_048_576,requirePrivate:false)
        guard try UpdateBundleValidation.verify(target)==expected else{throw UpdateInstallerIO.reject("Trusted extractor bundle changed.")}
        let work=installationParent.appendingPathComponent(".atlas-extractor-"+UUID().uuidString,isDirectory:true)
        try FileManager.default.createDirectory(at:work,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        var node=stat();guard lstat(work.path,&node)==0 else{throw UpdateInstallerIO.reject("Cannot pin extractor snapshot.")}
        defer{try? UpdateOwnedStaging.remove(work,device:node.st_dev,inode:node.st_ino)}
        let copy=work.appendingPathComponent("extract_update.py"),dependency=work.appendingPathComponent("update_verify.py")
        for (url,data) in [(copy,script),(dependency,verifier)] {
            try data.write(to:url,options:.withoutOverwriting)
            try FileManager.default.setAttributes([.posixPermissions:0o600],ofItemAtPath:url.path)
        }
        return try body(copy)
    }
    static func install(request:UpdateInstallerRequest)throws->UpdateInstallerResult {
        // Empty production trust roots block before touching any installation.
        guard UpdatePublisherTrust.configured else{throw UpdateInstallerIO.reject("No publisher trust root is embedded; signed installation is disabled.")}
        try UpdateInstallerIO.privatePipe(STDIN_FILENO);try UpdateInstallerIO.privatePipe(STDOUT_FILENO)
        guard getppid()==request.parentPID,request.stateDirectory==stateDirectory().path else{throw UpdateInstallerIO.reject("Installer parent or state binding differs.")}
        let target=URL(fileURLWithPath:request.target)
        try UpdateInstallerIO.verifyProcess(request.parentPID,executable:target.appendingPathComponent("Contents/MacOS/Atticus"))
        guard try UpdateInstallerIO.processPath(getpid())==target.appendingPathComponent("Contents/MacOS/ATLASUpdateInstaller").path else{throw UpdateInstallerIO.reject("Installer is not embedded in the target app.")}
        let old=try UpdateBundleValidation.verify(target)
        guard old==request.expectedTarget else{throw UpdateInstallerIO.reject("Installer bundle identity changed.")}
        let watch=try UpdateParentExitWatch(pid:request.parentPID)
        let extractor=target.appendingPathComponent("Contents/Resources/Updater/extract_update.py")
        #if arch(arm64)
        let machine="arm64"
        #else
        let machine="x86_64"
        #endif
        let os=ProcessInfo.processInfo.operatingSystemVersion
        let hooks=UpdateInstallerHooks(verifyBundle:{try UpdateBundleValidation.verify($0,release:$1)},verifyRelease:{r,i,receipt in try UpdateManifestVerifier.verify(raw:r.manifest,signature:r.signature,installed:i,receipt:receipt,machine:machine,macOS:"\(os.majorVersion).\(os.minorVersion).\(os.patchVersion)",includePrereleases:r.includePrereleases)},stage:{bytes,release,parent,source in
            return try withExtractorSnapshot(target:target,expected:old,installationParent:parent,source:source){copy in
                try UpdateArchiveStager.stage(bytes:bytes,release:release,installationParent:parent,extractor:copy,cancelled:{false})
            }
        },parentExited:{try watch.wait(timeout:180)},ready:{id in try UpdateInstallerIO.write(UpdateInstallerEvent(status:"readyToQuit",nonce:request.nonce,transaction:id),to:STDOUT_FILENO)},launch:{try launchChild(target:$0,record:$1,nonce:$2,expectedIdentity:$3)})
        if request.restoreTransaction != nil {return try UpdateInstallerEngine.restore(request:request,hooks:hooks)}
        return try UpdateInstallerEngine.perform(request:request,extractor:extractor,hooks:hooks)
    }
    static func inspect(target:URL,stateDirectory:URL)throws->[UpdateRecoveryInspection] {
        // Inspection classifies only. No recovery path automatically swaps or
        // launches an app after a crash. Explicit rollback UI is not supplied
        // by this helper; unknown/live processes must first be resolved.
        let store=try UpdateTransactionStore(installationParent:target.deletingLastPathComponent(),stateDirectory:stateDirectory.appendingPathComponent("transactions"),verifyBundle:{try UpdateBundleValidation.verify($0)})
        return try store.recover()
    }
}

enum UpdateInstallerLauncher {
    // Returns only after helper revalidation and the exit watch are ready. The
    // native controller may then quit; it must not terminate itself on error.
    // Run off the main actor: extraction/verification can take several seconds.
    static func start(prepared:PreparedSignedUpdate,target:URL,stateDirectory:URL,parentPID:pid_t)throws->Process {
        guard UpdatePublisherTrust.configured else{throw UpdateInstallerIO.reject("Signed installation is disabled until a publisher key is embedded.")}
        guard parentPID==getpid(),stateDirectory.path==UpdateInstallerRuntime.stateDirectory().path else{throw UpdateInstallerIO.reject("Installer launch binding differs.")}
        try UpdateInstallationInterlock.requireProtocol(target)
        let identity=try UpdateBundleValidation.verify(target)
        try UpdateInstallerIO.verifyProcess(parentPID,executable:target.appendingPathComponent("Contents/MacOS/Atticus"))
        let nonce=try UpdateInstallerIO.nonce()
        let request=UpdateInstallerRequest(schema:1,parentPID:parentPID,target:target.path,stateDirectory:stateDirectory.path,expectedTarget:identity,archive:prepared.archive.path,manifest:prepared.release.rawManifest,signature:prepared.release.rawSignature,includePrereleases:prepared.release.channel=="prerelease",nonce:nonce)
        return try launch(request:request,target:target)
    }
    static func startRollback(transactionID:String,target:URL,stateDirectory:URL,parentPID:pid_t)throws->Process {
        guard UpdatePublisherTrust.configured else{throw UpdateInstallerIO.reject("Local-backup restore is disabled until updater trust is configured.")}
        guard UUID(uuidString:transactionID) != nil,parentPID==getpid(),stateDirectory.path==UpdateInstallerRuntime.stateDirectory().path else{throw UpdateInstallerIO.reject("Restore launch binding differs.")}
        try UpdateInstallationInterlock.requireProtocol(target)
        let identity=try UpdateBundleValidation.verify(target)
        try UpdateInstallerIO.verifyProcess(parentPID,executable:target.appendingPathComponent("Contents/MacOS/Atticus"))
        let request=UpdateInstallerRequest(schema:1,parentPID:parentPID,target:target.path,stateDirectory:stateDirectory.path,expectedTarget:identity,archive:"",manifest:Data(),signature:Data(),includePrereleases:false,nonce:try UpdateInstallerIO.nonce(),restoreTransaction:transactionID)
        return try launch(request:request,target:target)
    }
    private static func launch(request:UpdateInstallerRequest,target:URL)throws->Process {
        let nonce=request.nonce
        let process=Process(),input=Pipe(),output=Pipe()
        process.executableURL=target.appendingPathComponent("Contents/MacOS/ATLASUpdateInstaller")
        process.arguments=[];process.standardInput=input;process.standardOutput=output;process.standardError=FileHandle.nullDevice
        process.environment=["PATH":"/usr/bin:/bin:/usr/sbin:/sbin","HOME":NSHomeDirectory()]
        try process.run()
        try? input.fileHandleForReading.close();try? output.fileHandleForWriting.close()
        do {
            try UpdateInstallerIO.write(request,to:input.fileHandleForWriting.fileDescriptor);try input.fileHandleForWriting.close()
            let event=try JSONDecoder().decode(UpdateInstallerEvent.self,from:UpdateInstallerIO.readLine(output.fileHandleForReading.fileDescriptor,maximum:4096,timeout:180))
            guard event.status=="readyToQuit",event.nonce==nonce,let id=event.transaction,UUID(uuidString:id) != nil,process.isRunning else{throw UpdateInstallerIO.reject("Installer did not confirm the quit handshake.")}
            return process
        }catch{ // No quit handshake means parent stays open; helper cannot swap.
            if process.isRunning {process.terminate()};throw error
        }
    }
}

#if ATLAS_UPDATE_INSTALLER
@main struct UpdateInstallerMain {
    static func main() {
        signal(SIGPIPE,SIG_IGN)
        do {
            try UpdateInstallerIO.privatePipe(STDIN_FILENO);try UpdateInstallerIO.privatePipe(STDOUT_FILENO)
            let data=try UpdateInstallerIO.readLine(STDIN_FILENO,maximum:400_000,timeout:10)
            let request=try JSONDecoder().decode(UpdateInstallerRequest.self,from:data)
            let result=try UpdateInstallerRuntime.install(request:request)
            try UpdateInstallerIO.write(UpdateInstallerEvent(status:result.status,nonce:request.nonce,transaction:result.transaction),to:STDOUT_FILENO)
        }catch{exit(1)}
    }
}
#endif
