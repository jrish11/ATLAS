# Installation, migration and rollback

Back up only the previous customized app bundle, quit it, and place the reviewed update in its previous folder. Do not overwrite official Atticus or an unrelated older ATLAS prototype. Never run old and new copies together. Existing customized namespace remains `com.atticus.personal.dev`, internal executable `Atticus`, profile `~/.config/atticus-personal-dev`, external runtime `~/Library/Application Support/Atticus Dev/pi-runtime`, and Keychain service `com.atticus.personal.dev.provider`. The source is renamed ATLAS for display while these stable identifiers preserve local data.

Do not delete profile/runtime/vault/Keychain data to update. No credential/session transfer is supported. Review exact macOS permission and Keychain prompts yourself; ad-hoc signatures can require another review. Do not disable security controls or remove quarantine. Microphone/Accessibility/Automation permissions apply only to implemented functionality.

Wake migration changes only a missing or exact legacy Atticus name to Atlas; other phrases and the listening switch are preserved. Memory migrations and corrections use existing records and recovery controls; never import a private profile automatically. The public release contains none.

Rollback: quit the update and restore the backed-up customized app bundle. Leave local data intact. App rollback does not undo file/model/browser actions, separately confirmed profile imports or memory changes. Inspect changes and use their audited undo/backup controls. Unknown task outcomes require review; restarting must not redispatch them.
