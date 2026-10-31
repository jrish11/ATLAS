import Foundation
import Darwin

// The replay receipt is local update metadata only. No profile or credential is
// copied, restored or included in an update transaction.
// Immutable path/inode binding; every read/write is serialized by an OS flock.
final class UpdateReceiptStore: @unchecked Sendable {
    let directory:URL
    private let device:dev_t,inode:ino_t
    init(directory:URL) throws {
        self.directory=directory
        if !FileManager.default.fileExists(atPath:directory.path) {
            try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        }
        var node=stat();guard lstat(directory.path,&node)==0 else{throw SignedUpdateError.rejected("Cannot pin update state.")}
        device=node.st_dev;inode=node.st_ino
        try validateDirectory()
    }
    private func validateDirectory() throws {
        var s=stat()
        guard lstat(directory.path,&s)==0, s.st_mode&S_IFMT==S_IFDIR,s.st_uid==geteuid(),s.st_mode&0o077==0,s.st_dev==device,s.st_ino==inode else {throw SignedUpdateError.rejected("Update state directory must be private and owned by you.")}
        guard let resolved=realpath(directory.path,nil) else {throw SignedUpdateError.rejected("Cannot resolve update state directory.")}
        defer{free(resolved)}
        guard String(cString:resolved)==directory.path else {throw SignedUpdateError.rejected("Update state directory contains a symbolic link.")}
    }
    private func locked<T>(_ work:()throws->T)throws->T {
        try validateDirectory()
        let fd=open(directory.appendingPathComponent(".receipt.lock").path,O_RDWR|O_CREAT|O_NOFOLLOW|O_CLOEXEC,0o600)
        guard fd>=0 else{throw SignedUpdateError.rejected("Cannot lock update receipt.")};defer{close(fd)}
        var s=stat();guard fstat(fd,&s)==0,s.st_mode&S_IFMT==S_IFREG,s.st_uid==geteuid(),s.st_mode&0o077==0,s.st_nlink==1 else{throw SignedUpdateError.rejected("Unsafe update receipt lock.")}
        guard flock(fd,LOCK_EX|LOCK_NB)==0 else{throw SignedUpdateError.rejected("Another update is changing its receipt.")};defer{flock(fd,LOCK_UN)}
        try validateDirectory();return try work()
    }
    func read() throws -> UpdateReplayReceipt {try locked{try readUnlocked()}}
    private func readUnlocked() throws -> UpdateReplayReceipt {
        try validateDirectory();let url=directory.appendingPathComponent("trusted-release.json")
        let fd=open(url.path,O_RDONLY|O_NOFOLLOW|O_CLOEXEC)
        if fd<0 && errno==ENOENT {return UpdateReplayReceipt(highestSequence:0,lastTrustedTime:Date(timeIntervalSince1970:0))}
        guard fd>=0 else {throw SignedUpdateError.rejected("Cannot safely read update receipt.")};defer{close(fd)}
        var s=stat();guard fstat(fd,&s)==0,s.st_mode&S_IFMT==S_IFREG,s.st_uid==geteuid(),s.st_mode&0o077==0,s.st_nlink==1,s.st_size<=4096 else {throw SignedUpdateError.rejected("Unsafe update receipt.")}
        var data=Data(),buffer=[UInt8](repeating:0,count:4097)
        while data.count<=4096 {
            let n=Darwin.read(fd,&buffer,4097-data.count)
            if n<0 && errno==EINTR{continue}
            guard n>=0 else{throw SignedUpdateError.rejected("Cannot read update receipt.")}
            if n==0{break};data.append(contentsOf:buffer.prefix(n))
        }
        var after=stat()
        guard data.count<=4096,data.count==s.st_size,fstat(fd,&after)==0,s.st_dev==after.st_dev,s.st_ino==after.st_ino,s.st_size==after.st_size,s.st_mtimespec.tv_sec==after.st_mtimespec.tv_sec,s.st_mtimespec.tv_nsec==after.st_mtimespec.tv_nsec,s.st_ctimespec.tv_sec==after.st_ctimespec.tv_sec,s.st_ctimespec.tv_nsec==after.st_ctimespec.tv_nsec else{throw SignedUpdateError.rejected("Update receipt changed while reading.")}
        let receipt=try JSONDecoder().decode(UpdateReplayReceipt.self,from:data)
        guard receipt.highestSequence>=0,receipt.lastTrustedTime.timeIntervalSince1970.isFinite else {throw SignedUpdateError.rejected("Malformed update receipt.")};return receipt
    }
    func save(sequence:Int,now:Date) throws {try locked{try saveUnlocked(sequence:sequence,now:now)}}
    private func saveUnlocked(sequence:Int,now:Date)throws {
        try validateDirectory();let old=try readUnlocked()
        guard sequence>=old.highestSequence,now>=old.lastTrustedTime.addingTimeInterval(-300) else {throw SignedUpdateError.rejected("Update receipt cannot move backwards.")}
        let next=UpdateReplayReceipt(highestSequence:sequence,lastTrustedTime:max(old.lastTrustedTime,now))
        let temp=directory.appendingPathComponent(".receipt-"+UUID().uuidString)
        let fd=open(temp.path,O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC,0o600)
        guard fd>=0 else {throw SignedUpdateError.rejected("Cannot create update receipt.")}
        defer{close(fd);unlink(temp.path)}
        let data=try JSONEncoder().encode(next)
        try FileHandle(fileDescriptor:fd,closeOnDealloc:false).write(contentsOf:data)
        guard fsync(fd)==0,rename(temp.path,directory.appendingPathComponent("trusted-release.json").path)==0 else {throw SignedUpdateError.rejected("Cannot persist update receipt.")}
        let parent=open(directory.path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);guard parent>=0 else{throw SignedUpdateError.rejected("Update state changed.")};defer{close(parent)}
        guard fsync(parent)==0 else{throw SignedUpdateError.rejected("Cannot sync update receipt.")}
    }
}

enum SignedUpdatePhase:Equatable {case idle,checking,available,downloading,prepared,installing,cancelled,blocked,failed}

private final class UpdateCancellation: @unchecked Sendable {
    private let lock=NSLock();private var stopped=false
    func cancel(){lock.lock();stopped=true;lock.unlock()}
    var cancelled:Bool{lock.lock();defer{lock.unlock()};return stopped}
}
@MainActor final class SignedUpdateCoordinator {
    private(set) var phase:SignedUpdatePhase = .idle
    private(set) var message="Signed updates are disabled until a publisher key is approved and embedded. Manual replacement remains available."
    private(set) var release:AuthenticatedUpdate?
    private(set) var prepared:PreparedSignedUpdate?
    var changed:(()->Void)?
    private var operation:Task<Void,Never>?
    private var generation=UUID()
    private var cancellation=UpdateCancellation()
    private let downloader:UpdateDownloading
    init(downloader:UpdateDownloading=BoundedUpdateDownloader()){self.downloader=downloader}
    var busy:Bool{[.checking,.downloading,.installing].contains(phase)}
    func cancel(){guard phase != .installing else{return};generation=UUID();cancellation.cancel();operation?.cancel();operation=nil;guard clearPrepared() else{return};phase = .cancelled;message="Cancelled. The installed app was not replaced.";changed?()}
    @discardableResult func clearPrepared()->Bool {
        if let prepared {do{try prepared.discard();self.prepared=nil}catch{phase = .blocked;message="Staged update could not be removed safely; it needs inspection.";changed?();return false}}
        return true
    }
    func check(includePrereleases:Bool,installed:UpdateInstalledVersion,machine:String,macOS:String,receipt:UpdateReplayReceipt) {
        guard !busy else{return}
        // This check precedes URLSession creation or state writes. A feed cannot
        // supply its own trust root, and settings cannot turn this gate on.
        guard UpdatePublisherTrust.configured else{phase = .blocked;message="Signed updates are not configured. No request was sent. Use a verified manual package.";changed?();return}
        guard clearPrepared() else{return};release=nil;phase = .checking;message="Checking signed release metadata…";changed?()
        let id=UUID();generation=id;cancellation=UpdateCancellation()
        let channel=includePrereleases ? "prerelease" : "stable"
        let root="https://github.com/"+UpdateLimits.repository+"/releases/download/atlas-update-feed/"+channel
        operation=Task { [weak self] in
            guard let self else{return}
            do {
                async let raw=downloader.fetch(URL(string:root+".manifest.json")!,maximum:UpdateLimits.manifest,expectedSize:nil)
                async let sig=downloader.fetch(URL(string:root+".signature.json")!,maximum:UpdateLimits.signature,expectedSize:nil)
                let authenticated=try await UpdateManifestVerifier.verify(raw:raw,signature:sig,installed:installed,receipt:receipt,machine:machine,macOS:macOS,includePrereleases:includePrereleases)
                try Task.checkCancellation();guard generation==id else{return}
                release=authenticated;phase = .available;message="Verified \(authenticated.version), build \(authenticated.build). Review the release notes before downloading.";changed?()
            }catch{guard generation==id else{return};phase = Task.isCancelled ? .cancelled : .failed;message=Self.safeMessage(error);changed?()}
        }
    }
    func download(installationParent:URL,extractor:URL){
        guard phase == .available,let selected=release else{return}
        phase = .downloading;message="Downloading and verifying the signed archive…";changed?()
        let id=UUID();generation=id;cancellation=UpdateCancellation()
        let token=cancellation
        operation=Task { [weak self] in
            guard let self else{return}
            do {
                let bytes=try await downloader.fetch(selected.url,maximum:UpdateLimits.archive,expectedSize:selected.size)
                try Task.checkCancellation()
                let result=try await Task.detached {
                    try UpdateArchiveStager.stage(bytes:bytes,release:selected,installationParent:installationParent,extractor:extractor,cancelled:{token.cancelled})
                }.value
                guard generation==id,!Task.isCancelled else{try? result.discard();return}
                prepared=result;phase = .prepared;message="Archive and app verified. Installation requires confirmation and quitting ATLAS. Your profile and Keychain will not be replaced.";changed?()
            }catch{guard generation==id else{return};phase = Task.isCancelled ? .cancelled : .failed;message=Self.safeMessage(error);changed?()}
        }
    }
    func beginInstall(_ installer:(PreparedSignedUpdate)async throws->Void) async throws {
        guard phase == .prepared,let prepared,prepared.release==release,prepared.release.expires>Date() else{throw SignedUpdateError.rejected("The verified update is no longer ready. Check again.")}
        phase = .installing;message="Verifying the native installer handoff…";changed?()
        do{try await installer(prepared);message="Waiting for ATLAS to quit before replacement.";changed?()}
        catch{phase = .prepared;message=Self.safeMessage(error);changed?();throw error}
    }
    static func safeMessage(_ error:Error)->String {
        if error is CancellationError{return "Cancelled. The installed app was not replaced."}
        // No transport URL, filesystem path, headers or signed asset query is
        // displayed or logged. Validation errors use fixed local messages.
        if let error=error as? SignedUpdateError{return error.localizedDescription}
        return "Update failed safely. Check the connection and available space, then retry. The installed app was not replaced."
    }
}
