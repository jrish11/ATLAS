import Foundation
import CryptoKit

// Storage and transport are deliberately separate. No fallback target is ever
// selected, and a revoked or offline computer cannot receive a request.
enum DeviceError: Error { case invalid, missing, offline, revoked, stale, denied }
struct LinkedComputer: Codable, Equatable, Identifiable {
    let id: UUID
    var name: String
    var origin: String
    var publicKey: Data
    var generation: UInt64
    var revoked: Bool
    var online: Bool
}
private func validComputer(_ computer: LinkedComputer) -> Bool {
    !computer.name.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty && computer.name.utf8.count<=80 &&
    !computer.name.unicodeScalars.contains(where:{$0.value<32 || $0.value==127}) &&
    computer.origin.range(of:#"^https://[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?$"#,options:.regularExpression) != nil &&
    URLComponents(string:computer.origin).map { c in c.host.map { $0 != "localhost" && !$0.hasSuffix(".localhost") && $0.contains(where:{$0.isLetter}) } == true && (c.port.map({(1...65535).contains($0)}) ?? true) } == true &&
    (try? P256.Signing.PublicKey(x963Representation:computer.publicKey)) != nil && computer.generation>0
}
struct DeviceRegistry: Codable {
    private(set) var computers: [LinkedComputer] = []
    private(set) var selected: UUID?
    init() {}
    private enum CodingKeys: String, CodingKey { case computers }
    init(from decoder: Decoder) throws {
        let c=try decoder.container(keyedBy:CodingKeys.self)
        let loaded=try c.decode([LinkedComputer].self,forKey:.computers)
        guard loaded.allSatisfy(validComputer),Set(loaded.map(\.id)).count==loaded.count else { throw DeviceError.invalid }
        computers=loaded.map { var item=$0;item.online=false;return item }
        selected=nil
    }
    func encode(to encoder: Encoder) throws {
        var c=encoder.container(keyedBy:CodingKeys.self)
        try c.encode(computers.map { var item=$0;item.online=false;return item },forKey:.computers)
    }
    mutating func add(_ computer: LinkedComputer) throws {
        guard validComputer(computer),!computers.contains(where:{$0.id==computer.id}),!computer.revoked else { throw DeviceError.invalid }
        computers.append(computer)
    }
    mutating func select(_ id: UUID) throws {
        guard let c=computers.first(where:{$0.id==id}) else { throw DeviceError.missing }
        guard !c.revoked else { throw DeviceError.revoked };selected=id
    }
    func target(_ explicitID: UUID) throws -> LinkedComputer {
        guard selected == explicitID,let c=computers.first(where:{$0.id==explicitID}) else { throw DeviceError.missing }
        guard !c.revoked else { throw DeviceError.revoked };guard c.online else { throw DeviceError.offline };return c
    }
    mutating func setOnline(_ id: UUID, _ online: Bool) throws {
        guard let i=computers.firstIndex(where:{$0.id==id}) else { throw DeviceError.missing };computers[i].online=online
    }
    /// Owner confirmation is supplied only by the local native UI. Remote
    /// delivery of a revocation remains a separate authenticated operation.
    mutating func revoke(_ id: UUID, ownerConfirmed: Bool) throws {
        guard ownerConfirmed else { throw DeviceError.denied }
        guard let i=computers.firstIndex(where:{$0.id==id}) else { throw DeviceError.missing }
        computers[i].revoked=true;computers[i].online=false
        if selected==id { selected=nil }
    }
    mutating func rotate(_ id: UUID, expectedGeneration: UInt64, publicKey: Data, ownerConfirmed: Bool) throws {
        guard ownerConfirmed else { throw DeviceError.denied }
        guard let i=computers.firstIndex(where:{$0.id==id}) else { throw DeviceError.missing }
        guard !computers[i].revoked else { throw DeviceError.revoked }
        guard computers[i].generation==expectedGeneration,expectedGeneration<UInt64.max else { throw DeviceError.stale }
        guard (try? P256.Signing.PublicKey(x963Representation:publicKey)) != nil,publicKey != computers[i].publicKey else { throw DeviceError.invalid }
        computers[i].publicKey=publicKey;computers[i].generation += 1;computers[i].online=false
    }
}
