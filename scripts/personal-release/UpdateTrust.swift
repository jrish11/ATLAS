// Verification component only. No downloader, installer, private key or user-state access.
import Foundation
import CryptoKit

enum AtlasReleaseTrust {
    // Intentionally empty until the owner approves release-signing key provisioning
    // and independently verifies a public fingerprint in a trusted app release.
    // Never populate this map from GitHub metadata, preferences, environment or UI.
    private static let pinnedPublicKeys: [String: Data] = [:]

    static var configured: Bool { !pinnedPublicKeys.isEmpty }

    static func verifies(keyID: String, signature: Data, manifest: Data) -> Bool {
        guard manifest.count > 0, manifest.count <= 256 * 1024,
              signature.count == 64, let raw = pinnedPublicKeys[keyID], raw.count == 32,
              let key = try? Curve25519.Signing.PublicKey(rawRepresentation: raw)
        else { return false }
        return key.isValidSignature(signature, for: manifest)
    }
}
