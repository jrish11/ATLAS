import Foundation
import CryptoKit
import Security

// Inactive pairing primitives. No socket, persistence or task authority lives here.
enum EnrollmentError: Error { case invalid, expired, replay, denied, badState, entropy }

struct EnrollmentChallenge: Codable {
    let version: Int
    let hostID: UUID
    let origin: String
    let macName: String
    let nonce: Data
    let macEphemeral: Data
    let macSigningPublic: Data
}
struct EnrollmentResponse: Codable {
    let phoneName: String
    let nonce: Data
    let phoneEphemeral: Data
}
struct EnrollmentComparison {
    let phoneName: String
    let code: String
}
final class ApprovedEnrollment {
    let channel:SymmetricKey, binding:Data, hostID:UUID, macSigningPublic:Data, phoneName:String, deadline:Double
    private let lock=NSLock();private var claimed=false
    fileprivate init(channel:SymmetricKey,binding:Data,hostID:UUID,macSigningPublic:Data,phoneName:String,deadline:Double) {
        self.channel=channel;self.binding=binding;self.hostID=hostID;self.macSigningPublic=macSigningPublic;self.phoneName=phoneName;self.deadline=deadline
    }
    func consume() throws { lock.lock();defer{lock.unlock()};guard !claimed else { throw EnrollmentError.replay };claimed=true }
}

private func validName(_ s: String) -> Bool {
    !s.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty && s.utf8.count <= 80 &&
    !s.unicodeScalars.contains(where: { $0.value < 32 || $0.value == 127 })
}
private func validOrigin(_ s: String) -> Bool {
    guard s.range(of:#"^https://[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?$"#,options:.regularExpression) != nil,
          let c=URLComponents(string:s), c.scheme == "https", c.host != nil, c.user == nil, c.password == nil,
          c.path.isEmpty, c.query == nil, c.fragment == nil, c.port.map({(1...65535).contains($0)}) ?? true else { return false }
    guard let host=c.host,host != "localhost",!host.hasSuffix(".localhost"),host.contains(where: { $0.isLetter }) else { return false }
    return true
}
private func bytes(_ fields: [Data]) -> Data {
    var out=Data()
    for field in fields { var n=UInt32(field.count).bigEndian;withUnsafeBytes(of:&n) { out.append(contentsOf:$0) };out.append(field) }
    return out
}
private func transcript(_ c: EnrollmentChallenge, _ r: EnrollmentResponse) -> Data {
    bytes([Data("atlas-enrollment-v1".utf8),Data(c.hostID.uuidString.lowercased().utf8),Data(c.origin.utf8),Data(c.macName.utf8),c.nonce,c.macEphemeral,c.macSigningPublic,Data(r.phoneName.utf8),r.nonce,r.phoneEphemeral])
}
func enrollmentBinding(_ c: EnrollmentChallenge, _ r: EnrollmentResponse) -> Data { Data(SHA256.hash(data:transcript(c,r))) }
func signingFingerprint(_ key: Data) throws -> String {
    guard (try? P256.Signing.PublicKey(x963Representation:key)) != nil else { throw EnrollmentError.invalid }
    return SHA256.hash(data:key).map { String(format:"%02x",$0) }.joined()
}
private func derive(_ secret: SharedSecret, _ c: EnrollmentChallenge, _ r: EnrollmentResponse) -> SymmetricKey {
    let digest=Data(SHA256.hash(data:transcript(c,r)))
    return secret.hkdfDerivedSymmetricKey(using:SHA256.self,salt:digest,sharedInfo:Data("atlas-pair-channel-v1".utf8),outputByteCount:32)
}
private func comparison(_ key: SymmetricKey, _ c: EnrollmentChallenge, _ r: EnrollmentResponse) -> String {
    let tag=HMAC<SHA256>.authenticationCode(for:bytes([Data("compare".utf8),transcript(c,r)]),using:key)
    // 30 bits, shown identically on both devices; compare the full code.
    let b=Array(tag);let value=(UInt32(b[0])<<24 | UInt32(b[1])<<16 | UInt32(b[2])<<8 | UInt32(b[3])) & 0x3fffffff
    return String(format:"%010u",value)
}
private func randomBytes(_ count: Int) throws -> Data {
    var data=Data(count:count)
    let result=data.withUnsafeMutableBytes { SecRandomCopyBytes(kSecRandomDefault,count,$0.baseAddress!) }
    guard result == errSecSuccess else { throw EnrollmentError.entropy };return data
}

/// Host methods are native-only. `approve` must be called from a real Mac
/// confirmation after the owner compares the code displayed on both devices.
final class EnrollmentHost {
    private let lock=NSLock(), clock: () -> Double
    private let key=P256.KeyAgreement.PrivateKey()
    private let deadline: Double
    let challenge: EnrollmentChallenge
    private var state=0 // offered -> awaiting owner -> approved, or consumed
    private var channel: SymmetricKey?, response: EnrollmentResponse?, code: String?
    init(hostID: UUID, macSigningPublic: Data, origin: String, macName: String, clock: @escaping () -> Double, lifetime: Double = 120) throws {
        guard (try? signingFingerprint(macSigningPublic)) != nil,validOrigin(origin),validName(macName),lifetime > 0,lifetime <= 120,clock().isFinite else { throw EnrollmentError.invalid }
        self.clock=clock;deadline=clock()+lifetime
        challenge=EnrollmentChallenge(version:1,hostID:hostID,origin:origin,macName:macName,nonce:try randomBytes(32),macEphemeral:key.publicKey.x963Representation,macSigningPublic:macSigningPublic)
    }
    func accept(_ value: EnrollmentResponse) throws -> EnrollmentComparison {
        lock.lock();defer{lock.unlock()}
        guard state==0 else { throw EnrollmentError.replay }
        guard clock() < deadline else { state=3;throw EnrollmentError.expired }
        guard value.nonce==challenge.nonce,validName(value.phoneName),value.phoneEphemeral.count==65,
              let peer=try? P256.KeyAgreement.PublicKey(x963Representation:value.phoneEphemeral),
              let shared=try? key.sharedSecretFromKeyAgreement(with:peer) else { throw EnrollmentError.invalid }
        let secret=derive(shared,challenge,value);let display=comparison(secret,challenge,value)
        channel=secret;response=value;code=display;state=1
        return EnrollmentComparison(phoneName:value.phoneName,code:display)
    }
    /// Approval consumes the challenge. No persistent key is generated here.
    func approve(displayedCode: String, displayedMacFingerprint: String, ownerConfirmed: Bool) throws -> ApprovedEnrollment {
        lock.lock();defer{lock.unlock()}
        guard state==1 else { throw EnrollmentError.badState }
        defer { state=3;channel=nil;response=nil;code=nil }
        guard clock() < deadline else { throw EnrollmentError.expired }
        guard ownerConfirmed,let expected=code,displayedCode==expected,displayedMacFingerprint == (try? signingFingerprint(challenge.macSigningPublic)),let secret=channel,let response=response else { throw EnrollmentError.denied }
        return ApprovedEnrollment(channel:secret,binding:enrollmentBinding(challenge,response),hostID:challenge.hostID,macSigningPublic:challenge.macSigningPublic,phoneName:response.phoneName,deadline:deadline)
    }
    func cancel() { lock.lock();state=3;channel=nil;response=nil;code=nil;lock.unlock() }
}

struct EnrollmentPhone {
    let response: EnrollmentResponse
    let code: String
    let channel: SymmetricKey
    // The origin must come from a separately owner-approved selection or
    // manual entry, never from the scanned QR alone. This object does no I/O.
    init(challenge: EnrollmentChallenge,expectedOrigin: String,expectedMacFingerprint:String,phoneName: String) throws {
        guard challenge.version==1,challenge.origin==expectedOrigin,validOrigin(expectedOrigin),expectedMacFingerprint == (try? signingFingerprint(challenge.macSigningPublic)),validName(challenge.macName),validName(phoneName),challenge.nonce.count==32,challenge.macEphemeral.count==65,
              let peer=try? P256.KeyAgreement.PublicKey(x963Representation:challenge.macEphemeral) else { throw EnrollmentError.invalid }
        let key=P256.KeyAgreement.PrivateKey()
        let shared=try key.sharedSecretFromKeyAgreement(with:peer)
        let value=EnrollmentResponse(phoneName:phoneName,nonce:challenge.nonce,phoneEphemeral:key.publicKey.x963Representation)
        let secret=derive(shared,challenge,value)
        response=value;channel=secret;code=comparison(secret,challenge,value)
    }
}
