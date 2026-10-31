import AppKit

// This window is opened only by the owner's existing Check updates action.
// Release notes are plain text. Web content/model tools cannot press Install.
@MainActor final class SignedUpdateWindow:NSObject,NSWindowDelegate {
    static let shared=SignedUpdateWindow()
    let model=SignedUpdateCoordinator()
    private var window:NSWindow?
    private let status=NSTextField(wrappingLabelWithString:"")
    private let notes=NSTextView()
    private let channel=NSButton(checkboxWithTitle:"Include prerelease builds",target:nil,action:nil)
    private let checkButton=NSButton(title:"Check updates",target:nil,action:nil)
    private let downloadButton=NSButton(title:"Download",target:nil,action:nil)
    private let installButton=NSButton(title:"Install and restart…",target:nil,action:nil)
    private let recoveryButton=NSButton(title:"Inspect previous updates…",target:nil,action:nil)
    private let cancelButton=NSButton(title:"Cancel",target:nil,action:nil)
    private var restoring=false
    private var restoreTask:Task<Void,Never>?
    var isIdle:()->Bool = {false}
    // Supplied by the native app integration. It is never a WebKit callback.
    var install:((PreparedSignedUpdate)async throws->Void)?
    func show(){
        if window==nil {
            let w=NSWindow(contentRect:NSRect(x:0,y:0,width:580,height:420),styleMask:[.titled,.closable],backing:.buffered,defer:false)
            w.title="ATLAS updates";w.isReleasedWhenClosed=false;w.delegate=self;w.center();window=w
            let stack=NSStackView();stack.orientation = .vertical;stack.alignment = .leading;stack.spacing=14;stack.translatesAutoresizingMaskIntoConstraints=false
            w.contentView!.addSubview(stack)
            NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo:w.contentView!.leadingAnchor,constant:20),stack.trailingAnchor.constraint(equalTo:w.contentView!.trailingAnchor,constant:-20),stack.topAnchor.constraint(equalTo:w.contentView!.topAnchor,constant:20),stack.bottomAnchor.constraint(equalTo:w.contentView!.bottomAnchor,constant:-20)])
            stack.addArrangedSubview(NSTextField(labelWithString:"Signed application updates"));stack.addArrangedSubview(status);stack.addArrangedSubview(channel)
            let scroll=NSScrollView();scroll.hasVerticalScroller=true;notes.isEditable=false;notes.isRichText=false;notes.font = .systemFont(ofSize:13);scroll.documentView=notes
            stack.addArrangedSubview(scroll);scroll.widthAnchor.constraint(equalTo:stack.widthAnchor).isActive=true;scroll.heightAnchor.constraint(greaterThanOrEqualToConstant:180).isActive=true
            let row=NSStackView(views:[checkButton,downloadButton,installButton,cancelButton]);row.spacing=10;stack.addArrangedSubview(row);stack.addArrangedSubview(recoveryButton)
            recoveryButton.target=self;recoveryButton.action=#selector(inspectRecovery)
            checkButton.target=self;checkButton.action=#selector(check)
            downloadButton.target=self;downloadButton.action=#selector(download)
            installButton.target=self;installButton.action=#selector(confirmInstall)
            cancelButton.target=self;cancelButton.action=#selector(cancel)
            model.changed={[weak self] in self?.refresh()}
        }
        refresh();window?.makeKeyAndOrderFront(nil);NSApp.activate(ignoringOtherApps:true)
    }
    func windowWillClose(_ notification:Notification){restoreTask?.cancel();model.cancel()}
    private func refresh(){status.stringValue=model.message;notes.string=model.release?.changelog ?? "No verified release loaded. Your current installation remains unchanged."
        recoveryButton.isEnabled = !model.busy && !restoring
        checkButton.isEnabled = !model.busy && !restoring;channel.isEnabled = !model.busy && !restoring
        downloadButton.isEnabled=model.phase == .available && !restoring
        installButton.isEnabled=model.phase == .prepared && install != nil && !restoring
        cancelButton.title=model.phase == .prepared ? "Discard download" : "Cancel"
        cancelButton.isEnabled=(model.busy && model.phase != .installing) || model.phase == .prepared
    }
    private func stateDirectory()throws->URL {
        let raw=FileManager.default.urls(for:.applicationSupportDirectory,in:.userDomainMask).first!
        guard let path=realpath(raw.path,nil) else{throw SignedUpdateError.rejected("Application Support is unavailable.")}
        defer{free(path)}
        let parent=URL(fileURLWithPath:String(cString:path))
        let root=parent.appendingPathComponent("ATLAS Updates",isDirectory:true)
        return try UpdateReceiptStore(directory:root).directory
    }
    @objc private func check(){
        // With no embedded key, the model returns before filesystem/network I/O.
        if !UpdatePublisherTrust.configured {
            model.check(includePrereleases:channel.state == .on,installed:.init(version:"v0.0",build:0,epoch:0),machine:"arm64",macOS:"0.0",receipt:.init(highestSequence:0,lastTrustedTime:Date(timeIntervalSince1970:0)));return
        }
        do {
            let b=Bundle.main,os=ProcessInfo.processInfo.operatingSystemVersion
            guard let version=b.object(forInfoDictionaryKey:"CFBundleShortVersionString") as? String,let buildText=b.object(forInfoDictionaryKey:"CFBundleVersion") as? String,let build=Int(buildText),let epoch=b.object(forInfoDictionaryKey:"ATLASUpdateEpoch") as? Int else{throw SignedUpdateError.rejected("Installed app version metadata is incomplete.")}
            #if arch(arm64)
            let machine="arm64"
            #else
            let machine="x86_64"
            #endif
            model.check(includePrereleases:channel.state == .on,installed:.init(version:"v"+version,build:build,epoch:epoch),machine:machine,macOS:"\(os.majorVersion).\(os.minorVersion).\(os.patchVersion)",receipt:try UpdateReceiptStore(directory:stateDirectory()).read())
        }catch{alert(SignedUpdateCoordinator.safeMessage(error))}
    }
    @objc private func download(){
        guard let resource=Bundle.main.resourceURL else{return}
        guard let parent=try? UpdateInstallerIO.canonicalPath(Bundle.main.bundleURL.deletingLastPathComponent().path) else{alert("The app installation path needs inspection.");return}
        model.download(installationParent:URL(fileURLWithPath:parent),extractor:resource.appendingPathComponent("Updater/extract_update.py"))
    }
    @objc private func inspectRecovery(){
        do {
            let state=try stateDirectory(),directory=state.appendingPathComponent("transactions",isDirectory:true)
            guard FileManager.default.fileExists(atPath:directory.path) else{alert("No update transactions have been recorded.");return}
            let target=URL(fileURLWithPath:try UpdateInstallerIO.canonicalPath(Bundle.main.bundleURL.path))
            let store=try UpdateTransactionStore(installationParent:target.deletingLastPathComponent(),stateDirectory:directory,verifyBundle:{try UpdateBundleValidation.verify($0)})
            let records=try store.recover().filter{$0.record.target==target.lastPathComponent}.sorted{$0.record.order.sequence>$1.record.order.sequence}
            guard !records.isEmpty else{alert("No update transactions for this copy of ATLAS.");return}
            let summary=records.prefix(20).map{"\($0.record.order.version), build \($0.record.order.build): \($0.disposition) [\($0.record.id)]"}.joined(separator:"\n")
            let pending=records.first{$0.disposition=="prepared"}
            let a=NSAlert();a.messageText="Previous ATLAS updates";a.informativeText=summary+"\n\nUncertain swaps are never retried automatically. A retained backup can be inspected before manual restoration while ATLAS is quit."
            a.addButton(withTitle:"Close")
            if let pending {
                a.addButton(withTitle:"Discard unstarted update…")
                if a.runModal() == .alertSecondButtonReturn {
                    let confirmation=NSAlert();confirmation.messageText="Discard this unstarted update?";confirmation.informativeText="\(pending.record.order.version), build \(pending.record.order.build)\nTransaction: \(pending.record.id)\nApp: \(target.lastPathComponent)\n\nThe installed app stays unchanged. The candidate stays on disk for inspection."
                    confirmation.addButton(withTitle:"Cancel");confirmation.addButton(withTitle:"Discard pending update")
                    if confirmation.runModal() == .alertSecondButtonReturn {_=try store.cancelPrepared(id:pending.record.id);alert("Unstarted update discarded. The installed app was not replaced.")}
                }
            }else if let restore=records.first(where:{$0.disposition=="launched" || $0.disposition=="activeNeedsLaunchConfirmation"}),UpdatePublisherTrust.configured {
                a.addButton(withTitle:"Restore saved local backup…")
                if a.runModal() == .alertSecondButtonReturn {confirmRestore(restore.record,target:target,state:state)}
            }else{a.runModal()}
        }catch{alert("Update recovery needs inspection. No app was replaced or automatically restored.")}
    }
    private func confirmRestore(_ record:UpdateTransactionRecord,target:URL,state:URL){
        guard !restoring,isIdle() else{alert("Finish active work before restoring a backup.");return}
        let a=NSAlert();a.messageText="Restore saved local backup and restart?"
        a.informativeText="Current build: \(record.new.build)\nSaved build: \(record.old.build)\nSaved bundle digest: \(record.old.digest)\nTransaction: \(record.id)\n\nThis restores the exact previously installed local app, checked against its private journal and code signature. It is not a publisher-signed rollback release. Your settings, files, runtime and Keychain remain outside the transaction."
        a.addButton(withTitle:"Cancel");a.addButton(withTitle:"Restore local backup")
        guard a.runModal() == .alertSecondButtonReturn,isIdle() else{return}
        restoring=true;refresh()
        restoreTask=Task {
            defer{restoring=false;restoreTask=nil;refresh()}
            do {
                let process=try await Task.detached{try UpdateInstallerLauncher.startRollback(transactionID:record.id,expectedBackup:record.old,target:target,stateDirectory:state,parentPID:getpid())}.value
                guard !Task.isCancelled,isIdle() else{if process.isRunning{process.terminate()};throw SignedUpdateError.rejected("Restore cancelled before ATLAS quit. Inspect the transaction before retrying.")}
                NSApplication.shared.terminate(nil)
            }catch{alert(SignedUpdateCoordinator.safeMessage(error))}
        }
    }
    @objc private func cancel(){model.cancel()}
    @objc private func confirmInstall(){
        guard isIdle(),let install,let prepared=model.prepared else{alert("Finish or cancel active work before installing an update.");return}
        let a=NSAlert();a.messageText="Install \(prepared.release.version) and restart ATLAS?";a.informativeText="Only this ATLAS app bundle will be replaced. The previous app will be kept as a backup. Settings, runtime, personal files and Keychain are not part of the update."
        a.addButton(withTitle:"Cancel");a.addButton(withTitle:"Install and restart")
        guard a.runModal() == .alertSecondButtonReturn,isIdle() else{return}
        Task {do{try await model.beginInstall(install)}catch{alert(SignedUpdateCoordinator.safeMessage(error))}}
    }
    private func alert(_ message:String){let a=NSAlert();a.messageText="ATLAS update";a.informativeText=message;a.addButton(withTitle:"OK");a.runModal()}
}
