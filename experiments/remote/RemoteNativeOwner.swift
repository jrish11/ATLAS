import Cocoa
import Darwin

// The web surfaces never issue supervisor-only remote control messages.
func webAgentActionAllowed(_ action: String) -> Bool { !action.hasPrefix("remote-") }

// A private child channel, never a listener. The caller must supply a trusted
// worker and the exact owner-selected immutable scope. Nothing starts it by default.
final class RemoteNativeOwner {
    struct Scope {
        let folder: String, id: String, revision: String
        let device: Int, inode: Int
        let expires: Double // mach continuous seconds, including sleep
    }
    struct Activation { let origin: String, token: String, csrf: String, invitation: String }
    private let scope: Scope
    private let activation: Activation?
    private let clock: () -> Double
    private let decide: (([String: Any], @escaping (Bool) -> Void) -> Void)?
    private weak var window: NSWindow?
    private var closeObserver: NSObjectProtocol?
    private let queue = DispatchQueue(label: "atlas.remote.owner")
    private let lock = NSLock()
    private var process: Process?
    private var socket: Int32 = -1
    private var generation: UInt64 = 0
    private var seen = Set<String>()
    private var sheet: NSAlert?
    private var sheetGeneration: UInt64?
    private var expiryTimer: DispatchSourceTimer?

    init(scope: Scope, clock: @escaping () -> Double, window: NSWindow? = nil, activation: Activation? = nil, decide: (([String: Any], @escaping (Bool) -> Void) -> Void)? = nil) {
        self.scope = scope; self.activation = activation; self.clock = clock; self.window = window; self.decide = decide
        if let window = window {
            closeObserver = NotificationCenter.default.addObserver(forName: NSWindow.willCloseNotification, object: window, queue: .main) { [weak self] _ in self?.stop() }
        }
    }
    deinit { stop(); if let observer = closeObserver { NotificationCenter.default.removeObserver(observer) } }
    static func alertDecision(window: NSWindow?, target: [String: Any], clock: () -> Double, completion: @escaping (Bool) -> Void) -> NSAlert {
        let alert = NSAlert(); let pairing = target["action"] as? String == "remote-pair"
        alert.messageText = pairing ? "Allow this phone to pair?" : "Allow this remote task?"
        let scope = target["scope"] as? [String: String] ?? [:]
        let identity = target["identity"] as? [String: Int] ?? [:]
        let subject = pairing ? "Device: \(target["device"] as? String ?? "")" : "Task:\n\(target["task"] as? String ?? "")"
        let expiry = (target["expires"] as? Double) ?? 0
        let when = Date(timeIntervalSinceNow:max(0,expiry-clock())).formatted(date:.abbreviated,time:.standard)
        alert.informativeText = "\(subject)\n\nProject: \(target["folder"] as? String ?? "")\nScope: \(scope["id"] ?? "") / \(scope["revision"] ?? "")\nFolder identity: \(identity["device"] ?? -1):\(identity["inode"] ?? -1)\nExpires: \(when)\n\nStop cannot undo an action already dispatched."
        alert.addButton(withTitle: pairing ? "Allow pairing" : "Allow task"); alert.addButton(withTitle: "Stop")
        if let window = window { alert.beginSheetModal(for: window) { completion($0 == .alertFirstButtonReturn) } }
        else { completion(false) }
        return alert
    }
    func start(executable: String, arguments: [String]) throws {
        lock.lock(); defer { lock.unlock() }
        guard process == nil, socket == -1, clock() < scope.expires else { throw NSError(domain: "RemoteOwner", code: 1) }
        var fds: [Int32] = [-1, -1]
        guard socketpair(AF_UNIX, SOCK_STREAM, 0, &fds) == 0 else { throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno)) }
        _ = fcntl(fds[0], F_SETFD, FD_CLOEXEC); _ = fcntl(fds[1], F_SETFD, FD_CLOEXEC)
        _ = fcntl(fds[0], F_SETNOSIGPIPE, 1)
        let child = FileHandle(fileDescriptor: fds[1], closeOnDealloc: true)
        let p = Process(); p.executableURL = URL(fileURLWithPath: executable); p.arguments = arguments
        p.standardInput = child; p.standardOutput = FileHandle.nullDevice; p.standardError = FileHandle.nullDevice
        do { try p.run() } catch { close(fds[0]); try? child.close(); throw error }
        try? child.close(); arm(fd: fds[0], child: p)
    }
    // Takes ownership of the native end of a socketpair already inherited by
    // the existing Agents supervisor. It does not terminate that supervisor.
    func attach(fd: Int32) throws {
        lock.lock(); defer { lock.unlock() }
        guard fd >= 0, process == nil, socket == -1, clock() < scope.expires else { throw NSError(domain: "RemoteOwner", code: 1) }
        _ = fcntl(fd, F_SETFD, FD_CLOEXEC); _ = fcntl(fd, F_SETNOSIGPIPE, 1)
        arm(fd: fd, child: nil)
    }
    private func arm(fd: Int32, child: Process?) {
        socket = fd; process = child; generation &+= 1; let current = generation; seen.removeAll()
        let timer = DispatchSource.makeTimerSource(queue: DispatchQueue.global())
        timer.schedule(deadline: .now(), repeating: .milliseconds(100))
        timer.setEventHandler { [weak self] in
            guard let self = self else { return }
            if self.clock() >= self.scope.expires { self.stop(generation: current) }
        }
        expiryTimer = timer; timer.resume()
        child?.terminationHandler = { [weak self] _ in self?.stop(generation: current) }
        queue.async { [weak self] in
            guard let self = self else { close(fd); return }
            self.serve(fd: fd, generation: current)
        }
    }
    func stop() { stop(generation: nil) }
    private func stop(generation expected: UInt64?) {
        lock.lock()
        guard expected == nil || expected == generation else { lock.unlock(); return }
        let stoppedGeneration = generation
        generation &+= 1; let fd = socket; socket = -1; let p = process; process = nil; let timer = expiryTimer; expiryTimer = nil
        lock.unlock()
        timer?.cancel()
        if fd >= 0 { _ = shutdown(fd, SHUT_RDWR) }
        if let p = p, p.isRunning { p.terminate() }
        DispatchQueue.main.async { [weak self] in
            guard let self = self, self.sheetGeneration == stoppedGeneration else { return }
            if let alert = self.sheet, let window = alert.window.sheetParent { window.endSheet(alert.window, returnCode: .cancel) }
            self.sheet = nil; self.sheetGeneration = nil
        }
    }
    private func readExact(_ fd: Int32, _ count: Int) -> Data? {
        var data = Data(count: count); var offset = 0
        let ok = data.withUnsafeMutableBytes { raw -> Bool in
            while offset < count {
                let n = Darwin.read(fd, raw.baseAddress!.advanced(by: offset), count-offset)
                if n <= 0 { return false }; offset += n
            }; return true
        }; return ok ? data : nil
    }
    private func frame(_ fd: Int32) -> [String: Any]? {
        guard let header = readExact(fd, 4) else { return nil }
        let length = header.reduce(0) { ($0 << 8) | Int($1) }
        guard length > 0, length <= 8192, let data = readExact(fd, length), let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { return nil }
        return obj
    }
    private func send(_ fd: Int32, _ obj: [String: Any]) -> Bool {
        guard let data = try? JSONSerialization.data(withJSONObject: obj), data.count <= 8192 else { return false }
        let n = data.count; var packet = Data([UInt8((n >> 24)&255), UInt8((n >> 16)&255), UInt8((n >> 8)&255), UInt8(n&255)]); packet.append(data)
        return packet.withUnsafeBytes { raw in
            var offset = 0
            while offset < raw.count { let n = Darwin.write(fd, raw.baseAddress!.advanced(by: offset), raw.count-offset); if n <= 0 { return false }; offset += n }; return true
        }
    }
    private func valid(_ message: [String: Any]) -> ([String: Any], String, String)? {
        guard Set(message.keys) == Set(["kind","id","revision","target"]), message["kind"] as? String == "request",
              let id = message["id"] as? String, let revision = message["revision"] as? String,
              id.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil,
              revision.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil,
              let target = message["target"] as? [String: Any], let action = target["action"] as? String,
              target["folder"] as? String == scope.folder,
              let s = target["scope"] as? [String: String], s == ["id":scope.id,"revision":scope.revision],
              let identity = target["identity"] as? [String: Int], identity == ["device":scope.device,"inode":scope.inode],
              let expires = target["expires"] as? Double, expires == scope.expires, clock() < expires else { return nil }
        if action == "remote-enable" {
            guard let approved=activation, Set(target.keys) == Set(["action","folder","scope","identity","expires","origin","credentials"]), target["origin"] as? String == approved.origin,
                  let credentials=target["credentials"] as? [String:String], credentials == ["token":approved.token,"csrf":approved.csrf,"invitation":approved.invitation] else { return nil }
        } else if action == "remote-codex-task" {
            guard Set(target.keys) == Set(["action","task","folder","scope","identity","expires"]), let task = target["task"] as? String, !task.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, task.count <= 4000, !task.contains("\0") else { return nil }
        } else if action == "remote-pair" {
            guard Set(target.keys) == Set(["action","device","folder","scope","identity","expires"]), let device = target["device"] as? String, !device.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty, device.count <= 80, !device.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 }) else { return nil }
        } else { return nil }
        return (target,id,revision)
    }
    private func serve(fd: Int32, generation current: UInt64) {
        defer { stop(generation: current); if fd >= 0 { close(fd) } }
        var activated = activation == nil
        while fd >= 0, let message = frame(fd), let (target,id,revision) = valid(message) {
            lock.lock(); let fresh = current == generation && !seen.contains(id); if fresh { seen.insert(id) }; lock.unlock()
            guard fresh else { return }
            if target["action"] as? String == "remote-enable" {
                guard !activated, clock() < scope.expires, send(fd,["kind":"decision","id":id,"revision":revision,"allow":true]) else { return }
                activated=true;continue
            }
            guard activated else { return }
            let semaphore = DispatchSemaphore(value: 0); let decisionLock = NSLock(); var decision = false
            DispatchQueue.main.async { [weak self] in
                guard let self = self else { semaphore.signal(); return }
                self.lock.lock(); let live = current == self.generation && self.clock() < self.scope.expires; self.lock.unlock()
                guard live else { semaphore.signal(); return }
                let done: (Bool) -> Void = { answer in decisionLock.lock(); decision = answer; decisionLock.unlock(); semaphore.signal() }
                if let decide = self.decide { decide(target, done) }
                else { self.sheetGeneration = current; self.sheet = Self.alertDecision(window: self.window, target: target, clock: self.clock, completion: done) }
            }
            while semaphore.wait(timeout: .now() + 0.1) == .timedOut {
                lock.lock(); let live = current == generation && clock() < scope.expires; lock.unlock()
                if !live { return }
            }
            lock.lock(); let live = current == generation && clock() < scope.expires; lock.unlock()
            decisionLock.lock(); let allow = decision && live; decisionLock.unlock()
            guard live, send(fd,["kind":"decision","id":id,"revision":revision,"allow":allow]) else { return }
            if !allow { return } // denial terminates this worker, not just this request
        }
    }
}
