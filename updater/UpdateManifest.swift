import Foundation
import CryptoKit
import CoreFoundation

enum SignedUpdateError: Error, LocalizedError {
    case rejected(String)
    var errorDescription: String? { if case let .rejected(message) = self { return message }; return nil }
}

enum UpdateLimits {
    static let manifest = 262_144, signature = 2048, archive = 268_435_456
    static let bundleID = "com.atticus.personal.dev"
    static let repository = "jrish11/ATLAS"
}

// Production trust is compiled in and deliberately unconfigured. Neither
// settings, environment, a feed nor model content can supply a publisher key.
enum UpdatePublisherTrust {
    static let keys: [String: Data] = [:]
    static var configured: Bool { !keys.isEmpty }
}

struct UpdateInstalledVersion: Codable, Equatable {
    let version: String, build: Int, epoch: Int
}
struct UpdateReplayReceipt: Codable, Equatable {
    let highestSequence: Int, lastTrustedTime: Date
}
struct AuthenticatedUpdate: Equatable {
    let version: String, sequence: Int, epoch: Int, build: Int, channel: String
    let url: URL, sha256: String, size: Int, minimumMacOS: String, architecture: String
    let changelog: String, expires: Date, manifestHash: String
    // Retain the exact signed bytes for independent helper-side verification.
    let rawManifest: Data, rawSignature: Data

    fileprivate init(version: String, sequence: Int, epoch: Int, build: Int, channel: String, url: URL,
                     sha256: String, size: Int, minimumMacOS: String, architecture: String,
                     changelog: String, expires: Date, manifestHash: String, rawManifest: Data, rawSignature: Data) {
        self.version=version; self.sequence=sequence; self.epoch=epoch; self.build=build; self.channel=channel
        self.url=url; self.sha256=sha256; self.size=size; self.minimumMacOS=minimumMacOS; self.architecture=architecture
        self.changelog=changelog; self.expires=expires; self.manifestHash=manifestHash
        self.rawManifest=rawManifest; self.rawSignature=rawSignature
    }
}

// JSONSerialization accepts duplicate keys. This scanner rejects them before
// authority-bearing values are decoded, including escaped-equivalent names.
private struct UpdateJSONScanner {
    let bytes: [UInt8]
    var index = 0
    mutating func space() { while index < bytes.count && [9,10,13,32].contains(bytes[index]) { index += 1 } }
    mutating func string() throws -> String {
        guard index < bytes.count && bytes[index] == 34 else { throw SignedUpdateError.rejected("Malformed update JSON.") }
        let start=index; index += 1
        while index < bytes.count {
            let c=bytes[index]; index += 1
            if c == 34 {
                let raw=Data(bytes[start..<index])
                guard let s=try JSONSerialization.jsonObject(with: raw, options: [.fragmentsAllowed]) as? String else { throw SignedUpdateError.rejected("Invalid JSON string.") }
                return s
            }
            if c < 32 { throw SignedUpdateError.rejected("Invalid JSON control character.") }
            if c == 92 { guard index < bytes.count else { break }; index += 1 }
        }
        throw SignedUpdateError.rejected("Unterminated JSON string.")
    }
    mutating func value(_ depth: Int = 0) throws {
        guard depth < 32 else { throw SignedUpdateError.rejected("Update JSON is too deeply nested.") }
        space(); guard index < bytes.count else { throw SignedUpdateError.rejected("Incomplete update JSON.") }
        switch bytes[index] {
        case 123:
            index += 1; space(); var names=Set<String>()
            if index < bytes.count && bytes[index] == 125 { index += 1; return }
            while true {
                space(); let name=try string()
                guard names.insert(name).inserted else { throw SignedUpdateError.rejected("Duplicate update field.") }
                space(); guard index < bytes.count && bytes[index] == 58 else { throw SignedUpdateError.rejected("Malformed update object.") }; index += 1
                try value(depth+1); space(); guard index < bytes.count else { throw SignedUpdateError.rejected("Incomplete update object.") }
                let c=bytes[index]; index += 1
                if c == 125 { return }; guard c == 44 else { throw SignedUpdateError.rejected("Malformed update object.") }
            }
        case 91:
            index += 1; space(); if index < bytes.count && bytes[index] == 93 { index += 1; return }
            while true { try value(depth+1); space(); guard index < bytes.count else { throw SignedUpdateError.rejected("Incomplete update array.") }; let c=bytes[index]; index += 1; if c == 93 { return }; guard c == 44 else { throw SignedUpdateError.rejected("Malformed update array.") } }
        case 34: _ = try string()
        default:
            let start=index
            while index < bytes.count && ![9,10,13,32,44,93,125].contains(bytes[index]) { index += 1 }
            guard index > start else { throw SignedUpdateError.rejected("Malformed update value.") }
            _ = try JSONSerialization.jsonObject(with: Data(bytes[start..<index]), options: [.fragmentsAllowed])
        }
    }
}

enum UpdateManifestVerifier {
    static func object(_ data: Data, maximum: Int) throws -> [String: Any] {
        guard !data.isEmpty && data.count <= maximum else { throw SignedUpdateError.rejected("Update metadata exceeds its limit.") }
        var scanner=UpdateJSONScanner(bytes: Array(data)); try scanner.value(); scanner.space()
        guard scanner.index == scanner.bytes.count, let obj=try JSONSerialization.jsonObject(with: data) as? [String:Any] else { throw SignedUpdateError.rejected("Invalid update object.") }
        return obj
    }
    static func number(_ value: Any?) throws -> Int {
        guard let n=value as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID(), !["f","d"].contains(String(cString:n.objCType)), n.doubleValue.isFinite,
              n.doubleValue.rounded() == n.doubleValue, n.doubleValue >= 0, n.doubleValue <= 9_007_199_254_740_991 else { throw SignedUpdateError.rejected("Invalid update order.") }
        return n.intValue
    }
    static func components(_ text: String, prefix: Bool = true) throws -> [Int] {
        let pattern=prefix ? "^v(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(\\.(0|[1-9][0-9]*))?$" : "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)(\\.(0|[1-9][0-9]*))?$"
        guard text.count <= 40, text.range(of:pattern, options:.regularExpression) != nil else { throw SignedUpdateError.rejected("Invalid release version.") }
        var result=try (prefix ? String(text.dropFirst()) : text).split(separator:".").map { p -> Int in guard let n=Int(p) else {throw SignedUpdateError.rejected("Version overflow.")}; return n }
        while result.count < 3 {result.append(0)}; return result
    }
    static func date(_ value: Any?) throws -> Date {
        guard let s=value as? String, s.range(of:"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$",options:.regularExpression) != nil,
              let date=ISO8601DateFormatter().date(from:s) else {throw SignedUpdateError.rejected("Invalid release time.")}; guard ISO8601DateFormatter().string(from:date)==s else{throw SignedUpdateError.rejected("Invalid release calendar time.")}; return date
    }
    static func verify(raw: Data, signature: Data, installed: UpdateInstalledVersion, receipt: UpdateReplayReceipt,
                       machine: String, macOS: String, includePrereleases: Bool, now: Date = Date()) throws -> AuthenticatedUpdate {
        try verifyWithKeys(raw:raw, signature:signature, keys:UpdatePublisherTrust.keys, installed:installed,
                           receipt:receipt, machine:machine, macOS:macOS, includePrereleases:includePrereleases, now:now)
    }
    #if UPDATER_TESTING
    static func fixtureVerify(raw: Data, signature: Data, keys: [String:Data], installed: UpdateInstalledVersion,
                              receipt: UpdateReplayReceipt, machine: String, macOS: String, includePrereleases: Bool, now: Date) throws -> AuthenticatedUpdate {
        try verifyWithKeys(raw:raw, signature:signature, keys:keys, installed:installed, receipt:receipt,
                           machine:machine, macOS:macOS, includePrereleases:includePrereleases, now:now)
    }
    #endif
    private static func verifyWithKeys(raw: Data, signature: Data, keys: [String:Data], installed: UpdateInstalledVersion,
                                       receipt: UpdateReplayReceipt, machine: String, macOS: String, includePrereleases: Bool, now: Date) throws -> AuthenticatedUpdate {
        guard !raw.isEmpty && raw.count <= UpdateLimits.manifest else {throw SignedUpdateError.rejected("Invalid manifest size.")}
        let envelope=try object(signature, maximum:UpdateLimits.signature)
        guard Set(envelope.keys)==Set(["key_id","algorithm","signature"]), envelope["algorithm"] as? String == "Ed25519",
              let keyID=envelope["key_id"] as? String, keyID.range(of:"^[a-z0-9-]{1,64}$",options:.regularExpression) != nil,
              let encoded=envelope["signature"] as? String, let sig=Data(base64Encoded:encoded), sig.count==64,
              let key=keys[keyID], let publicKey=try? Curve25519.Signing.PublicKey(rawRepresentation:key), publicKey.isValidSignature(sig, for:raw)
        else {throw SignedUpdateError.rejected("Signed updates are not configured or the signature is untrusted.")}
        let obj=try object(raw, maximum:UpdateLimits.manifest)
        let expected=Set(["schema","product","repository","version","sequence","channel","update_epoch","build","published_at","expires_at","minimum_macos","architecture","bundle_id","archive","changelog"])
        guard Set(obj.keys)==expected, try number(obj["schema"])==2, obj["product"] as? String == "ATLAS",
              obj["repository"] as? String == UpdateLimits.repository, obj["bundle_id"] as? String == UpdateLimits.bundleID,
              let version=obj["version"] as? String, let minimum=obj["minimum_macos"] as? String,
              let architecture=obj["architecture"] as? String, architecture==machine, ["arm64","x86_64"].contains(machine),
              let channel=obj["channel"] as? String, channel=="stable" || (channel=="prerelease" && includePrereleases),
              let notes=obj["changelog"] as? String, !notes.isEmpty, notes.utf8.count <= 32_000,
              !notes.unicodeScalars.contains(where:{$0.value<32 && $0 != "\n" && $0 != "\t"}),
              let archive=obj["archive"] as? [String:Any], Set(archive.keys)==Set(["url","sha256","size"]),
              let urlText=archive["url"] as? String, let url=URL(string:urlText),
              let sha=archive["sha256"] as? String, sha.range(of:"^[a-f0-9]{64}$",options:.regularExpression) != nil
        else {throw SignedUpdateError.rejected("Unsupported release metadata.")}
        let seq=try number(obj["sequence"]), epoch=try number(obj["update_epoch"]), build=try number(obj["build"]), size=try number(archive["size"])
        guard seq>receipt.highestSequence, epoch>=installed.epoch, build>installed.build, size>0, size<=UpdateLimits.archive,
              now >= receipt.lastTrustedTime.addingTimeInterval(-300), try !components(minimum,prefix:false).lexicographicallyPrecedes(components("0.0",prefix:false))
        else {throw SignedUpdateError.rejected("Release order or trusted clock check failed.")}
        let newVersion=try components(version), oldVersion=try components(installed.version)
        guard epoch>installed.epoch || !newVersion.lexicographicallyPrecedes(oldVersion),
              try !components(macOS,prefix:false).lexicographicallyPrecedes(components(minimum,prefix:false)) else {throw SignedUpdateError.rejected("Release version or macOS is incompatible.")}
        let expectedURL="https://github.com/"+UpdateLimits.repository+"/releases/download/"+version+"/ATLAS-"+version+"-macOS-"+machine+"-PUBLIC.zip"
        guard urlText==expectedURL, url.user==nil, url.password==nil, url.fragment==nil else {throw SignedUpdateError.rejected("Unapproved update origin.")}
        let published=try date(obj["published_at"]), expires=try date(obj["expires_at"])
        guard published<=now.addingTimeInterval(300), published<expires, expires.timeIntervalSince(published)<=90*86400, now<expires else {throw SignedUpdateError.rejected("Release is expired or not yet valid.")}
        return AuthenticatedUpdate(version:version,sequence:seq,epoch:epoch,build:build,channel:channel,url:url,sha256:sha,size:size,
                                   minimumMacOS:minimum,architecture:machine,changelog:notes,expires:expires,manifestHash:SHA256.hash(data:raw).map{String(format:"%02x",$0)}.joined(),rawManifest:raw,rawSignature:signature)
    }
}
