# Pairing screens in the desktop review candidate

These labels describe this development candidate, not the currently published
ATLAS app. Its menu item appears only in the development build launched with
`--experimental-companion`; it is not a claim that the public preview can pair.
A separately approved private HTTPS route and a compatible PWA are still needed.

1. Open ATLAS’s menu and choose **Phone Pairing…**. Select the project folder.
2. In **Private companion HTTPS origin**, enter the exact preconfigured private
   HTTPS origin. ATLAS does not create the route, VPN, certificate or firewall.
3. Review **Start experimental companion?** and choose **Start companion** only
   if the Keychain identity, local listener, project, scope and expiry are
   approved. **Companion listener started locally** then shows its loopback port.
4. On a fresh pairing, **Pair ATLAS on your phone** shows the short-lived QR.
   Scan it from the companion, or choose **Copy pairing challenge** and paste the
   complete challenge into the companion. It is single-use and expires after two
   minutes. On **Confirm this phone**, compare the phone name,
   comparison code and Mac fingerprint, then choose **Codes match; pair**.
5. After the exchange, **Allow a companion session?** shows the chosen phone,
   project, scope and expiry. Choose **Allow session**. Each task then opens a
   separate Mac approval showing the authenticated phone and Mac fingerprints,
   project, scope, expiry and a scrollable view of the exact task’s digest and
   escaped display text.
6. On later starts, **Review previous companion activity** appears before the
   **Paired phones** selector. It offers **Use selected**, **Link new phone**,
   **Revoke selected**, and **Recover pairing**. A receipt that may not have
   arrived must be reviewed using **Recover pairing**; no request is resent
   automatically. **Recovery receipt issued** asks the owner to check that the
   phone actually confirms recovery before a session is offered. **Stop Phone Access** stops the local listener and session.

A clean quiesced stop retains the pairing; a task receipt needing inspection
requires owner review before reconnecting. An interrupted or uncertain session
can conservatively revoke the phone, requiring a new pairing. Do not suggest
these screens are available in the published desktop release until the reviewed
candidate has actually been installed and its transport separately configured.
