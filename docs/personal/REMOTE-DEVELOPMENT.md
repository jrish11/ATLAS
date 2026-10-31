# ATLAS Remote development boundary

The isolated development candidate contains an experimental remote session. It
is off by default and is available only to the development app launched with
`--experimental-remote`. The native owner selects a project and HTTPS origin,
reviews a ten-minute disclosure, and separately approves phone pairing and each
task. Credentials and a one-use invitation are created only after the initial
approval, remain in memory, and are revoked when the private channel closes.
The native app also sends a fresh control capability over that channel; remote
supervisor commands require it, and activation must independently match the
exact configuration held by the native owner. WebKit cannot send remote
control commands. A phone keeps one immutable active task ID for the session.
The HTTP service binds only to IPv4 loopback; ATLAS does not configure a route,
VPN, proxy, firewall, or public endpoint. The phone page uses text or keyboard
dictation, review before Send, progress, and Stop.

The existing Agents registry remains the only task dispatcher. The selected
project identity and expiry are checked again at dispatch. A persistent barrier
blocks another session when an in-flight result is uncertain. Native owner
review can clear it only after dispatch settles and the owner inspects the
receipt and project; absence of a receipt does not prove that nothing happened.
Stop cannot undo an already dispatched action. The ordinary app-server transport
remains local stdio, and remote requests cannot select a project, export
credentials, or invoke raw shell.

Synthetic tests cover native private-channel approval, a fake Codex provider,
loopback transport, registry status and Stop, scope changes, expiry, replay,
rotation, denial, and uncertain outcomes. They are not a live phone validation
or an independent security review. Do not enable a real session, create a real
invitation, pair a device, or configure a route until independent review and
explicit owner approval for each action. No public endpoint, network setting,
credential, device, OS permission, installation, or upload was configured by
this development work. Same-user malicious-process isolation is not claimed.
