# Persistent companion integration candidate

This isolated development branch connects the strict authenticated Swift HTTP
handler to `RegistryRoutes`, correlated native supervisor IPC, the existing
`RemoteGate`/`NativeRegistryBridge`, its durable barrier, and `Agents`. Native
confirmation remains the final task-dispatch authority. No web message can
supply the supervisor capability. The development-only native coordinator
presents owner disclosures, QR comparison, a paired-phone selector, revocation,
and a scoped session confirmation. A loopback listener exists in code but is
started only by the experimental native entry point after owner action.

The journal is separate from the pairing vault. Restart review consults the
actual supervisor task barrier; if a session was interrupted, recovery revokes
its phone conservatively, including when a revocation-journal write failed
before recording the owner's intent. A clean Stop quiesces the signed route and writes a distinct durable stopped
marker. If no receipt is pending it clears immediately; otherwise owner review
of the actual supervisor receipt is required before reconnection, while preserving
the phone identity. A failed or uncertain Stop leaves the active marker and is
conservatively revoked during restart review. An unclear result cannot be silently
retried. The session reserves one task slot through Stop and unknown outcomes.

`tests/companion/production_e2e_fixture.swift` uses synthetic keys, a temporary
profile and a fake provider to run signed enrollment and task requests through
the real handler, native channel, supervisor and Agents registry. Its optional
`--loopback` mode binds only 127.0.0.1 and uses disposable files. This is not a
real-phone or production-Keychain test. The code has not been independently
reviewed as an integrated whole and must not be enabled or published on that
basis. The private TLS route, real browser PNA/CORS behavior, actual Keychain
recovery, frontend integration, signing and separately approved real-device
validation remain open. No route, keychain item, real pairing or network setting
was created during development.

The signed request's wall and continuous-clock expiry is carried into the
supervisor dispatch token, checked before native approval and again at the
final commit boundary. A delayed approval cannot start the task. The native
sheet displays that request deadline as well as the selected project and scope.
Every task sheet binds the selected phone's name, ID, generation and key
fingerprint, the Mac fingerprint, project, scope and deadline. Untrusted task
text is displayed separately with controls visible and its exact SHA-256 digest;
the original bytes continue unchanged to the registry. Pairing receipt recovery
requires explicit native review and phone key proof as described in
PWA-RECOVERY-CONTRACT.md. The complete integration and pending-sheet lifecycle
still require independent security and real UI review.
