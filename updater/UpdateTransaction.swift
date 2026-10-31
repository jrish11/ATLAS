// Filesystem transaction only. The native coordinator must verify signatures,
// release ordering, owner consent and application idleness before calling it.
import Foundation
import CryptoKit
import Darwin

public struct UpdateBundleIdentity: Codable, Equatable {
    public let bundleIdentifier: String
    public let build: Int
    public let epoch: Int
    public let digest: String
    public init(bundleIdentifier: String, build: Int, epoch: Int, digest: String) {
        self.bundleIdentifier = bundleIdentifier; self.build = build; self.epoch = epoch; self.digest = digest
    }
}
public struct UpdateTransactionOrder: Codable, Equatable {
    public let version: String
    public let sequence: Int
    public let epoch: Int
    public let build: Int
    public init(version: String, sequence: Int, epoch: Int, build: Int) {
        self.version = version; self.sequence = sequence; self.epoch = epoch; self.build = build
    }
}
public enum UpdateTransactionError: Error, CustomStringConvertible {
    case invalid(String), system(String, Int32), conflict(String), busy, cancelled
    public var description: String {
        switch self {
        case .invalid(let s): return "Invalid update: \(s)"
        case .system(let s, let e): return "Update filesystem failure: \(s) (\(e))"
        case .conflict(let s): return "Update requires inspection: \(s)"
        case .busy: return "Another update transaction holds the installation lock"
        case .cancelled: return "Update cancelled before atomic replacement"
        }
    }
}
private func checked(_ value: Int32, _ operation: String) throws -> Int32 {
    guard value >= 0 else { throw UpdateTransactionError.system(operation, errno) }; return value
}
private func statFD(_ fd: Int32) throws -> stat {
    var s = stat(); _ = try checked(fstat(fd, &s), "fstat"); return s
}
private func sameNode(_ a: stat, _ b: stat) -> Bool { a.st_dev == b.st_dev && a.st_ino == b.st_ino }
private func stableNode(_ a: stat, _ b: stat) -> Bool {
    sameNode(a,b) && a.st_mode == b.st_mode && a.st_uid == b.st_uid && a.st_gid == b.st_gid && a.st_size == b.st_size && a.st_nlink == b.st_nlink && a.st_flags == b.st_flags && a.st_mtimespec.tv_sec == b.st_mtimespec.tv_sec && a.st_mtimespec.tv_nsec == b.st_mtimespec.tv_nsec && a.st_ctimespec.tv_sec == b.st_ctimespec.tv_sec && a.st_ctimespec.tv_nsec == b.st_ctimespec.tv_nsec
}
private func names(_ fd: Int32) throws -> [String] {
    let duplicate = try checked(dup(fd), "dup directory")
    guard let directory = fdopendir(duplicate) else { close(duplicate); throw UpdateTransactionError.system("fdopendir", errno) }
    defer { closedir(directory) }
    rewinddir(directory)
    var result: [String] = []; errno = 0
    while let entry = readdir(directory) {
        let name: String? = withUnsafePointer(to: &entry.pointee.d_name) { pointer in
            pointer.withMemoryRebound(to: CChar.self, capacity: Int(entry.pointee.d_namlen) + 1) { String(validatingUTF8: $0) }
        }
        guard let name else { throw UpdateTransactionError.invalid("Non-UTF8 file name") }
        if name != "." && name != ".." { result.append(name) }; errno = 0
    }
    guard errno == 0 else { throw UpdateTransactionError.system("readdir", errno) }
    return result.sorted()
}
private func aclBytes(_ fd: Int32, rejectAllows: Bool = false) throws -> Data {
    guard let acl = acl_get_fd_np(fd, ACL_TYPE_EXTENDED) else { if errno == ENOENT { return Data() }; throw UpdateTransactionError.system("read ACL",errno) }
    defer { acl_free(UnsafeMutableRawPointer(acl)) }
    if rejectAllows {
        var entry: acl_entry_t?; var position = ACL_FIRST_ENTRY
        while true {
            let next = acl_get_entry(acl, Int32(position.rawValue), &entry); position = ACL_NEXT_ENTRY
            if next == -1 { if errno == EINVAL { break }; throw UpdateTransactionError.system("read ACL entry",errno) }
            var tag = ACL_UNDEFINED_TAG
            guard acl_get_tag_type(entry!, &tag) == 0 else { throw UpdateTransactionError.system("read ACL tag",errno) }
            guard tag != ACL_EXTENDED_ALLOW else { throw UpdateTransactionError.invalid("Directory ACL grants additional access") }
        }
    }
    var size: ssize_t = 0
    guard let text = acl_to_text(acl, &size), size >= 0, size <= 1_048_576 else { throw UpdateTransactionError.invalid("Unreadable ACL") }
    defer { acl_free(text) }; return Data(bytes:text,count:size)
}
private func noLinkDirectory(_ url: URL, privateOnly: Bool = false) throws -> Int32 {
    guard url.isFileURL, url.path.hasPrefix("/"), !url.pathComponents.contains(".."), !url.pathComponents.contains(".") else { throw UpdateTransactionError.invalid("Canonical absolute directory required") }
    var fd = try checked(open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC), "open root")
    do {
        for part in url.pathComponents.dropFirst() {
            guard part != "..", part != "." else { throw UpdateTransactionError.invalid("Unsafe path component") }
            let next = try checked(openat(fd, part, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC), "open directory without links")
            close(fd); fd = next
        }
        let s = try statFD(fd)
        guard s.st_uid == geteuid(), s.st_mode & 0o022 == 0, !privateOnly || s.st_mode & 0o077 == 0 else { throw UpdateTransactionError.invalid("Directory must be owner controlled" ) }
        _ = try aclBytes(fd,rejectAllows:true)
        return fd
    } catch { close(fd); throw error }
}
private func syncDirectory(_ fd: Int32) throws { _ = try checked(fsync(fd), "fsync directory") }
private func syncFile(_ fd: Int32) throws {
    _ = try checked(fsync(fd), "fsync file")
    if fcntl(fd, F_FULLFSYNC) < 0 { throw UpdateTransactionError.system("full fsync file", errno) }
}

public enum UpdateFileTree {
    // Includes every entry, regular-file bytes, mode/ownership/timestamps and
    // extended attributes. Rejects symlinks, special files and multiply linked
    // files; directory and file identities are rechecked after reading.
    public static func identity(app: URL) throws -> UpdateBundleIdentity {
        let fd = try noLinkDirectory(app); defer { close(fd) }
        var hash = SHA256()
        func frame(_ bytes: Data) { hash.update(data: Data("\(bytes.count):".utf8)); hash.update(data: bytes) }
        func text(_ string: String) { frame(Data(string.utf8)) }
        func attributes(_ node: Int32) throws {
            let length = flistxattr(node, nil, 0, 0)
            guard length >= 0, length <= 1_048_576 else { throw UpdateTransactionError.invalid("Unreadable or excessive extended attributes") }
            var buffer = [CChar](repeating: 0, count: max(length,1))
            let actual = flistxattr(node, &buffer, length, 0)
            guard actual == length else { throw UpdateTransactionError.conflict("Attributes changed") }
            let attributeNames = buffer.prefix(length).split(separator: 0).map { Data($0.map { UInt8(bitPattern: $0) }) }.sorted { $0.lexicographicallyPrecedes($1) }
            for encoded in attributeNames {
                guard let name = String(data: encoded, encoding: .utf8) else { throw UpdateTransactionError.invalid("Invalid attribute name") }
                text(name)
                let size = fgetxattr(node, name, nil, 0, 0, 0)
                guard size >= 0, size <= 16_777_216 else { throw UpdateTransactionError.invalid("Unreadable or excessive attribute") }
                var value = Data(count: size)
                let read = value.withUnsafeMutableBytes { fgetxattr(node, name, $0.baseAddress, size, 0, 0) }
                guard read == size else { throw UpdateTransactionError.conflict("Attribute changed") }; frame(value)
            }
            text("end-attributes")
        }
        var count = 0
        var infoBytes: Data?
        func walk(_ node: Int32, _ relative: String) throws {
            count += 1; guard count <= 100_000 else { throw UpdateTransactionError.invalid("Excessive app tree") }
            let before = try statFD(node), type = before.st_mode & S_IFMT
            guard type == S_IFDIR || type == S_IFREG, type != S_IFREG || before.st_nlink == 1 else { throw UpdateTransactionError.invalid("Links and special files are unsupported") }
            text(relative); text("\(before.st_mode):\(before.st_uid):\(before.st_gid):\(before.st_mtimespec.tv_sec):\(before.st_mtimespec.tv_nsec)")
            text("flags:\(before.st_flags)"); frame(try aclBytes(node))
            try attributes(node)
            if type == S_IFDIR {
                for name in try names(node) {
                    let child = try checked(openat(node, name, O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC), "open app entry")
                    defer { close(child) }; try walk(child, relative + "/" + name)
                }
            } else {
                guard before.st_size >= 0, before.st_size <= 4_294_967_296 else { throw UpdateTransactionError.invalid("Excessive app file") }
                text("\(before.st_size)"); var captured = Data(); var buffer = [UInt8](repeating: 0, count: 65536); var total: Int64 = 0
                while true {
                    let n = Darwin.read(node, &buffer, buffer.count)
                    guard n >= 0 else { throw UpdateTransactionError.system("read app", errno) }; if n == 0 { break }
                    total += Int64(n); guard total <= before.st_size else { throw UpdateTransactionError.conflict("File grew") }
                    hash.update(data: Data(buffer.prefix(n)))
                    if relative == "/Contents/Info.plist" { guard total <= 1_048_576 else { throw UpdateTransactionError.invalid("Excessive Info.plist") }; captured.append(contentsOf:buffer.prefix(n)) }
                }
                guard total == before.st_size else { throw UpdateTransactionError.conflict("File shrank") }
                if relative == "/Contents/Info.plist" { infoBytes = captured }
            }
            guard stableNode(before, try statFD(node)) else { throw UpdateTransactionError.conflict("App entry changed while hashing") }
        }
        try walk(fd, "")
        guard let data = infoBytes, let info = try PropertyListSerialization.propertyList(from: data, format: nil) as? [String: Any], let identifier = info["CFBundleIdentifier"] as? String, !identifier.isEmpty, let buildText = info["CFBundleVersion"] as? String, let build = Int(buildText), build >= 0 else { throw UpdateTransactionError.invalid("Missing bundle identity") }
        let epoch = (info["ATLASUpdateEpoch"] as? NSNumber)?.intValue ?? 1
        guard epoch >= 0 else { throw UpdateTransactionError.invalid("Invalid update epoch") }
        return UpdateBundleIdentity(bundleIdentifier: identifier, build: build, epoch: epoch, digest: hash.finalize().map { String(format: "%02x", $0) }.joined())
    }
}

public struct UpdateTransactionRecord: Codable, Equatable {
    public let schema: Int
    public let id: String
    public let target: String
    public let staged: String
    public let backup: String
    public let old: UpdateBundleIdentity
    public let new: UpdateBundleIdentity
    public let order: UpdateTransactionOrder
    public fileprivate(set) var phase: String
    fileprivate let oldNode: String
    fileprivate let newNode: String
}
public struct UpdateRecoveryInspection: Equatable {
    public let record: UpdateTransactionRecord
    public let disposition: String
}

public final class UpdateTransactionStore {
    private let parent: URL, state: URL
    private let parentFD: Int32, stateFD: Int32
    private let parentNode: stat, stateNode: stat
    private let verify: (URL) throws -> UpdateBundleIdentity
    // Fault injection is for temporary-fixture tests, never an authority source.
    public var fault: ((String) throws -> Void)?
    public init(installationParent: URL, stateDirectory: URL, verifyBundle: @escaping (URL) throws -> UpdateBundleIdentity) throws {
        parent = installationParent; state = stateDirectory; verify = verifyBundle
        parentFD = try noLinkDirectory(installationParent)
        do { stateFD = try noLinkDirectory(stateDirectory, privateOnly: true) }
        catch { close(parentFD); throw error }
        do { parentNode = try statFD(parentFD); stateNode = try statFD(stateFD) }
        catch { close(parentFD); close(stateFD); throw error }
    }
    deinit { close(parentFD); close(stateFD) }
    private func pinned() throws {
        let p = try noLinkDirectory(parent); defer { close(p) }
        let s = try noLinkDirectory(state, privateOnly: true); defer { close(s) }
        guard sameNode(parentNode, try statFD(p)), sameNode(stateNode, try statFD(s)) else { throw UpdateTransactionError.conflict("Pinned directory replaced") }
    }
    private func locked<T>(_ body: () throws -> T) throws -> T {
        try pinned()
        let fd = try checked(openat(parentFD, ".atlas-update.lock", O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, 0o600), "open installation lock"); defer { close(fd) }
        let before = try statFD(fd)
        guard before.st_mode & S_IFMT == S_IFREG, before.st_nlink == 1, before.st_uid == geteuid(), before.st_mode & 0o077 == 0 else { throw UpdateTransactionError.invalid("Unsafe lock file") }
        guard flock(fd, LOCK_EX | LOCK_NB) == 0 else { if errno == EWOULDBLOCK { throw UpdateTransactionError.busy }; throw UpdateTransactionError.system("flock",errno) }
        defer { flock(fd, LOCK_UN) }
        var now = stat(); _ = try checked(fstatat(parentFD, ".atlas-update.lock", &now, AT_SYMLINK_NOFOLLOW), "check lock identity")
        guard sameNode(before,now) else { throw UpdateTransactionError.conflict("Lock replaced") }
        try pinned(); return try body()
    }
    private func basename(_ app: URL) throws -> String {
        guard app.isFileURL, app.deletingLastPathComponent().path == parent.path, !app.pathComponents.contains(".."), !app.pathComponents.contains("."), app.lastPathComponent.hasSuffix(".app"), !app.lastPathComponent.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) else { throw UpdateTransactionError.invalid("App must be a direct child of installation parent") }
        guard !state.path.hasPrefix(app.path + "/"), state.path != app.path else { throw UpdateTransactionError.invalid("State cannot be inside an app") }
        return app.lastPathComponent
    }
    private func node(_ name: String) throws -> String {
        let fd = try checked(openat(parentFD, name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC), "open app identity"); defer { close(fd) }
        let s = try statFD(fd); guard s.st_dev == parentNode.st_dev else { throw UpdateTransactionError.invalid("App must be on installation volume") }
        return "\(s.st_dev):\(s.st_ino)"
    }
    private func flushTree(_ name: String) throws {
        let root = try checked(openat(parentFD,name,O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC),"open staged tree for durability"); defer { close(root) }
        func flush(_ fd: Int32) throws {
            let before = try statFD(fd), type = before.st_mode & S_IFMT
            if type == S_IFDIR {
                for entry in try names(fd) {
                    let child = try checked(openat(fd,entry,O_RDONLY | O_NONBLOCK | O_NOFOLLOW | O_CLOEXEC),"open staged durability entry"); defer { close(child) }
                    try flush(child)
                }
                try syncDirectory(fd)
            } else if type == S_IFREG && before.st_nlink == 1 { try syncFile(fd) }
            else { throw UpdateTransactionError.invalid("Unsafe staged durability entry") }
            guard stableNode(before,try statFD(fd)) else { throw UpdateTransactionError.conflict("Staged tree changed during flush") }
        }
        try flush(root); try syncDirectory(parentFD)
    }
    private func identity(_ name: String) throws -> UpdateBundleIdentity {
        let before = try node(name), result = try verify(parent.appendingPathComponent(name))
        guard before == (try node(name)) else { throw UpdateTransactionError.conflict("App replaced during verification") }; return result
    }
    private func matches(_ name: String, _ expected: UpdateBundleIdentity, _ expectedNode: String) -> Bool {
        (try? node(name)) == expectedNode && (try? identity(name)) == expected
    }
    private func exists(_ name: String) -> Bool { var s = stat(); return fstatat(parentFD, name, &s, AT_SYMLINK_NOFOLLOW) == 0 || errno != ENOENT }
    private func validIdentity(_ value: UpdateBundleIdentity) -> Bool {
        value.build >= 0 && value.epoch >= 0 && !value.bundleIdentifier.isEmpty && value.bundleIdentifier.utf8.count <= 255 && !value.bundleIdentifier.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) && value.digest.utf8.count == 64 && value.digest.utf8.allSatisfy { (48...57).contains($0) || (97...102).contains($0) }
    }
    private func validOrder(_ value: UpdateTransactionOrder, _ new: UpdateBundleIdentity) -> Bool {
        value.sequence > 0 && value.epoch == new.epoch && value.build == new.build && !value.version.isEmpty && value.version.utf8.count <= 128 && !value.version.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) })
    }
    private func validID(_ id: String) throws { guard UUID(uuidString:id)?.uuidString.lowercased() == id else { throw UpdateTransactionError.invalid("Invalid transaction id") } }
    private func save(_ record: UpdateTransactionRecord) throws {
        try pinned(); let name = record.id + ".json", temp = ".journal-" + UUID().uuidString
        let fd = try checked(openat(stateFD, temp, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0o600), "create journal")
        defer { close(fd); unlinkat(stateFD, temp, 0) }
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys]; let data = try encoder.encode(record)
        try data.withUnsafeBytes { bytes in
            var offset = 0
            while offset < bytes.count { let n = Darwin.write(fd, bytes.baseAddress!.advanced(by:offset), bytes.count-offset); guard n > 0 else { throw UpdateTransactionError.system("write journal",errno) }; offset += n }
        }
        try syncFile(fd)
        _ = try checked(renameat(stateFD, temp, stateFD, name), "commit journal"); try syncDirectory(stateFD)
    }
    private func load(_ id: String) throws -> UpdateTransactionRecord {
        try validID(id); let fd = try checked(openat(stateFD, id + ".json", O_RDONLY | O_NOFOLLOW | O_CLOEXEC), "open journal"); defer { close(fd) }
        let s = try statFD(fd); guard s.st_mode & S_IFMT == S_IFREG, s.st_nlink == 1, s.st_uid == geteuid(), s.st_mode & 0o077 == 0, s.st_size > 0, s.st_size < 65536 else { throw UpdateTransactionError.invalid("Unsafe journal") }
        var bytes = [UInt8](repeating:0,count:Int(s.st_size)); guard Darwin.read(fd,&bytes,bytes.count) == bytes.count else { throw UpdateTransactionError.conflict("Journal changed") }
        let record = try JSONDecoder().decode(UpdateTransactionRecord.self,from:Data(bytes))
        guard record.schema == 1, record.id == id, validIdentity(record.old), validIdentity(record.new), validOrder(record.order,record.new), record.old.bundleIdentifier == record.new.bundleIdentifier, record.backup == ".atlas-backup-" + id + ".app", ["prepared","cancelled","swapPending","swapped","active","launched","rollbackPending","rolledBack"].contains(record.phase), [record.target,record.staged,record.backup].allSatisfy({ !$0.isEmpty && !$0.contains("/") && $0 != "." && $0 != ".." && $0.hasSuffix(".app") }), Set([record.target,record.staged,record.backup]).count == 3 else { throw UpdateTransactionError.invalid("Invalid journal record") }; return record
    }
    private func records() throws -> [UpdateTransactionRecord] { try names(stateFD).filter { $0.hasSuffix(".json") }.map { try load(String($0.dropLast(5))) } }
    @discardableResult public func prepare(stagedApp: URL, targetApp: URL, expectedOld: UpdateBundleIdentity, expectedNew: UpdateBundleIdentity, order: UpdateTransactionOrder) throws -> UpdateTransactionRecord {
        try locked {
            let target = try basename(targetApp), staged = try basename(stagedApp)
            guard target != staged, validIdentity(expectedOld), validIdentity(expectedNew), validOrder(order,expectedNew), expectedOld.bundleIdentifier == expectedNew.bundleIdentifier, expectedNew.epoch >= expectedOld.epoch, expectedNew.epoch > expectedOld.epoch || expectedNew.build > expectedOld.build, expectedNew.digest != expectedOld.digest, order.build == expectedNew.build, order.epoch == expectedNew.epoch, order.sequence > 0, !order.version.isEmpty else { throw UpdateTransactionError.invalid("Invalid update identity or order") }
            let existing = try records()
            guard existing.allSatisfy({ $0.phase == "rolledBack" || $0.phase == "launched" || $0.phase == "cancelled" }) else { throw UpdateTransactionError.conflict("An update is pending inspection") }
            guard !existing.filter({ $0.phase != "cancelled" }).contains(where: { $0.order.sequence >= order.sequence || $0.new == expectedNew }) else { throw UpdateTransactionError.conflict("Stale or duplicate release") }
            try flushTree(staged)
            guard try identity(target) == expectedOld, try identity(staged) == expectedNew else { throw UpdateTransactionError.conflict("Bundle digest changed") }
            let id = UUID().uuidString.lowercased(), backup = ".atlas-backup-" + id + ".app"
            guard !exists(backup) else { throw UpdateTransactionError.conflict("Backup already exists") }
            let record = UpdateTransactionRecord(schema:1,id:id,target:target,staged:staged,backup:backup,old:expectedOld,new:expectedNew,order:order,phase:"prepared",oldNode:try node(target),newNode:try node(staged))
            try save(record); return record
        }
    }
    // Owner-requested cancellation of a provably unstarted transaction only.
    // Keep the candidate for inspection; never infer that a pending swap failed.
    @discardableResult public func cancelPrepared(id:String)throws->UpdateTransactionRecord {
        try locked {
            var record=try load(id)
            guard record.phase=="prepared",matches(record.target,record.old,record.oldNode),matches(record.staged,record.new,record.newNode),!exists(record.backup) else{throw UpdateTransactionError.conflict("Only an unchanged, unstarted update can be discarded")}
            record.phase="cancelled";try save(record);return record
        }
    }
    @discardableResult public func activate(id: String, cancelled: () -> Bool = { false }) throws -> UpdateTransactionRecord {
        try locked {
            var record = try load(id)
            guard record.phase == "prepared" else { throw UpdateTransactionError.conflict("Activation already attempted") }
            guard matches(record.target,record.old,record.oldNode), matches(record.staged,record.new,record.newNode), !exists(record.backup) else { throw UpdateTransactionError.conflict("Activation inputs changed") }
            if cancelled() { record.phase="cancelled"; try save(record); throw UpdateTransactionError.cancelled }
            record.phase="swapPending"; try save(record); try fault?("beforeSwap")
            try pinned()
            guard matches(record.target,record.old,record.oldNode), matches(record.staged,record.new,record.newNode), !exists(record.backup) else { throw UpdateTransactionError.conflict("Activation inputs changed before swap") }
            if cancelled() { record.phase="cancelled"; try save(record); throw UpdateTransactionError.cancelled }
            _ = try checked(renameatx_np(parentFD,record.target,parentFD,record.staged,UInt32(RENAME_SWAP)), "atomic app exchange")
            try syncDirectory(parentFD); try fault?("afterSwap")
            guard matches(record.target,record.new,record.newNode), matches(record.staged,record.old,record.oldNode) else { throw UpdateTransactionError.conflict("Post-swap identity mismatch") }
            record.phase="swapped"; try save(record); try fault?("beforeBackup")
            _ = try checked(renameatx_np(parentFD,record.staged,parentFD,record.backup,UInt32(RENAME_EXCL)), "preserve previous app")
            try syncDirectory(parentFD); try fault?("afterBackup"); try fault?("beforeReceipt")
            record.phase="active"; try save(record); try fault?("afterReceipt"); return record
        }
    }
    @discardableResult public func markLaunched(id: String) throws -> UpdateTransactionRecord {
        try locked {
            var record = try load(id)
            guard record.phase == "active", matches(record.target,record.new,record.newNode), matches(record.backup,record.old,record.oldNode) else { throw UpdateTransactionError.conflict("Launch receipt does not match active bundle") }
            record.phase="launched"; try save(record); return record
        }
    }
    @discardableResult public func rollback(id: String, cancelled: () -> Bool = { false }) throws -> UpdateTransactionRecord {
        try locked {
            var record = try load(id)
            guard ["swapPending","swapped","active","launched","rollbackPending"].contains(record.phase), matches(record.target,record.new,record.newNode) else { throw UpdateTransactionError.conflict("Rollback outcome needs inspection") }
            let oldLocation: String
            if matches(record.backup,record.old,record.oldNode), !exists(record.staged) { oldLocation = record.backup }
            else if matches(record.staged,record.old,record.oldNode), !exists(record.backup) { oldLocation = record.staged }
            else { throw UpdateTransactionError.conflict("Backup identity ambiguous") }
            if cancelled() { throw UpdateTransactionError.cancelled }
            record.phase="rollbackPending"; try save(record); try fault?("beforeRollback"); try pinned()
            guard matches(record.target,record.new,record.newNode), matches(oldLocation,record.old,record.oldNode) else { throw UpdateTransactionError.conflict("Rollback inputs changed") }
            if cancelled() { throw UpdateTransactionError.cancelled }
            _ = try checked(renameatx_np(parentFD,record.target,parentFD,oldLocation,UInt32(RENAME_SWAP)), "atomic rollback")
            try syncDirectory(parentFD); try fault?("afterRollback")
            guard matches(record.target,record.old,record.oldNode), matches(oldLocation,record.new,record.newNode) else { throw UpdateTransactionError.conflict("Rollback verification failed") }
            record.phase="rolledBack"; try save(record); return record
        }
    }
    public func recover() throws -> [UpdateRecoveryInspection] {
        try locked {
            let all = try records()
            return all.map { record in
                let oldAtTarget=matches(record.target,record.old,record.oldNode), newAtTarget=matches(record.target,record.new,record.newNode)
                let oldAtStage=matches(record.staged,record.old,record.oldNode), newAtStage=matches(record.staged,record.new,record.newNode)
                let oldAtBackup=matches(record.backup,record.old,record.oldNode), newAtBackup=matches(record.backup,record.new,record.newNode)
                let disposition: String
                if ["prepared","cancelled"].contains(record.phase), oldAtTarget,newAtStage,!exists(record.backup) { disposition=record.phase }
                else if record.phase == "swapPending",oldAtTarget,newAtStage,!exists(record.backup) { disposition="notSwappedNeedsReview" }
                else if ["swapPending","swapped"].contains(record.phase),newAtTarget,oldAtStage,!exists(record.backup) { disposition="swappedBackupPending" }
                else if ["swapPending","swapped","active","launched"].contains(record.phase),newAtTarget,oldAtBackup,!exists(record.staged) { disposition=record.phase == "launched" ? "launched" : "activeNeedsLaunchConfirmation" }
                else if ["rollbackPending","rolledBack"].contains(record.phase),oldAtTarget,((newAtBackup && !exists(record.staged)) || (newAtStage && !exists(record.backup))) { disposition=record.phase == "rolledBack" ? "rolledBack" : "rollbackAppliedNeedsReview" }
                else if record.phase == "rollbackPending",newAtTarget,((oldAtBackup && !exists(record.staged)) || (oldAtStage && !exists(record.backup))) { disposition="rollbackNotAppliedNeedsReview" }
                else if ["launched","rolledBack"].contains(record.phase), all.contains(where: { $0.target == record.target && $0.order.sequence > record.order.sequence && $0.phase != "cancelled" }) { disposition="historicalCompleted" }
                else { disposition="conflict" }
                return UpdateRecoveryInspection(record:record,disposition:disposition)
            }
        }
    }
}
