# Native pairing-recovery contract (review candidate)

This is a disabled development candidate, not an enabled service. Transport
remains the exact owner-approved private HTTPS origin; Origin must be exactly
`https://atlas-desktop.joelr2.chatgpt.site`, Host must match the private origin,
requests are POST JSON without cookies or authorization headers. PNA preflight
continues to fail closed. Never send an automatic retry after an unknown result.

If `/v1/enrollment/ack` returns 409 `{"error":"outcome-unknown"}` or its
response is lost, preserve the pending non-extractable phone key, host/phone
IDs, expected Mac public key, and enrollment binding. Display “Pairing outcome
unknown; review it on the Mac.” Never silently call ack, finish, join, or a
recovery endpoint again. The Mac owner first inspects the saved record, confirms
the exact phone name, phone ID, phone fingerprint and Mac fingerprint in the
native sheet, and approves a one-use 30-second recovery challenge. Local task
receipt/barrier review must also pass.

The phone may then POST `/v1/enrollment/recovery/challenge` with exactly
`{"phoneID":"<UUID>"}`. Success is JSON:
`{"descriptor":{"hostID":"<UUID>","phoneID":"<UUID>","phoneName":"<name>","generation":1,"binding":"<base64 32 bytes>","macPublic":"<base64 P-256 X9.63 public key>","phonePublic":"<base64 P-256 X9.63 public key>"},"nonce":"<base64 32 bytes>"}`.
Verify host ID, phone ID, generation, binding, and both public keys against the
phone's retained pending record before signing. The signed message is the
concatenation of unsigned 32-bit big-endian length-prefixed fields: UTF-8
`atlas-pair-recovery-v1`, lowercase host UUID, lowercase phone UUID, decimal
generation, raw binding bytes, and raw nonce bytes. Sign with P-256 ECDSA
SHA-256 using the retained non-extractable phone private key; the signature is
64-byte IEEE-P1363 `r || s` encoded as base64.

POST `/v1/enrollment/recovery/finish` with exactly
`{"challenge":<the complete challenge object>,"signature":"<base64 signature>"}`.
The response is `{"descriptor":<the same descriptor>,"signature":"<base64>"}`.
Verify the Mac ECDSA signature against the previously pinned Mac key over the
length-prefixed fields used by `pairingReceiptMessage`: UTF-8
`atlas-pair-receipt-v1`, lowercase host UUID, lowercase phone UUID, phoneName,
decimal generation, binding bytes, Mac public bytes, phone public bytes. Only
after verification may the phone commit its local pairing record. Any rejected,
expired, invalid or replayed request returns 403. Finish consumes the challenge,
including on failed proof; recovery after a lost finish response requires a new
explicit native review and challenge, never automatic resubmission.

No recovery API accepts owner approval from HTTP. Local controls cancel pending
recovery on Stop or window close. An interrupted active session is handled by
conservative native revocation before any recovery challenge can be issued.
