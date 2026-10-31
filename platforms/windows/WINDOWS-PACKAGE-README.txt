ATLAS for Windows - experimental candidate

This folder contains an experimental Windows development build. It is not a verified release. Keep the files together and run Atticus.exe. It requires Windows 10 version 2004 (build 19041) or newer, x64; Windows 11 is recommended. Microsoft Edge WebView2 Runtime and Git for Windows are required. If WebView2 is missing, obtain the Evergreen Runtime from Microsoft: https://developer.microsoft.com/microsoft-edge/webview2/ The existing task backend uses Claude Code and a supported Claude account; sign-in and speech model setup occur separately. ChatGPT/Codex task support remains disabled.

The bundled Python runtime and dependencies are in runtime. The first launch may download a speech model after the user chooses setup. ATLAS can interact with applications and files; inspect prompts and approve only actions you intend.

See LICENSE-ATTICUS.txt, LICENSE-Plip.txt and the licenses folder for component notices. Automatic updates are disabled. The app is unsigned unless a later verified release explicitly says otherwise. No installer or account is included.
