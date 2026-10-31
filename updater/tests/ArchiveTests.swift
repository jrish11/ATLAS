import Foundation
import CryptoKit
@main struct Tests {
 static func main()throws {
    let archive=URL(fileURLWithPath:CommandLine.arguments[1]),parent=URL(fileURLWithPath:CommandLine.arguments[2]),extractor=URL(fileURLWithPath:CommandLine.arguments[3])
    let bytes=try Data(contentsOf:archive),key=Curve25519.Signing.PrivateKey(),now=Date(),fmt=ISO8601DateFormatter()
    #if arch(arm64)
    let machine="arm64"
    #else
    let machine="x86_64"
    #endif
    let manifest:[String:Any] = ["schema":2,"product":"ATLAS","repository":UpdateLimits.repository,"version":"v1.2.0","sequence":2,"channel":"stable","update_epoch":1,"build":4,"published_at":fmt.string(from:now.addingTimeInterval(-60)),"expires_at":fmt.string(from:now.addingTimeInterval(3600)),"minimum_macos":"26.0","architecture":machine,"bundle_id":UpdateLimits.bundleID,"archive":["url":"https://github.com/jrish11/ATLAS/releases/download/v1.2.0/ATLAS-v1.2.0-macOS-\(machine)-PUBLIC.zip","sha256":SHA256.hash(data:bytes).map{String(format:"%02x",$0)}.joined(),"size":bytes.count],"changelog":"Fixture only"]
    let raw=try JSONSerialization.data(withJSONObject:manifest,options:.sortedKeys)
    let sig=try JSONSerialization.data(withJSONObject:["key_id":"fixture","algorithm":"Ed25519","signature":key.signature(for:raw).base64EncodedString()])
    let release=try UpdateManifestVerifier.fixtureVerify(raw:raw,signature:sig,keys:["fixture":key.publicKey.rawRepresentation],installed:.init(version:"v1.1.0",build:3,epoch:1),receipt:.init(highestSequence:0,lastTrustedTime:now),machine:machine,macOS:"26.0",includePrereleases:false,now:now)
    let stage=try UpdateArchiveStager.stage(bytes:bytes,release:release,installationParent:parent,extractor:extractor,cancelled:{false})
    precondition(stage.identity.build==4);precondition(FileManager.default.isExecutableFile(atPath:stage.app.appendingPathComponent("Contents/MacOS/ATLASUpdateInstaller").path))
    try stage.discard();precondition(stage.ownedContainer==nil)
    do{_=try UpdateArchiveStager.stage(bytes:bytes+Data([0]),release:release,installationParent:parent,extractor:extractor,cancelled:{false});preconditionFailure()}catch{}
    do{_=try UpdateArchiveStager.stage(bytes:bytes,release:release,installationParent:parent,extractor:extractor,cancelled:{true});preconditionFailure()}catch{}
    print("archive: 6 assertions passed, real ephemeral signature + ZIP + ad-hoc fake bundle; no installed app")
 }
}
