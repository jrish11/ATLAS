import Foundation
import Darwin
@main struct Tests {
    static func main()throws {
        var count=0
        func check(_ b:Bool){precondition(b);count+=1}
        func reject(_ run:()throws->Void){do{try run();preconditionFailure("expected rejection")}catch{count+=1}}
        let data=try Data(contentsOf:URL(fileURLWithPath:CommandLine.arguments[0]))
        #if arch(arm64)
        let arch="arm64"
        #else
        let arch="x86_64"
        #endif
        check(try UpdateBundleValidation.architectures(data).contains(arch))
        let minimum=try UpdateBundleValidation.minimumOS(data,architecture:arch)
        check(minimum.count==3);check(minimum[0]>=10)
        reject{_=try UpdateBundleValidation.minimumOS(Data(),architecture:arch)}
        reject{_=try UpdateBundleValidation.minimumOS(Data(data.prefix(32)),architecture:arch)}
        reject{_=try UpdateBundleValidation.architectures(Data("not executable".utf8))}
        var broken=data;broken.replaceSubrange(16..<20,with:[255,255,255,255]);reject{_=try UpdateBundleValidation.minimumOS(broken,architecture:arch)}
        // A duplicate deployment command must not lower the effective target.
        func put(_ value:UInt32,_ at:Int,_ into:inout Data){for i in 0..<4{into[at+i]=UInt8((value>>UInt32(i*8))&255)}}
        var duplicate=Data(repeating:0,count:72);put(0xfeedfacf,0,&duplicate)
        put(arch=="arm64" ? 0x0100000c : 0x01000007,4,&duplicate);put(2,16,&duplicate);put(40,20,&duplicate)
        put(0x32,32,&duplicate);put(24,36,&duplicate);put(1,40,&duplicate);put(99<<16,44,&duplicate)
        put(0x24,56,&duplicate);put(16,60,&duplicate);put(10<<16,64,&duplicate)
        reject{_=try UpdateBundleValidation.minimumOS(duplicate,architecture:arch)}
        var cpuMismatch=data;put(0,4,&cpuMismatch);reject{_=try UpdateBundleValidation.minimumOS(cpuMismatch,architecture:arch)}
        // Cleanup follows owned descriptors, never a symlink into an outside directory.
        let fm=FileManager.default,root=fm.temporaryDirectory.appendingPathComponent("atlas-cleanup-"+UUID().uuidString).resolvingSymlinksInPath()
        try fm.createDirectory(at:root,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700]);defer{try? fm.removeItem(at:root)}
        let owned=root.appendingPathComponent("owned"),outside=root.appendingPathComponent("outside")
        try fm.createDirectory(at:owned,withIntermediateDirectories:false);try fm.createDirectory(at:outside,withIntermediateDirectories:false)
        let sentinel=outside.appendingPathComponent("keep");try Data("KEEP".utf8).write(to:sentinel)
        try fm.createSymbolicLink(at:owned.appendingPathComponent("link"),withDestinationURL:outside)
        var node=stat();precondition(lstat(owned.path,&node)==0)
        try UpdateOwnedStaging.remove(owned,device:node.st_dev,inode:node.st_ino)
        check(fm.fileExists(atPath:sentinel.path));check(!fm.fileExists(atPath:owned.path))
        reject{try UpdateOwnedStaging.remove(outside,device:node.st_dev,inode:node.st_ino)}
        check(fm.fileExists(atPath:sentinel.path))
        let result=try UpdateProcess.run(URL(fileURLWithPath:"/usr/bin/printf"),["fixture"])
        check(String(data:result,encoding:.utf8)=="fixture")
        reject{_=try UpdateProcess.run(URL(fileURLWithPath:"/usr/bin/false"),[])}
        reject{_=try UpdateProcess.run(URL(fileURLWithPath:"/bin/sleep"),["3"],timeout:0.05)}
        reject{_=try UpdateProcess.run(URL(fileURLWithPath:"/bin/sleep"),["3"],cancelled:{true})}
        print("staging/process: \(count) assertions passed; synthetic subprocesses only")
    }
}
