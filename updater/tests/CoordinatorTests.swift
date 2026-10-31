import Foundation
import Darwin
final class NeverDownload:UpdateDownloading {
    var calls=0
    func fetch(_ url:URL,maximum:Int,expectedSize:Int?) async throws->Data {calls+=1;throw SignedUpdateError.rejected("must not run")}
}
@main struct Tests {
    @MainActor static func main() async throws {
        var assertions=0
        func check(_ b:Bool){precondition(b);assertions+=1}
        let d=NeverDownload(),model=SignedUpdateCoordinator(downloader:d)
        model.check(includePrereleases:true,installed:.init(version:"v1.1",build:3,epoch:1),machine:"arm64",macOS:"26.0",receipt:.init(highestSequence:0,lastTrustedTime:Date()))
        check(model.phase == .blocked);check(d.calls==0);check(!model.busy);check(model.release==nil)
        model.download(installationParent:URL(fileURLWithPath:"/must-not-exist"),extractor:URL(fileURLWithPath:"/must-not-run"));check(d.calls==0)
        var installs=0
        do{try await model.beginInstall{_ in installs+=1};preconditionFailure()}catch{assertions+=1};check(installs==0)
        model.cancel();check(model.phase == .cancelled)
        check(!SignedUpdateCoordinator.safeMessage(NSError(domain:"https://private.example/token=SECRET",code:9)).contains("SECRET"))
        let resolved=realpath(FileManager.default.temporaryDirectory.path,nil)!;let canonical=String(cString:resolved);free(resolved)
        let root=URL(fileURLWithPath:canonical).appendingPathComponent("atlas-receipt-test-"+UUID().uuidString)
        try FileManager.default.createDirectory(at:root,withIntermediateDirectories:false,attributes:[.posixPermissions:0o700]);defer{try? FileManager.default.removeItem(at:root)}
        let dir=root.appendingPathComponent("state"),store=try UpdateReceiptStore(directory:dir)
        check(try store.read().highestSequence==0)
        let now=Date();try store.save(sequence:5,now:now);check(try store.read().highestSequence==5)
        do{try store.save(sequence:4,now:now);preconditionFailure()}catch{assertions+=1}
        do{try store.save(sequence:6,now:now.addingTimeInterval(-600));preconditionFailure()}catch{assertions+=1}
        let successful=NSLock();var sequences=[Int]()
        DispatchQueue.concurrentPerform(iterations:40){i in
            if (try? store.save(sequence:10+i,now:now)) != nil {successful.lock();sequences.append(10+i);successful.unlock()}
        }
        check(!sequences.isEmpty);check(try store.read().highestSequence==sequences.max()!)
        let receipt=dir.appendingPathComponent("trusted-release.json")
        try FileManager.default.removeItem(at:receipt);try FileManager.default.createSymbolicLink(at:receipt,withDestinationURL:root.appendingPathComponent("outside"))
        do{_=try store.read();preconditionFailure()}catch{assertions+=1}
        try FileManager.default.removeItem(at:receipt)
        try Data("{malformed".utf8).write(to:receipt);chmod(receipt.path,0o600)
        do{_=try store.read();preconditionFailure()}catch{assertions+=1}
        let link=root.appendingPathComponent("link");try FileManager.default.createSymbolicLink(at:link,withDestinationURL:dir)
        do{_=try UpdateReceiptStore(directory:link);preconditionFailure()}catch{assertions+=1}
        print("coordinator: \(assertions) assertions passed; no network or installation")
    }
}
