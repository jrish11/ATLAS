// Request evidence crypto primitive. Key and data travel only over private
// stdin/stdout pipes; this helper never accesses Keychain or the filesystem.
import Foundation
import CryptoKit

func fail() -> Never {
    print("{\"ok\":false}")
    exit(1)
}
let input = FileHandle.standardInput.readDataToEndOfFile()
guard input.count <= 2_000_000,
      let request = (try? JSONSerialization.jsonObject(with: input)) as? [String: String],
      Set(request.keys) == Set(["action", "key", "data", "aad"]),
      let action = request["action"], let keyText = request["key"],
      let key = Data(base64Encoded: keyText), key.count == 32,
      let dataText = request["data"], let data = Data(base64Encoded: dataText),
      let aadText = request["aad"], let aad = Data(base64Encoded: aadText),
      aad.count <= 256 else { fail() }
do {
    let secret = SymmetricKey(data: key)
    let result: Data
    switch action {
    case "seal":
        guard let combined = try AES.GCM.seal(data, using: secret, authenticating: aad).combined else { fail() }
        result = combined
    case "open":
        result = try AES.GCM.open(AES.GCM.SealedBox(combined: data), using: secret, authenticating: aad)
    default: fail()
    }
    guard let encoded = try? JSONSerialization.data(withJSONObject: ["ok": true, "data": result.base64EncodedString()]),
          let line = String(data: encoded, encoding: .utf8) else { fail() }
    print(line)
} catch { fail() }
