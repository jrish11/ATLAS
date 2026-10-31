> Historical development note. This may describe an earlier build. See the root README, CHANGELOG and RELEASES for current status.

# ATLAS Remote development boundary

This is an inactive protocol foundation, not a phone connection. Nothing opens a
listener, configures Tailscale, creates credentials, or starts a task. Do not
package or enable it until a native-owned authenticated bridge, pairing flow,
transport and independent review are complete.

A future owner-controlled enable action must disclose the exact selected project,
the HTTPS origin, device and session expiry. The native app must hold the
credentials and scope, generate unpredictable one-use pairing material only
after confirmation, and own revocation. A mobile client must never be able to
select a project, approve a sensitive action, invoke shell/JSON-RPC, or create
a session. Scope identity and normal local approvals must be rechecked by the
existing dispatcher. A stop cannot undo a command already dispatched.

Potential transport: Tailscale Serve to a loopback-only HTTP service. Serve must
be explicitly configured by the owner; public Funnel is out of scope. Host and
Origin checks are not authentication, and forwarded identity headers cannot be
trusted unless the verified transport provides a trustworthy boundary.
See https://tailscale.com/docs/features/tailscale-serve and
https://learn.chatgpt.com/docs/app-server.

Unresolved: authenticated native-to-gateway authority, identity binding through
the proxy, pairing and credential delivery, iOS browser session security, secure
status/cancellation bridging, and post-restart revocation. The gate is not
wired to Codex or a listener. No claim of same-user malicious process isolation.

The prototype now binds asynchronous callbacks to the exact in-memory session
and task. A submission whose acknowledgement is lost remains `unknown` and
blocks re-pairing until an owner-reviewed or authoritative terminal outcome is
recorded. This barrier is in memory only: a durable supervisor receipt and a
trusted native review channel are still required before any activation.

`remote_ipc.py` is an isolated adapter experiment. Synthetic socket-pair tests
exercise its fixed message shape against the existing Agents registry, using a
fake provider and an injected owner-confirmation callback. Existing task
receipts prevent redispatch across a synthetic supervisor restart; a prior
receipt is reported as unknown until reviewed. The adapter is not connected to
a native process, an HTTP endpoint, pairing, or an actual phone. Its callback
is not proof of owner consent until a native-owned private channel supplies it.
The native channel must also retain final dispatch/revocation guarantees and
independent review before enabling the feature.

The synthetic bridge now linearizes cancellation against a dispatch commit and
uses the existing Agents request receipt in tests. Stop returns immediately;
if dispatch has already committed, the bridge requests cancellation as soon as
its registry receipt exists. This cannot undo an action already committed.
The in-memory unknown-outcome barrier is not a durable reconciliation system.
The real native owner-confirmation callback, inherited descriptor ownership,
listener, pairing, and status/event transport are still absent; do not enable
or present this preview as functional remote control.
