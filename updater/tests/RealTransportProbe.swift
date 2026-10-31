// Explicit optional public transport probe. Not part of offline regression.
// Memory only: no extraction, installation, credentials or provider calls.
import Foundation
import CryptoKit
@main struct Probe {
 static func main()async throws {
    let expected="2c1335d796fd53880dbb8dbcc57733493b39e952dd5b9626fcc2ab0adf5d259e"
    let url=URL(string:"https://github.com/jrish11/ATLAS/releases/download/v3.6/ATLAS-v3.6-macOS-arm64-PUBLIC.zip")!
    let start=ProcessInfo.processInfo.systemUptime
    let bytes=try await BoundedUpdateDownloader().fetch(url,maximum:2_127_724,expectedSize:2_127_724)
    let hash=SHA256.hash(data:bytes).map{String(format:"%02x",$0)}.joined()
    guard hash==expected else{throw SignedUpdateError.rejected("Public transport probe digest changed.")}
    print(String(format:"Public GitHub transport verified: %d bytes, SHA256 matched, %.3f seconds; no installation.",bytes.count,ProcessInfo.processInfo.systemUptime-start))
 }
}
