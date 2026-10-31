# Request evidence encryption: disabled development adapter

`request_evidence_store.py` and `RequestCrypto.swift` are an isolated candidate,
not connected to any app writer or reader. Existing request files and behavior
are unchanged. The helper uses CryptoKit AES-256-GCM with a fresh system nonce,
binds ciphertext to the agent record ID as authenticated associated data, and
receives a supplied key over a private subprocess pipe. It does not access
Keychain, environment credentials, or a network. The adapter requires a
caller-supplied 32-byte key provider; it creates no key or new database.

Legacy migration requires explicit confirmation and the displayed revision.
It reads the key twice, authenticates and verifies the new ciphertext, creates
a separate mode-0600 **plaintext legacy backup**, and checks for changed
evidence before atomically replacing the existing file. It refuses symlinks,
hard-linked files, and special files. A canceled or stale migration does not
obtain a key. Edits authenticate the existing record, save its preceding
ciphertext in a separate edit backup, and use a revision check. A second edit
is refused while that backup exists; no backup-discard UI exists yet. Restore
requires confirmation and displayed revisions of both files, preserves the
displaced ciphertext, and refuses an existing recovery backup. Backups are never
deleted automatically. If backup creation or rename fails, a partial or complete
backup can remain and blocks retries; manual reviewed repair is not yet wired.
An authenticated in-memory preview of a sealed backup exists, but its Python
boolean is not an authority boundary: only a future verified native owner action
may call it, and the preview must never be logged or sent to a model.
If rename succeeds
but directory synchronization fails, the caller receives an unknown-durability
error and must inspect the file before retrying.

## Required before any owner-data migration

1. Independently review this adapter, the helper, and the native authorization
   boundary. A Python `confirmed=True` argument alone is not owner authority.
2. Coordinate **every** legacy request reader and writer with the same lock;
   otherwise an uncooperative writer can race the last revision check. Integrate
   all helper and resume paths without treating generated briefs as owner words.
   The current application is not coordinated and must not enable the adapter.
3. Provide a native preview of exact scope and recovery consequences, and ask
   for action-time owner approval to create a **new, separate, device-only
   Keychain item for request-evidence encryption**. Do not read, transfer, or
   reuse provider API keys. Native Keychain authorization may also be required.
4. Define key-loss recovery, authenticated backups, migration interruption and
   rollback, and an explicit policy for the plaintext legacy backup. Two
   successful key reads cannot establish that a key will remain available after
   restart. The retained backup enables explicit restore, but remains plaintext
   until separately handled with owner consent. This adapter
   does not securely erase plaintext blocks or copies in state, logs, backups,
   swap, or provider sessions. Losing the key can make sealed evidence unreadable.
5. Complete real CryptoKit round-trip/tamper tests in an approved VM. On this
   host the helper compiled, but the native host guard skipped execution. The
   synthetic test double verifies storage state transitions, not cryptography.

Until those gates pass, do not package or activate this adapter in a released
app and do not mark plaintext-storage alerts fixed. No owner keys have been
created or accessed during this work.
