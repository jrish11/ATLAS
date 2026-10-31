# ATLAS PWA companion: proposed contract v1

**Draft, not an enabled or approved API.** The existing temporary remote
prototype remains on `remote-owner-integration`; it does not provide this
contract. The public site worker should not ship a working pairing client until
both sides agree on this document and the implementation has independent
security review. This document authorizes no connection, publication, key
creation, certificate, route, or pairing.

## Origins and connectivity

The proposed canonical installable PWA origin is exactly
`https://atlas-desktop.joelr2.chatgpt.site` (no path or trailing slash in the
`Origin` header). Each Mac has a
separate owner-approved private HTTPS origin reachable only over a separately
approved private network. A static public site cannot discover or reach a Mac
that the phone cannot route to. The PWA never assumes that the Mac, phone, or a
second computer is on a tailnet, and never falls back to another computer.
Each request carries an explicitly selected Mac ID. Same-origin serving from
each private Mac would isolate browser storage per origin and does not by itself
provide a shared multi-Mac selector. A single-origin private gateway is an
alternative, but requires additional separately approved infrastructure. The
proposal here keeps the one public PWA origin and uses explicit, authenticated
cross-origin requests to each privately reachable Mac. If that route or the
browser cannot support the checks below, pairing and tasks must remain disabled.
Each request carries an explicitly selected Mac ID. Offline means unavailable;
no silent switching or queued dispatch. A signed response must bind the Mac ID
and request ID; never infer a selected target from the URL alone.

Cross-origin access is **not yet enabled**. The disabled Swift reference checks an
exact owner-approved public PWA `Origin` and exact private `Host`, answers only
required CORS preflights with that origin (never `*`), uses `Vary: Origin`, and
rejects unexpected methods, content types, duplicate fields, redirects and
oversized bodies. The browser must omit ambient credentials and cookies; the
handler sends no-store responses. CORS is not authentication. Mixed content and invalid
certificates must fail; do not bypass browser TLS warnings. Because the site and
Mac are different origins, all this must be tested in actual iPhone Safari,
including any local-network permission behavior, before deployment.
The reference parser rejects private-network preflight requests and does not
emit `Access-Control-Allow-Private-Network`. If a browser requires that grant,
the flow fails closed until the network policy is reviewed; do not bypass it.

## Enrollment and identity

1. After a local owner starts enrollment, the Mac displays a QR encoding a
   versioned JSON challenge: `version`, `hostID`, private HTTPS `origin`,
   `macName`, random 32-byte `nonce`, 65-byte uncompressed X9.63 P-256
   `macEphemeral`, and `macSigningPublic`. Data fields are standard base64 in
   JSON. An advisory expiry display field must be agreed before the wire
   contract is frozen. The Mac holds the
   matching ephemeral private key and enforces a maximum 120-second deadline
   on a continuous clock. The QR is a single-use enrollment challenge, never a
   permanent bearer URL. Manual entry of the same challenge is a fallback when
   camera capture/QR decoding is unavailable. Until a separate short-code
   protocol is reviewed, the fallback is pasting the complete challenge, not a
   weaker short secret or a permanent link.
2. The PWA supplies a phone name, the same nonce and a fresh 65-byte
   uncompressed P-256 ECDH public key. Both sides derive a channel key and
   display a matching 10-digit comparison code. The owner must compare it on
   the actual phone and Mac and locally approve that exact phone. Denial,
   expiry, window close, or replay consumes/cancels the attempt. The QR binds
   the host ID and Mac signing public key; the owner must separately approve
   any initial creation of that Mac identity before the QR is generated. No
   persistent identity is created before explicit activation.
3. Only after local owner approval and the phone user's confirmation may each
   side create its long-lived signing identity and exchange public keys over
   the authenticated encrypted enrollment channel. The phone generates a
   non-exportable WebCrypto P-256 ECDSA private key; the Mac stores its private
   identity in a device-local Keychain item. Synthetic completion messages and
   mutual key-possession proofs are described below. A test-only fsynced store
   exercises lost-ack recovery; actual Keychain crash behavior and browser
   persistence remain unverified. Do not treat a comparison code alone as a
   persisted pairing.
4. The phone's private CryptoKey is stored, if supported, by structured clone
   in same-origin IndexedDB, never as a bearer token in localStorage, URL,
   service-worker cache, or logs. Non-extractable does not prevent malicious
   same-origin JavaScript from using a key. Site compromise, XSS, compromised
   dependencies, or a malicious service worker can therefore impersonate the
   phone. Browser storage may be cleared or evicted and is not guaranteed
   permanent. Recovery requires explicit re-pairing; no silent key replacement.

The tested local Swift foundations in `companion/Shared` use P-256 ECDH,
HKDF-SHA256 and HMAC-SHA256 for the comparison code. The exact byte
serialization is length-prefixed (`UInt32` big-endian length followed by
bytes); the ordered transcript and HKDF labels are in `Enrollment.swift`.
The disabled handler opens no network listener or real Keychain, and its task
registry is synthetic. Interoperability with Safari is not yet tested.

## Persistent pairing versus action authorization

A persistent pairing identifies a phone and a Mac until revoked; it is not a
blanket task approval. A future short-lived session must be separately approved
on the selected Mac and scoped to an exact project identity and expiry. Every
task requires its own native Mac approval. The reviewed existing Agents
registry remains the only dispatcher; no raw shell endpoint, account export,
credentials export, phone-side permission escalation, or model-generated
approval is allowed.

Proposed private routes, subject to review (no routes are active yet):

- `POST /v1/enrollment/join`: challenge-bound ephemeral phone response; returns
  only pending/denied state and an opaque attempt ID. Owner approval is local.
- `POST /v1/enrollment/finish` and `/v1/enrollment/ack`: mutually authenticated
  encrypted key exchange; actual deployment and recovery UX remain unverified.
- `POST /v1/session/challenge`: after pairing, request a short-lived,
  one-use server challenge for one named action and exact target/scope.
- `POST /v1/tasks`, `/v1/tasks/status`, `/v1/tasks/stop`: a signed proof binds
  host ID, phone ID, key generation, selected scope revision, action, payload
  digest and fresh challenge. The server rechecks expiry, revocation, key
  generation and scope at dispatch. The action proof is not owner approval.

A submission with an uncertain outcome is never automatically retried. Stop is
bound to the immutable active request and cannot undo work already dispatched.
Owner revocation immediately disables the local identity; offline remote peers
must reject the old identity at their next authenticated contact. Rotation must
be explicitly approved, update the generation, and fail closed during partial
commit. Lost-phone controls and signed revocation delivery are not implemented.

## PWA constraints and handoff

- Home Screen installation is user initiated from the browser; the site worker
  owns the manifest, bold icon, install instructions, and offline shell.
- Camera QR scanning requires HTTPS, a user gesture and camera permission; use
  feature detection and provide manual challenge entry. Do not assume the
  experimental `BarcodeDetector` API exists in Safari.
- Use the iPhone keyboard's foreground dictation in a text field and let the
  user review before Send. Do not promise an always-listening or wake-word app.
- Use an explicit computer selector, an offline indicator, and a visible Stop.
  Do not imply that device pairing, transport, identity storage, or chat is
  functional until the end-to-end implementation is reviewed and tested.
- A service worker may cache only versioned public shell assets, not pairing
  challenges, keys, session proofs, requests, responses or private data.
- Do not deploy the shell or configure a private route as part of this draft.

References: [WebKit Home Screen web apps](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/),
[WebKit storage policy](https://webkit.org/blog/14403/updates-to-storage-policy/),
[Web Crypto key storage](https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto),
[camera secure-context and permission requirements](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia),
and [BarcodeDetector compatibility](https://developer.mozilla.org/en-US/docs/Web/API/BarcodeDetector).

## Precise synthetic wire proposal (not deployed)

These JSON shapes are for coordination and tests. They are not an activation
promise: the route adapter, strict JSON parser, signed responses, durable
transaction/recovery, native approval UI, and private HTTPS transport remain
unimplemented. The Node loopback bridge in the tests is a **fixture**, not the
production server. All byte strings below are standard padded base64; UUIDs are
canonical textual UUIDs and are lowercased when placed in signed transcripts.

The QR contains JSON:

```json
{"version":1,"hostID":"<uuid>","origin":"https://<approved-private-host>","macName":"<label>","nonce":"<base64 32 bytes>","macEphemeral":"<base64 65-byte P-256 X9.63 public key>","macSigningPublic":"<base64 65-byte P-256 X9.63 public key>"}
```

The phone must independently select or manually enter its expected private
origin **before** making a request, compare it exactly with `origin`, and show
the SHA-256 hexadecimal fingerprint of `macSigningPublic` to compare with the
Mac. A QR value alone must never authorize an arbitrary fetch, redirect, LAN
scan, or change of approved origin. The current core requires expected origin
and fingerprint as separate inputs; it does no network I/O. The Mac enforces
the challenge's one-use 120-second continuous-clock expiry. There is no QR
expiry timestamp yet; any future displayed wall-clock timestamp is advisory.

`POST /v1/enrollment/join` proposed body:

```json
{"phoneName":"<label>","nonce":"<challenge nonce, base64>","phoneEphemeral":"<base64 65-byte P-256 X9.63 public key>"}
```

The synthetic host returns `{"code":"<10 decimal digits>","fingerprint":"<64 lowercase hex>"}` for the interoperability fixture. A real
API must instead return `{"attemptID":"<uuid>","state":"pending"}`; the
browser computes the comparison code locally. The host's native UI must obtain
explicit owner approval after both fingerprint and comparison code are compared.
The proposed `POST /v1/enrollment/status` body is `{"attemptID":"<uuid>"}`;
its response must be an AES-GCM envelope (format below, role `approval`) whose
plaintext is `{"attemptID":"<uuid>","state":"pending|approved|denied|expired"}`.
The phone must authenticate that envelope and obtain the phone user's explicit
confirmation before creating a long-lived key. A disabled Swift handler and
native-only coordinator implement this binding with injected test storage; no
real native UI or listener is wired. The private host must independently
check the approved PWA Origin, Host, TLS, rate limits, and enrollment expiry.

After the explicit approval, proposed `POST /v1/enrollment/finish` and
`POST /v1/enrollment/ack` bodies and responses are AES-256-GCM envelopes:

```json
{"iv":"<base64 12-byte nonce>","ciphertext":"<base64 ciphertext followed by 16-byte GCM tag>"}
```

The phone plaintext for `finish` is
`{"deviceID":"<uuid>","generation":1,"publicKey":"<base64 P-256 X9.63 signing public key>","signature":"<base64 64-byte P1363 ECDSA signature>"}`.
The Mac reply has the same shape, using its host ID and pinned signing public
key. The phone's `ack` plaintext is `{"signature":"<base64 64-byte P1363 ECDSA signature>"}`. ECDSA uses SHA-256. `Enrollment.swift` and
`PairingCompletion.swift` define the ordered, length-prefixed transcript,
HKDF-SHA256 derivation, role-specific AES-GCM associated data, and proof
messages. Phone and Mac must verify the other side's proof and the Mac key
fingerprint. AES-GCM nonces must be fresh; never reuse a nonce with a key.
The normal disabled-handler `ack` response is a `receipt`-role encrypted
envelope containing a Mac-signed pairing receipt. If the durable write succeeds
but its acknowledgement is lost, the response is unknown, never retried
blindly. A local owner can inspect the stored phone, approve a fresh recovery
challenge, and require the phone to sign it before the Mac returns a signed
receipt. The full Swift/Node fixture simulates process exit after an fsynced
synthetic write and recovers from a fresh process. This is not proof of real
Keychain durability, browser IndexedDB behavior, or cross-device atomicity;
those remain blocking work. Remote revocation delivery is not implemented.
The disabled handler returns HTTP `409 {"error":"outcome-unknown"}` if a
commit reports failure after it may have written. The client must stop and use
the owner-reviewed recovery path, never automatically replay the ack. A lost
connection at that boundary is likewise unknown.

Proposed `POST /v1/session/challenge` body is an intent object:

```json
{"hostID":"<uuid>","deviceID":"<uuid>","generation":1,"scopeID":"<opaque id>","scopeRevision":"<opaque revision>","action":"submit","method":"POST","path":"/v1/tasks","expiresAt":1700000000,"payloadDigest":"<base64 SHA-256 of exact payload bytes>"}
```

`expiresAt` is Unix seconds and must be in the next 30 seconds; the server
also tracks a continuous-clock deadline. `action`/`path` are exactly
`submit`/`/v1/tasks`, `status`/`/v1/tasks/status`, or
`stop`/`/v1/tasks/stop`. Proposed success response:
`{"nonce":"<base64 32 bytes>","intent":{...the exact accepted intent...}}`.
The single-use server nonce, all intent fields including method/path/expiry,
and the SHA-256 digest of exact payload bytes are signed by the paired phone's
P-256 ECDSA key. `RequestProof.swift` defines the ordered length-prefixed bytes
under `atlas-request-proof-v1`. Signatures use WebCrypto ECDSA/SHA-256 raw
64-byte `r || s`; no exported private key is needed.

The proposed three task routes take:

```json
{"challenge":{"nonce":"<base64 32 bytes>","intent":{ "...":"..." }},"signature":"<base64 64-byte P1363 signature>","payload":"<base64 exact UTF-8 JSON bytes>"}
```

The decoded payload for submit is `{"id":"<uuid>","task":"<reviewed text>"}`;
status and Stop use `{"id":"<the same immutable uuid>"}`. The server must
compare the actual HTTP method/path and payload digest with the signed intent,
recheck the active local scope, key generation, revocation and expiry at the
final dispatch boundary, and consume each nonce once. The synthetic in-memory
routes return `{"id":"<uuid>","status":"submitted|stopped|..."}`; **that
unsigned response format is not safe for production**. The disabled HTTP
handler signs the synthetic result using the reference format below. A real
Agents dispatcher and production transport are not connected. Unknown dispatch
never retries.

The selector is a phone-local list of explicitly linked Mac IDs, names,
private origins, pinned public fingerprints and generations. It is not a
cross-device discovery endpoint. All entries begin offline after restart;
selecting an offline/revoked entry must not fall back to another. The Mac's
owner-only UI is the authority for listing and revoking phones. A local phone
unlink is immediate on that phone but cannot guarantee remote revocation while
offline; the owner must revoke the lost phone on each Mac. A signed remote
unlink/revocation route, acknowledgement and recovery schemas are not
implemented and must not be exposed as if they were. The disconnected
`MacPairingVault` reference supports local owner-approved revocation and
rotation with proof from both old and new keys; it is tested only against a
synthetic in-memory store and is not wired to an actual Keychain or network.

The reference signed-response JSON is:

```json
{"intent":{"hostID":"<uuid>","deviceID":"<uuid>","requestID":"<uuid>","generation":1,"action":"status","method":"POST","path":"/v1/tasks/status","status":"running","payloadDigest":"<base64 SHA-256 of exact response payload bytes>","requestNonce":"<base64 nonce from request>","expiresAt":1700000000},"signature":"<base64 64-byte P1363 signature>"}
```

The response payload bytes must travel separately as base64 in the eventual
HTTP envelope; that outer envelope and its strict parser are not implemented.
`ResponseProof.swift` specifies `atlas-response-proof-v1` length-prefixed
fields and verifies the pinned Mac key, exact selected host and phone, request
ID, generation, action, method, path, request nonce, body hash and expiry. The
browser must verify all of those before showing a status or acting on a reply.

### Lost-ack recovery reference

Recovery is local-owner initiated and has **no public HTTP route** yet. After
inspection, the synthetic Mac issues this fresh 30-second challenge:

```json
{"descriptor":{"hostID":"<UUID>","phoneID":"<UUID>","phoneName":"<label>","generation":1,"binding":"<base64 32-byte transcript hash>","macPublic":"<base64 65-byte P-256 key>","phonePublic":"<base64 65-byte P-256 key>"},"nonce":"<base64 32 bytes>"}
```

The phone verifies the stored Mac fingerprint, phone ID, public key, binding,
and generation, then signs length-prefixed `atlas-pair-recovery-v1`, lowercase
host ID, lowercase phone ID, decimal generation, raw binding, and raw nonce.
The Mac consumes the nonce once, rechecks the persisted record and revocation,
and returns:

```json
{"descriptor":{"hostID":"<UUID>","phoneID":"<UUID>","phoneName":"<label>","generation":1,"binding":"<base64 32 bytes>","macPublic":"<base64 65 bytes>","phonePublic":"<base64 65 bytes>"},"signature":"<base64 64-byte P1363 ECDSA signature>"}
```

The Mac signature covers length-prefixed `atlas-pair-receipt-v1`, lowercase
host ID, lowercase phone ID, phone name, decimal generation, raw binding,
Mac public key, and phone public key. The phone verifies this with its pinned
Mac key. Exact HTTP transport, owner UI, restart policy, and IndexedDB staging
still require implementation and independent review.
