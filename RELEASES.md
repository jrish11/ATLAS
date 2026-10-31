# Verified release inventory

Current delivered Mac preview: **v3.5**. Earlier unavailable prototypes and unverified Windows binaries are not invented here. All six source revisions below exist locally and have sanitized archives in the prepared workspace. The Git tags preserve actual product version names and point to sanitized snapshot commits. These are source tags; older private binary ZIPs are not published. No GitHub Release asset upload is claimed by this document.

| Source tag | Original source revision | Source status |
| --- | --- | --- |
| v3 | `cf931b1ceb5d3b9205a841820699ee3c222fbad7` | Sanitized source snapshot available |
| v3.1 | `c2018ceea4e89dc609947e1cc07de174b0af236d` | Sanitized source snapshot available |
| v3.2 | `5517bbe46a58f4b8f1540cdc525fcb5175006fca` | Sanitized source snapshot available |
| v3.3 | `37c9a57cff2d84d067109a73d7309d8ac848b743` | Sanitized source snapshot available |
| v3.4 | `ac03088c850d232cc6d85bd0f8cdc2e54a5ac57e` | Sanitized source snapshot available |
| v3.5 | `dc1780e84de5beef9c0830063fb035f87915e7f0` | Sanitized source snapshot available |

The machine-readable inventory in `docs/releases/source-versions.json` records exact dates, archive SHA-256 values and sanitization changes. Snapshots differ from original trees only where documented; they are not represented as byte-identical original commits. Original licenses are unchanged.

Only the v3.5 Mac binary has a separately verified public-safe artifact: `ATLAS-v3.5-macOS-arm64-PUBLIC.zip`, 2,123,762 bytes, SHA-256 `43af1cdb16b4a9fb251b2041cdf9b5238a223446a56e43dbc9376fbf0bb24d8b`. Earlier delivered binaries contain a private optional companion and MUST NOT be uploaded as public release assets. Rebuilding or separately sanitizing an older binary requires validation; none is claimed here.

Windows source-only and remote development snapshots are separate experimental tracks, not v3.5 release assets. The phone/PWA frontend is not ready. Repository: https://github.com/jrish11/ATLAS . Source tags and archive links are listed in the machine-readable inventory. A public GitHub network fork cannot be private; a private derived repository is a different arrangement.
