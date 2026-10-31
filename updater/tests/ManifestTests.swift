import Foundation
import CryptoKit

struct ManifestTestFailure: Error { let message: String }
@main struct ManifestTests {
    static var checks=0
    static func check(_ condition: @autoclosure () throws -> Bool,_ message:String) throws {
        guard try condition() else { throw ManifestTestFailure(message:message) }; checks += 1
    }
    static func reject(_ name:String,_ body:() throws -> Void) throws {
        do { try body() } catch { checks += 1; return }; throw ManifestTestFailure(message:"Accepted " + name)
    }
    static let now=Date(timeIntervalSince1970:1_793_448_000) // fixed synthetic clock; no host-clock dependence
    static let installed=UpdateInstalledVersion(version:"v3.6",build:36,epoch:1)
    static let receipt=UpdateReplayReceipt(highestSequence:6,lastTrustedTime:now)
    static func manifest() -> [String:Any] {
        let formatter=ISO8601DateFormatter()
        return ["schema":2,"product":"ATLAS","repository":"jrish11/ATLAS","version":"v3.7","sequence":7,"channel":"stable","update_epoch":1,"build":37,"published_at":formatter.string(from:now.addingTimeInterval(-3600)),"expires_at":formatter.string(from:now.addingTimeInterval(86400)),"minimum_macos":"26.0","architecture":"arm64","bundle_id":"com.atticus.personal.dev","archive":["url":"https://github.com/jrish11/ATLAS/releases/download/v3.7/ATLAS-v3.7-macOS-arm64-PUBLIC.zip","sha256":String(repeating:"a",count:64),"size":1024],"changelog":"Synthetic fixture only.\nNo owner data."]
    }
    static func encode(_ obj:[String:Any]) throws -> Data { try JSONSerialization.data(withJSONObject:obj,options:[.sortedKeys,.withoutEscapingSlashes]) }
    static func envelope(_ raw:Data,_ key:Curve25519.Signing.PrivateKey,keyID:String="fixture-key") throws -> Data {
        try encode(["key_id":keyID,"algorithm":"Ed25519","signature":key.signature(for:raw).base64EncodedString()])
    }
    #if UPDATER_TESTING
    static func verify(_ raw:Data,_ signature:Data,_ key:Curve25519.Signing.PrivateKey,installed:UpdateInstalledVersion=installed,receipt:UpdateReplayReceipt=receipt,machine:String="arm64",os:String="26.0",prereleases:Bool=false,at:Date=now) throws -> AuthenticatedUpdate {
        try UpdateManifestVerifier.fixtureVerify(raw:raw,signature:signature,keys:["fixture-key":key.publicKey.rawRepresentation],installed:installed,receipt:receipt,machine:machine,macOS:os,includePrereleases:prereleases,now:at)
    }
    static func signedReject(_ name:String,_ key:Curve25519.Signing.PrivateKey,_ change:(inout [String:Any])->Void) throws {
        var obj=manifest();change(&obj);let raw=try encode(obj), sig=try envelope(raw,key)
        try reject(name) { _=try verify(raw,sig,key) }
    }
    #endif
    static func main() async throws {
        let key=Curve25519.Signing.PrivateKey(), raw=try encode(manifest()), signature=try envelope(raw,key)
        try check(!UpdatePublisherTrust.configured && UpdatePublisherTrust.keys.isEmpty,"Production roots deliberately empty")
        try reject("Production acceptance with ephemeral signing key") {
            _=try UpdateManifestVerifier.verify(raw:raw,signature:signature,installed:installed,receipt:receipt,machine:"arm64",macOS:"26.0",includePrereleases:false,now:now)
        }
        #if UPDATER_TESTING
        for invalid in ["2026-02-30T12:00:00Z","2026-11-31T12:00:00Z","2026-10-31T24:00:00Z"] {
            try reject("Impossible calendar timestamp") { _=try UpdateManifestVerifier.date(invalid) }
        }
        do {
            _=try verify(raw,signature,key,installed:.init(version:"v3.7",build:37,epoch:1),receipt:.init(highestSequence:7,lastTrustedTime:now))
            preconditionFailure("Current release became installable")
        }catch SignedUpdateError.current {try check(true,"Authenticated current feed is not installable")}
        let accepted=try verify(raw,signature,key)
        try check(accepted.build==37 && accepted.sequence==7 && accepted.architecture=="arm64","Signed fixture accepted")
        try check(accepted.rawManifest==raw && accepted.rawSignature==signature,"Exact signed bytes retained")
        try check(accepted.manifestHash==SHA256.hash(data:raw).map {String(format:"%02x",$0)}.joined(),"Exact-byte manifest digest")
        for index in [0,raw.count/2,raw.count-1] {
            var altered=raw;altered[index] ^= 1
            try reject("One-byte tamper") { _=try verify(altered,signature,key) }
        }
        var appended=raw;appended.append(32)
        try reject("Whitespace tamper with original signature") { _=try verify(appended,signature,key) }
        let whitespaceSignature=try envelope(appended,key)
        try check(try verify(appended,whitespaceSignature,key).rawManifest==appended,"Exact whitespace accepted only when signed")
        let other=Curve25519.Signing.PrivateKey()
        try reject("Different publisher key") { _=try verify(raw,try envelope(raw,other),key) }
        try reject("Unknown key identifier") { _=try verify(raw,try envelope(raw,key,keyID:"unknown"),key) }
        for (name,field,value) in [("Schema","schema",3 as Any),("Product","product","Other"),("Repository","repository","other/ATLAS"),("Bundle identifier","bundle_id","other.app"),("Unknown channel","channel","nightly"),("Minimum macOS","minimum_macos","27.0"),("Architecture","architecture","x86_64"),("Unknown field","unexpected","value"),("Changelog controls","changelog","bad\u{0001}text"),("Changelog length","changelog",String(repeating:"x",count:32001)),("Invalid version","version","v03.7"),("Overflow version","version","v9999999999999999999999999999999999.7"),("Boolean sequence","sequence",true),("Fraction sequence","sequence",7.5),("Negative sequence","sequence",-1),("Unsafe integer","sequence",9_007_199_254_740_992 as Int),("Replayed sequence","sequence",6),("Same build","build",36),("Older build","build",35),("Older epoch","update_epoch",0),("Boolean build","build",true)] {
            try signedReject(name,key) { $0[field]=value }
        }
        for size in [0,UpdateLimits.archive+1,-1] {
            try signedReject("Archive size \(size)",key) { var a=$0["archive"] as! [String:Any];a["size"]=size;$0["archive"]=a }
        }
        for sha in ["ABC",String(repeating:"A",count:64),String(repeating:"g",count:64)] {
            try signedReject("Archive digest",key) { var a=$0["archive"] as! [String:Any];a["sha256"]=sha;$0["archive"]=a }
        }
        for url in ["http://github.com/jrish11/ATLAS/releases/download/v3.7/ATLAS-v3.7-macOS-arm64-PUBLIC.zip","https://github.com/other/ATLAS/releases/download/v3.7/file.zip","https://github.com/jrish11/ATLAS/releases/download/v3.7/ATLAS-v3.7-macOS-arm64-PUBLIC.zip?extra=1","https://github.com/jrish11/ATLAS/releases/download/v3.7/ATLAS-v3.7-macOS-arm64-PUBLIC.zip#fragment","https://user:pass@github.com/jrish11/ATLAS/releases/download/v3.7/ATLAS-v3.7-macOS-arm64-PUBLIC.zip"] {
            try signedReject("Archive origin",key) { var a=$0["archive"] as! [String:Any];a["url"]=url;$0["archive"]=a }
        }
        let iso=ISO8601DateFormatter()
        try signedReject("Expired release",key) { $0["expires_at"]=iso.string(from:now) }
        try signedReject("Future publication",key) { $0["published_at"]=iso.string(from:now.addingTimeInterval(301)) }
        try signedReject("Overlong validity",key) { $0["expires_at"]=iso.string(from:now.addingTimeInterval(91*86400)) }
        try signedReject("Malformed time",key) { $0["expires_at"]="not-a-date" }
        try reject("Trusted clock rollback beyond grace") { _=try verify(raw,signature,key,at:now.addingTimeInterval(-301)) }
        try check(try verify(raw,signature,key,at:now.addingTimeInterval(-300)).sequence==7,"Documented five-minute clock grace boundary")
        try reject("Unknown machine architecture") { _=try verify(raw,signature,key,machine:"universal") }
        try reject("Old operating system") { _=try verify(raw,signature,key,os:"25.9") }
        var prerelease=manifest();prerelease["channel"]="prerelease";let pre=try encode(prerelease), preSig=try envelope(pre,key)
        try reject("Prerelease without opt-in") { _=try verify(pre,preSig,key) }
        try check(try verify(pre,preSig,key,prereleases:true).channel=="prerelease","Explicit prerelease opt-in")
        try reject("Version rollback in current epoch") { _=try verify(raw,signature,key,installed:UpdateInstalledVersion(version:"v4.0",build:36,epoch:1)) }
        var epoch=manifest();epoch["update_epoch"]=2;let epochRaw=try encode(epoch), epochSig=try envelope(epochRaw,key)
        try check(try verify(epochRaw,epochSig,key,installed:UpdateInstalledVersion(version:"v4.0",build:36,epoch:1)).epoch==2,"Explicit higher epoch permits version migration")
        let text=String(decoding:raw,as:UTF8.self)
        for duplicate in ["\"build\":37,\"build\":37","\"build\":37,\"b\\u0075ild\":37"] {
            let bytes=Data(text.replacingOccurrences(of:"\"build\":37",with:duplicate).utf8)
            try reject("Duplicate/escaped-equivalent manifest JSON key") { _=try verify(bytes,try envelope(bytes,key),key) }
        }
        let archiveDuplicate=Data(text.replacingOccurrences(of:"\"size\":1024",with:"\"size\":1024,\"size\":1024").utf8)
        try reject("Nested duplicate archive key") { _=try verify(archiveDuplicate,try envelope(archiveDuplicate,key),key) }
        let signatureText=String(decoding:signature,as:UTF8.self)
        let duplicateEnvelope=Data(signatureText.replacingOccurrences(of:"\"algorithm\":\"Ed25519\"",with:"\"algorithm\":\"Ed25519\",\"algorithm\":\"Ed25519\"").utf8)
        try reject("Duplicate signature envelope key") { _=try verify(raw,duplicateEnvelope,key) }
        for bytes in [Data(),Data("{".utf8),Data((text+" {}").utf8),Data(repeating:32,count:UpdateLimits.manifest+1)] {
            try reject("Malformed/oversized manifest") { _=try verify(bytes,try envelope(bytes,key),key) }
        }
        for sig in [Data(),Data("{}".utf8),Data(repeating:32,count:UpdateLimits.signature+1)] {
            try reject("Malformed/oversized signature") { _=try verify(raw,sig,key) }
        }
        #endif
        let allowed=URL(string:"https://github.com/jrish11/ATLAS/releases/download/v3.7/file.zip")!
        try check(UpdateDownloadOrigins.permits(allowed,redirected:false),"Initial release origin accepted")
        for url in ["http://github.com/jrish11/ATLAS/releases/download/v3.7/file.zip","https://github.com/other/ATLAS/releases/download/v3.7/file.zip","https://github.com/jrish11/ATLAS/releases/download/v3.7/file.zip?x=1","https://user:pass@github.com/jrish11/ATLAS/releases/download/v3.7/file.zip","https://github.com:444/jrish11/ATLAS/releases/download/v3.7/file.zip","https://evil.example/github-production-release-asset/x"] {
            try check(!UpdateDownloadOrigins.permits(URL(string:url)!,redirected:false),"Unapproved transport origin refused")
        }
        let asset=URL(string:"https://release-assets.githubusercontent.com/github-production-release-asset/test?token=synthetic")!
        try check(!UpdateDownloadOrigins.permits(asset,redirected:false) && UpdateDownloadOrigins.permits(asset,redirected:true),"Release asset accepted only as redirect")
        let downloader=BoundedUpdateDownloader()
        do { _=try await downloader.fetch(URL(string:"http://invalid.example/file")!,maximum:1024,expectedSize:nil);throw ManifestTestFailure(message:"Invalid URL dispatched") } catch is ManifestTestFailure { throw ManifestTestFailure(message:"Invalid URL dispatched") } catch { checks += 1 }
        for maximum in [0,-1] {
            do { _=try await downloader.fetch(allowed,maximum:maximum,expectedSize:nil);throw ManifestTestFailure(message:"Invalid limit dispatched") } catch is ManifestTestFailure { throw ManifestTestFailure(message:"Invalid limit dispatched") } catch { checks += 1 }
        }
        // Cancellation is set synchronously within this task before fetch can
        // create a URLSession. No valid request reaches transport in this suite.
        let cancelled=Task {
            withUnsafeCurrentTask { $0?.cancel() }
            do { _=try await downloader.fetch(allowed,maximum:1024,expectedSize:1024);return false }
            catch is CancellationError { return true } catch { return false }
        }
        let cancellationPassed=await cancelled.value
        try check(cancellationPassed,"Already-cancelled fetch exits without transport")
        #if UPDATER_TESTING
        print("Manifest/transport-boundary fixtures passed: \(checks) assertions, real ephemeral Ed25519; no persistent key or network. Stream/redirect callback transport remains unexercised.")
        #else
        print("Production empty-root and transport-boundary fixtures passed: \(checks) assertions; no acceptance or network.")
        #endif
    }
}
