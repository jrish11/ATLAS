Atticus requires Apple Silicon, macOS 26+, and a working /usr/bin/python3.

This limited-test app does not contain Node or Pi. Install Node 22.19 or newer with npm from https://nodejs.org/en/download if they are missing. No credentials are transferred.

In Finder, use Show Package Contents on Atticus Dev.app, then open Contents/Resources/Setup/Setup.command. Read the prompt and choose whether to download the pinned public Pi runtime. It disables package install scripts, uses an isolated npm cache/config, and writes only a new per-device runtime under ~/Library/Application Support/Atticus Dev/pi-runtime. Canceling the prompt makes no changes. Existing runtime directories are never overwritten; failed setup leaves an INCOMPLETE marker for inspection.

The app's foreground OpenAI key must be entered locally into its secure settings. Codex uses its separate supported local ChatGPT login and remains subject to the development task gate. Node/npm and Codex setup are independent.

The app is ad-hoc signed, not notarized. If macOS blocks it, do not bypass a warning automatically; report it for owner review. Microphone, Accessibility and browser Automation permissions must be granted by the owner when needed.

Rollback: quit this development app and remove its copied bundle. Removing its separate development profile or runtime is optional after reviewing the contents. Do not remove or overwrite any other Atticus installation. Keys belong to this Mac's Keychain and are not in this download.
