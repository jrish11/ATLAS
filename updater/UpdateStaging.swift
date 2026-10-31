import Foundation
import Security
import CryptoKit
import Darwin

enum UpdateProcess {
    static func run(_ executable:URL, _ arguments:[String], timeout:TimeInterval=60, cancelled:()->Bool = {false}) throws -> Data {
        let p=Process(), out=Pipe(), err=Pipe(), done=DispatchSemaphore(value:0), reads=DispatchGroup(), lock=NSLock()
        var data=Data(), tooLarge=false
        p.executableURL=executable;p.arguments=arguments;p.standardOutput=out;p.standardError=err;p.standardInput=FileHandle.nullDevice
        p.environment=["PATH":"/usr/bin:/bin:/usr/sbin:/sbin","PYTHONDONTWRITEBYTECODE":"1"]
        p.terminationHandler={_ in done.signal()}; try p.run()
        for pipe in [out,err] {
            reads.enter();DispatchQueue.global().async {
                defer {reads.leave()}
                while true {
                    let part=pipe.fileHandleForReading.availableData
                    if part.isEmpty {break}
                    lock.lock();if data.count+part.count <= 32_768 {data.append(part)} else {tooLarge=true};lock.unlock()
                }
            }
        }
        let deadline=ProcessInfo.processInfo.systemUptime+timeout
        while done.wait(timeout:.now()+0.05) == .timedOut {
            if cancelled() || ProcessInfo.processInfo.systemUptime>=deadline {
                p.terminate();if done.wait(timeout:.now()+2) == .timedOut {kill(p.processIdentifier,SIGKILL);_ = done.wait(timeout:.now()+2)}
                throw cancelled() ? CancellationError() : SignedUpdateError.rejected("Update helper timed out.")
            }
        }
        guard reads.wait(timeout:.now()+2) == .success else {throw SignedUpdateError.rejected("Update helper output did not close.")}
        guard !tooLarge, p.terminationStatus==0 else {throw SignedUpdateError.rejected("Update validation helper failed.")}
        return data
    }
}

enum UpdateBundleValidation {
    static func verify(_ app:URL, release:AuthenticatedUpdate? = nil) throws -> UpdateBundleIdentity {
        let identity=try UpdateFileTree.identity(app:app)
        guard identity.bundleIdentifier==UpdateLimits.bundleID else {throw SignedUpdateError.rejected("App identity changed.")}
        var code:SecStaticCode?
        guard SecStaticCodeCreateWithPath(app as CFURL,SecCSFlags(),&code)==errSecSuccess, let code,
              SecStaticCodeCheckValidity(code,SecCSFlags(rawValue:kSecCSStrictValidate | kSecCSCheckAllArchitectures | kSecCSCheckNestedCode),nil)==errSecSuccess else {
            throw SignedUpdateError.rejected("App code signature is invalid.")
        }
        if let release {
            guard identity.build==release.build, identity.epoch==release.epoch else {throw SignedUpdateError.rejected("App release order differs from its signed manifest.")}
            let os=ProcessInfo.processInfo.operatingSystemVersion
            let currentOS=[os.majorVersion,os.minorVersion,os.patchVersion]
            for name in ["Atticus","PersonalKeychain","ATLASUpdateInstaller"] {
                let executable=app.appendingPathComponent("Contents/MacOS/"+name)
                let bytes=try Data(contentsOf:executable,options:.mappedIfSafe)
                guard try architectures(bytes).contains(release.architecture) else {throw SignedUpdateError.rejected("App architecture is incompatible.")}
                let required=try minimumOS(bytes,architecture:release.architecture)
                guard !currentOS.lexicographicallyPrecedes(required),try !UpdateManifestVerifier.components(release.minimumMacOS,prefix:false).lexicographicallyPrecedes(required) else {throw SignedUpdateError.rejected("An executable needs a newer macOS version than the signed release declares.")}
            }
            let info=try PropertyListSerialization.propertyList(from:Data(contentsOf:app.appendingPathComponent("Contents/Info.plist")),format:nil) as? [String:Any]
            if let minimum=info?["LSMinimumSystemVersion"] as? String {
                let os=ProcessInfo.processInfo.operatingSystemVersion
                guard try !UpdateManifestVerifier.components("\(os.majorVersion).\(os.minorVersion).\(os.patchVersion)",prefix:false).lexicographicallyPrecedes(UpdateManifestVerifier.components(minimum,prefix:false)) else {throw SignedUpdateError.rejected("The app needs a newer macOS version.")}
            }
        }
        return identity
    }
    static func minimumOS(_ data:Data,architecture:String) throws -> [Int] {
        let b=[UInt8](data)
        func word(_ p:Int,_ little:Bool=true)throws->UInt32 {
            guard p>=0,p<=b.count-4 else{throw SignedUpdateError.rejected("Truncated executable metadata.")}
            return little ? UInt32(b[p])|UInt32(b[p+1])<<8|UInt32(b[p+2])<<16|UInt32(b[p+3])<<24 : UInt32(b[p+3])|UInt32(b[p+2])<<8|UInt32(b[p+1])<<16|UInt32(b[p])<<24
        }
        var offset=0,limit=b.count
        if try word(0,false)==0xcafebabe {
            let count=Int(try word(4,false));guard count>0,count<=8 else{throw SignedUpdateError.rejected("Invalid universal executable.")}
            var found=false
            for i in 0..<count {let p=8+i*20;let cpu=try word(p,false);let name=cpu==0x0100000c ? "arm64" : "x86_64"
                if name==architecture {offset=Int(try word(p+8,false));let size=Int(try word(p+12,false));guard offset>=8+count*20,size>=32,offset<=b.count-size else{throw SignedUpdateError.rejected("Invalid executable slice.")};limit=offset+size;found=true;break}}
            guard found else{throw SignedUpdateError.rejected("Missing executable architecture.")}
        }
        guard try word(offset)==0xfeedfacf,try word(offset+4)==(architecture=="arm64" ? 0x0100000c : 0x01000007) else{throw SignedUpdateError.rejected("Unsupported executable header.")}
        let count=Int(try word(offset+16)),size=Int(try word(offset+20));guard count>0,count<4096,size>=8,size<=limit-offset-32 else{throw SignedUpdateError.rejected("Invalid executable commands.")}
        var p=offset+32,minimum:[Int]?
        for _ in 0..<count {
            let cmd=try word(p),n=Int(try word(p+4));guard n>=8,p<=offset+32+size-n else{throw SignedUpdateError.rejected("Invalid executable command length.")}
            if cmd==0x32 {guard minimum==nil,n>=24,try word(p+8)==1 else{throw SignedUpdateError.rejected("Executable platform is not macOS.")};let v=try word(p+12);minimum=[Int(v>>16),Int((v>>8)&255),Int(v&255)]}
            if cmd==0x24 {guard minimum==nil,n>=16 else{throw SignedUpdateError.rejected("Invalid macOS version command.")};let v=try word(p+8);minimum=[Int(v>>16),Int((v>>8)&255),Int(v&255)]}
            p+=n
        }
        guard p==offset+32+size,let minimum else{throw SignedUpdateError.rejected("Executable has no unambiguous macOS deployment target.")};return minimum
    }
    static func architectures(_ bytes:Data) throws -> Set<String> {
        func word(_ p:Int,_ little:Bool)->UInt32? {
            guard p>=0,p+4<=bytes.count else{return nil};let b=[UInt8](bytes[p..<p+4])
            return little ? UInt32(b[0])|UInt32(b[1])<<8|UInt32(b[2])<<16|UInt32(b[3])<<24 : UInt32(b[3])|UInt32(b[2])<<8|UInt32(b[1])<<16|UInt32(b[0])<<24
        }
        func name(_ type:UInt32?)->String? {type==0x0100000c ? "arm64" : type==0x01000007 ? "x86_64" : nil}
        if word(0,true)==0xfeedfacf, let n=name(word(4,true)) {return [n]}
        if word(0,false)==0xcafebabe, let count=word(4,false), count>0,count<=8 {
            var result=Set<String>();for n in 0..<Int(count) {guard let a=name(word(8+n*20,false)) else{throw SignedUpdateError.rejected("Unsupported universal slice.")};result.insert(a)};return result
        }
        throw SignedUpdateError.rejected("App executable is not a supported Mach-O binary.")
    }
}

// Descriptor-relative cleanup never follows archive or replacement symlinks.
// A swapped nonempty root is preserved rather than recursively removed by path.
enum UpdateOwnedStaging {
    static func remove(_ root:URL,device:dev_t,inode:ino_t)throws {
        let parent=open(root.deletingLastPathComponent().path,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC)
        guard parent>=0 else{throw SignedUpdateError.rejected("Cannot open staging parent safely.")};defer{close(parent)}
        let fd=openat(parent,root.lastPathComponent,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC)
        guard fd>=0 else{throw SignedUpdateError.rejected("Cannot open staging directory safely.")};defer{close(fd)}
        var node=stat();guard fstat(fd,&node)==0,node.st_dev==device,node.st_ino==inode,node.st_uid==geteuid() else{throw SignedUpdateError.rejected("Staging cleanup identity changed.")}
        try empty(fd)
        var current=stat();guard fstatat(parent,root.lastPathComponent,&current,AT_SYMLINK_NOFOLLOW)==0,current.st_dev==device,current.st_ino==inode else{throw SignedUpdateError.rejected("Staging root changed during cleanup.")}
        guard unlinkat(parent,root.lastPathComponent,AT_REMOVEDIR)==0 else{throw SignedUpdateError.rejected("Cannot remove staging root safely.")}
    }
    private static func empty(_ fd:Int32)throws {
        let duplicate=dup(fd);guard duplicate>=0,let directory=fdopendir(duplicate) else{if duplicate>=0{close(duplicate)};throw SignedUpdateError.rejected("Cannot enumerate staging directory.")};defer{closedir(directory)}
        while let entry=readdir(directory) {
            let name=withUnsafePointer(to:&entry.pointee.d_name){$0.withMemoryRebound(to:CChar.self,capacity:Int(entry.pointee.d_namlen)+1){String(cString:$0)}}
            if name=="." || name==".."{continue}
            var before=stat();guard fstatat(fd,name,&before,AT_SYMLINK_NOFOLLOW)==0 else{throw SignedUpdateError.rejected("Staging changed during cleanup.")}
            if before.st_mode&S_IFMT==S_IFDIR {
                let child=openat(fd,name,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);guard child>=0 else{throw SignedUpdateError.rejected("Cannot open staged child safely.")}
                defer{close(child)};var current=stat();guard fstat(child,&current)==0,current.st_dev==before.st_dev,current.st_ino==before.st_ino else{throw SignedUpdateError.rejected("Staged child identity changed.")}
                try empty(child)
                guard fstatat(fd,name,&current,AT_SYMLINK_NOFOLLOW)==0,current.st_dev==before.st_dev,current.st_ino==before.st_ino,unlinkat(fd,name,AT_REMOVEDIR)==0 else{throw SignedUpdateError.rejected("Cannot remove changed staged directory.")}
            } else {
                // unlinkat removes only this directory entry, never its target.
                guard unlinkat(fd,name,0)==0 else{throw SignedUpdateError.rejected("Cannot remove staged file.")}
            }
        }
    }
}

final class PreparedSignedUpdate {
    let release:AuthenticatedUpdate, app:URL, identity:UpdateBundleIdentity, archive:URL
    private(set) var ownedContainer:URL?
    private let containerDevice:dev_t, containerInode:ino_t
    init(release:AuthenticatedUpdate,app:URL,identity:UpdateBundleIdentity,archive:URL,ownedContainer:URL) {
        self.release=release;self.app=app;self.identity=identity;self.archive=archive;self.ownedContainer=ownedContainer
        var node=stat();let valid=lstat(ownedContainer.path,&node)==0
        containerDevice=valid ? node.st_dev : 0;containerInode=valid ? node.st_ino : 0
    }
    func relinquish() {ownedContainer=nil}
    func discard() throws {
        guard let ownedContainer else{return}
        // The only removed path is the private directory created by the stager.
        var node=stat()
        guard lstat(ownedContainer.path,&node)==0,node.st_dev==containerDevice,node.st_ino==containerInode,node.st_uid==geteuid(),node.st_mode&S_IFMT==S_IFDIR else {throw SignedUpdateError.rejected("Staging cleanup identity changed.")}
        guard ownedContainer.lastPathComponent.hasPrefix(".atlas-download-"),
              (try? ownedContainer.resourceValues(forKeys:[.isSymbolicLinkKey]).isSymbolicLink)==false else {throw SignedUpdateError.rejected("Staging cleanup identity changed.")}
        try UpdateOwnedStaging.remove(ownedContainer,device:containerDevice,inode:containerInode);self.ownedContainer=nil
    }
}

enum UpdateArchiveStager {
    static func stage(bytes:Data, release:AuthenticatedUpdate, installationParent:URL, extractor:URL, cancelled:()->Bool) throws -> PreparedSignedUpdate {
        guard !cancelled(), bytes.count==release.size, SHA256.hash(data:bytes).map({String(format:"%02x",$0)}).joined()==release.sha256 else {throw SignedUpdateError.rejected("Downloaded archive differs from the signed release.")}
        let fm=FileManager.default
        let work=installationParent.appendingPathComponent(".atlas-download-"+UUID().uuidString,isDirectory:true)
        try fm.createDirectory(at:work,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700])
        var created=stat();guard lstat(work.path,&created)==0 else {throw SignedUpdateError.rejected("Cannot pin staging directory.")}
        do {
            let archive=work.appendingPathComponent("release.zip"), metadata=work.appendingPathComponent("release.json")
            try bytes.write(to:archive,options:.withoutOverwriting)
            let values:[String:Any]=["version":release.version,"sequence":release.sequence,"update_epoch":release.epoch,"build":release.build,
                "channel":release.channel,"url":release.url.absoluteString,"sha256":release.sha256,"size":release.size,"minimum_macos":release.minimumMacOS,
                "architecture":release.architecture,"changelog":release.changelog,"manifest_sha256":release.manifestHash]
            try JSONSerialization.data(withJSONObject:values,options:.sortedKeys).write(to:metadata,options:.withoutOverwriting)
            let extracted=work.appendingPathComponent("extracted",isDirectory:true)
            _ = try UpdateProcess.run(URL(fileURLWithPath:"/usr/bin/python3"),["-I","-B",extractor.path,archive.path,metadata.path,extracted.path],timeout:120,cancelled:cancelled)
            if cancelled(){throw CancellationError()}
            let app=extracted.appendingPathComponent("ATLAS.app",isDirectory:true)
            let identity=try UpdateBundleValidation.verify(app,release:release)
            return PreparedSignedUpdate(release:release,app:app,identity:identity,archive:archive,ownedContainer:work)
        } catch {var current=stat();if lstat(work.path,&current)==0,current.st_dev==created.st_dev,current.st_ino==created.st_ino,current.st_mode&S_IFMT==S_IFDIR {try? UpdateOwnedStaging.remove(work,device:created.st_dev,inode:created.st_ino)};throw error}
    }
}
