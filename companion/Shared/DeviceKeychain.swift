import Foundation
import Security

// No Keychain operation occurs on construction. The caller must obtain the
// local owner's approval before invoking write/delete. This store is not wired
// to either application yet and is not exercised against the real Keychain.
protocol SecureDeviceStorage {
    var storageIdentifier:String { get }
    func read() throws -> Data?
    func write(_ data: Data) throws
    func delete() throws
}
struct DeviceKeychain: SecureDeviceStorage {
    let service: String
    var storageIdentifier:String { "keychain:"+service+":pairing-v1" }
    private var query: [String:Any] { [kSecClass as String:kSecClassGenericPassword,kSecAttrService as String:service,kSecAttrAccount as String:"pairing-v1",kSecAttrSynchronizable as String:false] }
    func read() throws -> Data? {
        var q=query;q[kSecReturnData as String]=true;q[kSecMatchLimit as String]=kSecMatchLimitOne
        var result:CFTypeRef?;let status=SecItemCopyMatching(q as CFDictionary,&result)
        if status==errSecItemNotFound { return nil }
        guard status==errSecSuccess,let data=result as? Data else { throw NSError(domain:NSOSStatusErrorDomain,code:Int(status)) };return data
    }
    func write(_ data: Data) throws {
        guard !data.isEmpty,data.count<=65536 else { throw DeviceError.invalid }
        var q=query;let changes:[String:Any]=[kSecValueData as String:data,kSecAttrAccessible as String:kSecAttrAccessibleWhenUnlockedThisDeviceOnly]
        var status=SecItemUpdate(q as CFDictionary,changes as CFDictionary)
        if status==errSecItemNotFound { q[kSecValueData as String]=data;q[kSecAttrAccessible as String]=kSecAttrAccessibleWhenUnlockedThisDeviceOnly;status=SecItemAdd(q as CFDictionary,nil) }
        guard status==errSecSuccess else { throw NSError(domain:NSOSStatusErrorDomain,code:Int(status)) }
    }
    func delete() throws {
        let status=SecItemDelete(query as CFDictionary)
        guard status==errSecSuccess || status==errSecItemNotFound else { throw NSError(domain:NSOSStatusErrorDomain,code:Int(status)) }
    }
}
