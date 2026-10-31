// Isolated, opt-in Keychain helper. Secrets use stdin/stdout, never argv or files.
import Foundation
import Security

let service = "com.atticus.personal.dev.provider"
func reply(_ value: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: value), let text = String(data: data, encoding: .utf8) { print(text) }
}
let input = FileHandle.standardInput.readDataToEndOfFile()
guard input.count <= 32768, let request = (try? JSONSerialization.jsonObject(with: input)) as? [String: String],
      let action = request["action"] else { reply(["ok": false]); exit(1) }
let slot = request["slot"] ?? "custom-server"
guard ["custom-server", "openai-codex", "foreground-openai"].contains(slot) else { reply(["ok": false]); exit(1) }
let account = slot == "custom-server" ? "custom-server-api-key" : slot == "openai-codex" ? "openai-codex-api-key" : "foreground-openai-api-key"
let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                            kSecAttrService as String: service,
                            kSecAttrAccount as String: account]
var status: OSStatus = errSecParam
switch action {
case "set":
    guard let secret = request["secret"], !secret.isEmpty, let data = secret.data(using: .utf8) else { reply(["ok": false]); exit(1) }
    status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
    if status == errSecItemNotFound {
        var item = query
        item[kSecValueData as String] = data
        item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        status = SecItemAdd(item as CFDictionary, nil)
    }
    reply(["ok": status == errSecSuccess])
case "get":
    var item = query
    item[kSecReturnData as String] = true
    item[kSecMatchLimit as String] = kSecMatchLimitOne
    var result: CFTypeRef?
    status = SecItemCopyMatching(item as CFDictionary, &result)
    if status == errSecSuccess, let data = result as? Data, let secret = String(data: data, encoding: .utf8) {
        reply(["ok": true, "secret": secret])
    } else { reply(["ok": false, "missing": status == errSecItemNotFound]) }
case "delete":
    status = SecItemDelete(query as CFDictionary)
    reply(["ok": status == errSecSuccess || status == errSecItemNotFound])
default: reply(["ok": false]); exit(1)
}
exit(status == errSecSuccess || (action == "delete" && status == errSecItemNotFound) ? 0 : 1)
