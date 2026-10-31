import Cocoa
import CryptoKit

// Native UI/coordinator only. Creating this object does not open a listener or
// alter network settings. Call after the local owner explicitly approves setup.
private final class ChallengeCopyButton:NSButton {
    var onPress:(()->Void)?
    init() {super.init(frame:.zero);title="Copy pairing challenge";target=self;action=#selector(pressed)}
    required init?(coder:NSCoder){nil}
    @objc private func pressed(){onPress?()}
}
private struct CompanionIdentity:Codable {let hostID:UUID;let privateKey:Data}
final class NativeCompanionOwner {
    let handler:PairingHTTPHandler
    private let bridge:NativeCompanionTransport,nativeOwner:RemoteNativeOwner,scope:RemoteNativeOwner.Scope,clock:()->Double,onStopping:()->Void,onStop:()->Void
    private weak var window:NSWindow?
    private weak var copyChallengeButton:ChallengeCopyButton?
    private var timer:Timer?,sheet:NSAlert?,recoveryPhoneID:UUID?,recoveryDeadline:Double?,seen=Set<UUID>(),closed=false,enrollmentDismissedForComparison=false,approvedEnrollment=false,sessionOffered=false,uncertainShown=false
    init(window:NSWindow,nativeOwner:RemoteNativeOwner,scope:RemoteNativeOwner.Scope,origin:String,identityStore:SecureDeviceStorage,vaultStore:SecureDeviceStorage,journalStore:SecureDeviceStorage,bridge:NativeCompanionTransport,clock:@escaping ()->Double,ownerConfigured:Bool,onStopping:@escaping ()->Void,onStop:@escaping ()->Void)throws {
        guard ownerConfigured,Set([identityStore.storageIdentifier,vaultStore.storageIdentifier,journalStore.storageIdentifier]).count==3 else {throw DeviceError.denied}
        let identity:CompanionIdentity
        if let data=try identityStore.read() {identity=try JSONDecoder().decode(CompanionIdentity.self,from:data)}
        else {
            // A missing identity alongside any persisted state is not a new
            // installation: never silently orphan the previous paired devices.
            guard try vaultStore.read()==nil,try journalStore.read()==nil else {throw DeviceError.invalid}
            identity=CompanionIdentity(hostID:UUID(),privateKey:P256.Signing.PrivateKey().rawRepresentation)
            let data=try JSONEncoder().encode(identity);try identityStore.write(data)
            guard try identityStore.read()==data else {throw DeviceError.invalid}
        }
        let macKey=try P256.Signing.PrivateKey(rawRepresentation:identity.privateKey)
        guard let parts=URLComponents(string:origin),let host=parts.host else {throw EnrollmentError.invalid}
        self.window=window;self.nativeOwner=nativeOwner;self.scope=scope;self.clock=clock;self.bridge=bridge;self.onStopping=onStopping;self.onStop=onStop
        handler=try PairingHTTPHandler(hostID:identity.hostID,macKey:macKey,expectedHost:host+(parts.port.map{":"+String($0)} ?? ""),expectedOrigin:"https://atlas-desktop.joelr2.chatgpt.site",privateOrigin:origin,macName:Host.current().localizedName ?? "Mac",storage:vaultStore,journalStorage:journalStore,clock:clock,wallClock:{Int64(Date().timeIntervalSince1970)},ownerStarted:true,routeFactory:{h,host,origin,peer,scope,deadline,clock,wall in RegistryRoutes(hostID:h,expectedHost:host,expectedOrigin:origin,peer:peer,scope:scope,sessionDeadline:deadline,clock:clock,wallClock:wall,transport:bridge)},recoveryCheck:{bridge.recoveryClear()},ownerConfirm:{_ in false})
    }
    // UI entry points must only be called from native controls, never WebKit.
    func begin() {
        guard !closed,let phones=try? handler.ownerPhones() else {stop();return}
        if phones.isEmpty {try? showEnrollment()}
        else {reviewRestart {[weak self] ok in if ok {self?.choosePhone()} else {self?.stop()}}}
    }
    private func choosePhone() {
        guard !closed,let window,let phones=try? handler.ownerPhones() else {stop();return}
        let active=phones.filter{!$0.revoked};guard !active.isEmpty else {try? showEnrollment();return}
        let alert=NSAlert();alert.messageText="Paired phones";alert.informativeText="Choose a phone, or link a new one. A session still needs project and task approval."
        let menu=NSPopUpButton(frame:NSRect(x:0,y:0,width:380,height:26));for phone in active {menu.addItem(withTitle:phone.name+" · "+phone.id.uuidString)};alert.accessoryView=menu
        alert.addButton(withTitle:"Use selected");alert.addButton(withTitle:"Link new phone");alert.addButton(withTitle:"Revoke selected");alert.addButton(withTitle:"Recover pairing");alert.addButton(withTitle:"Cancel")
        alert.beginSheetModal(for:window) {[weak self] result in
            guard let self,!self.closed else{return};let index=menu.indexOfSelectedItem;guard active.indices.contains(index) else {self.stop();return}
            let phone=active[index]
            if result == .alertFirstButtonReturn {self.approveSession(phone:phone.id) {_ in}}
            else if result == .alertSecondButtonReturn {try? self.showEnrollment()}
            else if result == .alertThirdButtonReturn {
                do {try self.handler.ownerPrepareRevocation(phone.id)} catch {self.stop();return}
                let confirm=NSAlert();confirm.messageText="Revoke this phone?";confirm.informativeText=phone.name+" will need to be paired again.";confirm.addButton(withTitle:"Revoke");confirm.addButton(withTitle:"Cancel")
                confirm.beginSheetModal(for:window) {answer in
                    guard !self.closed else{return}
                    do {if answer == .alertFirstButtonReturn {try self.handler.ownerRevoke(expectedGeneration:phone.generation,confirmed:true)} else {try self.handler.ownerCancelPreparedRevocation()}} catch {self.stop();return};self.choosePhone()
                }
            } else if result.rawValue == NSApplication.ModalResponse.alertFirstButtonReturn.rawValue+3 {self.reviewPairingRecovery(phone)}
            else {self.stop()}
        }
    }
    private func reviewPairingRecovery(_ phone:PairedPhone) {
        guard !closed,let window,let descriptor=try? handler.ownerRecoveryDescriptor(phone.id) else {stop();return}
        let alert=NSAlert();alert.messageText="Review uncertain pairing";alert.informativeText="Phone: \(descriptor.phoneName)\nPhone ID: \(descriptor.phoneID.uuidString)\nPhone fingerprint: \((try? signingFingerprint(descriptor.phonePublic)) ?? "unavailable")\nMac fingerprint: \((try? signingFingerprint(descriptor.macPublic)) ?? "unavailable")\n\nThe previous pairing receipt may not have reached the phone. Compare these details on the phone. ATLAS will issue a one-use challenge; the phone must prove its key. No task or pairing will be automatically resent."
        alert.addButton(withTitle:"Details match; recover");alert.addButton(withTitle:"Cancel")
        alert.beginSheetModal(for:window) {[weak self] response in
            guard let self,!self.closed,response == .alertFirstButtonReturn else {self?.stop();return}
            let started=self.clock()
            DispatchQueue.global().async {
                let ok=(try? self.handler.ownerPrepareRecovery(descriptor,confirmed:true)) != nil
                DispatchQueue.main.async {
                    guard ok,!self.closed else {self.stop();return};self.approvedEnrollment=true;self.sessionOffered=false;self.recoveryPhoneID=descriptor.phoneID;self.recoveryDeadline=started+30
                    let waiting=NSAlert();waiting.messageText="Waiting for phone proof";waiting.informativeText="Continue recovery on the selected phone within 30 seconds. If the result is uncertain, review it again here; ATLAS will not resend it automatically.";waiting.addButton(withTitle:"Cancel");self.sheet=waiting
                    waiting.beginSheetModal(for:window) {[weak self] _ in guard let self,!self.sessionOffered else{return};self.stop()}
                    self.timer=Timer.scheduledTimer(withTimeInterval:0.2,repeats:true) {[weak self] _ in self?.pollComparison()}
                }
            }
        }
    }
    func showEnrollment() throws {
        guard !closed,let window else {throw DeviceError.denied}
        let image=try enrollmentQR(handler.challenge),alert=NSAlert();alert.messageText="Pair ATLAS on your phone"
        alert.informativeText="Scan this challenge or copy it into the ATLAS phone companion. It is single-use and expires after two minutes. Compare the code and Mac fingerprint before approving. ATLAS does not configure a network route."
        let panel=NSView(frame:NSRect(x:0,y:0,width:260,height:282)),imageView=NSImageView(frame:NSRect(x:10,y:42,width:240,height:240))
        imageView.image=NSImage(cgImage:image,size:NSSize(width:240,height:240));panel.addSubview(imageView)
        let button=ChallengeCopyButton();button.frame=NSRect(x:35,y:4,width:190,height:30);button.isEnabled=handler.ownerCanCopyChallenge()
        button.onPress={[weak self] in
            guard let self,!self.closed else{return}
            _=copyEnrollmentChallenge(self.handler.challenge,allowed:{self.handler.ownerCanCopyChallenge()},write:{text in
                let board=NSPasteboard.general;board.clearContents();return board.setString(text,forType:.string)
            })
        }
        copyChallengeButton=button;panel.addSubview(button);alert.accessoryView=panel;alert.addButton(withTitle:"Close")
        sheet=alert;alert.beginSheetModal(for:window) {[weak self] _ in guard let self,!self.enrollmentDismissedForComparison else{return};self.stop()}
        timer=Timer.scheduledTimer(withTimeInterval:0.2,repeats:true) {[weak self] _ in self?.pollComparison()}
    }
    private func pollComparison() {
        guard !closed,let window else {return}
        copyChallengeButton?.isEnabled=handler.ownerCanCopyChallenge()
        if let deadline=recoveryDeadline,clock()>=deadline,!sessionOffered {stop();return}
        if handler.ownerPairingUncertain(),!uncertainShown {
            uncertainShown=true;timer?.invalidate();timer=nil
            reviewRestart {[weak self] ok in
                guard let self,ok else {self?.stop();return}
                guard let phones=try? self.handler.ownerPhones(),!phones.isEmpty else {let notice=NSAlert();notice.messageText="Pairing outcome unknown";notice.informativeText="No recoverable pairing record was found on this Mac. Restart companion setup and inspect the phone before pairing again.";notice.runModal();self.stop();return}
                self.choosePhone()
            };return
        }
        if approvedEnrollment,!sessionOffered,let id=handler.ownerCurrentPhone(),(recoveryPhoneID == nil || (recoveryPhoneID == id && handler.ownerRecoveryCompleted() == id)),let phone=(try? handler.ownerPhones())?.first(where:{$0.id==id && !$0.revoked}) {
            sessionOffered=true;timer?.invalidate();timer=nil
            if let waiting=sheet,waiting.window.sheetParent != nil {sheet=nil;window.endSheet(waiting.window)}
            if recoveryPhoneID != nil {
                let notice=NSAlert();notice.messageText="Recovery receipt issued";notice.informativeText="The Mac sent a signed receipt, but it cannot tell whether the phone received or saved it. Check the phone. If it reports an unknown result, choose Recover pairing again; nothing will be resent automatically."
                notice.addButton(withTitle:"Phone confirms recovery");notice.addButton(withTitle:"Close")
                notice.beginSheetModal(for:window) {[weak self] answer in guard let self,!self.closed,answer == .alertFirstButtonReturn else {self?.stop();return};self.approveSession(phone:phone.id) {_ in}}
            } else {approveSession(phone:phone.id) {_ in}}
            return
        }
        guard let (id,comparison)=handler.ownerComparison(),!seen.contains(id) else {return}
        seen.insert(id);enrollmentDismissedForComparison=true;if let alert=sheet,alert.window.sheetParent != nil {window.endSheet(alert.window);sheet=nil}
        let alert=NSAlert();alert.messageText="Confirm this phone";alert.informativeText="Phone: \(comparison.phoneName)\nComparison code: \(comparison.code)\nMac fingerprint: \((try? signingFingerprint(handler.challenge.macSigningPublic)) ?? "unavailable")\n\nApprove only if the phone shows the same code and Mac fingerprint."
        alert.addButton(withTitle:"Codes match; pair");alert.addButton(withTitle:"Deny");sheet=alert
        alert.beginSheetModal(for:window) {[weak self] result in
            guard let self,!self.closed else{return};self.sheet=nil
            do {try self.handler.ownerApprove(attemptID:id,code:comparison.code,fingerprint:signingFingerprint(self.handler.challenge.macSigningPublic),confirmed:result == .alertFirstButtonReturn);self.approvedEnrollment=true}
            catch {self.stop()}
        }
    }
    func reviewRestart(completion:@escaping (Bool)->Void) {
        guard !closed,let window else {completion(false);return}
        let alert=NSAlert();alert.messageText="Review previous companion activity";alert.informativeText="Inspect the previous remote task and Agents history first. An interrupted session conservatively revokes its phone. You must pair it again."
        alert.addButton(withTitle:"I inspected the outcome");alert.addButton(withTitle:"Cancel")
        alert.beginSheetModal(for:window) {[weak self] result in
            guard let self,!self.closed,result == .alertFirstButtonReturn else {completion(false);return}
            DispatchQueue.global().async {let ok=(try? self.handler.ownerReviewRestart(confirmed:true,taskOutcomeReviewed:true)) != nil;DispatchQueue.main.async {completion(ok)}}
        }
    }
    func approveSession(phone:UUID,completion:@escaping (Bool)->Void) {
        guard !closed,let window,let record=try? handler.ownerPhones().first(where:{$0.id==phone && !$0.revoked}) else {completion(false);return}
        let alert=NSAlert();alert.messageText="Allow a companion session?";alert.informativeText="Phone: \(record.name)\nProject: \(scope.folder)\nScope: \(scope.id) / \(scope.revision)\nExpires: \(Date(timeIntervalSinceNow:max(0,scope.expires-clock())).formatted(date:.abbreviated,time:.standard))\n\nEach task still requires approval on this Mac."
        alert.addButton(withTitle:"Allow session");alert.addButton(withTitle:"Cancel")
        alert.beginSheetModal(for:window) {[weak self] answer in
            guard let self,!self.closed,answer == .alertFirstButtonReturn else {completion(false);return}
            do {
                try self.handler.ownerSelectPhone(phone,confirmed:true)
                let device:[String:Any] = ["id":phone.uuidString.lowercased(),"name":record.name,"generation":Int(record.generation),"fingerprint":try signingFingerprint(record.publicKey),"macFingerprint":try signingFingerprint(self.handler.challenge.macSigningPublic),"macName":self.handler.challenge.macName]
                guard self.nativeOwner.bindCompanionDevice(device) else {self.stop();completion(false);return}
                DispatchQueue.global().async {
                    let bound=self.bridge.bindDevice(device,id:phone)
                    DispatchQueue.main.async {
                        guard bound,!self.closed,self.clock()<self.scope.expires else {self.stop();completion(false);return}
                        do {try self.handler.ownerStartSession(scope:(self.scope.id,self.scope.revision),deadline:self.scope.expires,confirmed:true);completion(true)} catch {self.stop();completion(false)}
                    }
                }
            } catch {self.stop();completion(false)}
        }
    }
    func stop(completion:@escaping ()->Void = {}) {
        guard !closed else {completion();return};closed=true;timer?.invalidate();timer=nil
        if let alert=sheet,let window=alert.window.sheetParent {window.endSheet(alert.window,returnCode:.cancel)};sheet=nil
        onStopping()
        let handler=self.handler,bridge=self.bridge,onStop=self.onStop
        DispatchQueue.global().async {handler.ownerCancelRecovery();handler.ownerEndSession();bridge.close();completion();onStop()}
    }
    deinit {stop()}
}
