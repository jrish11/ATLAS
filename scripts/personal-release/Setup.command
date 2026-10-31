#!/bin/zsh
set -eu
setup_dir="$(cd "$(dirname "$0")" && pwd)"
export PATH="/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:/usr/bin:/bin"
print 'Atticus first-run runtime setup'
print 'Requires Node 22.19+ and npm installed from an official source.'
print 'Downloads pinned public Pi dependencies with install scripts disabled.'
print 'Creates a new per-device runtime. No keys, login sessions or permissions are copied.'
read -r 'answer?Continue with download? [y/N] '
[[ "$answer" == [yY] ]] || exit 0
node_path="$(command -v node || true)"
npm_path="$(command -v npm || true)"
[[ -n "$node_path" && -n "$npm_path" ]] || { print 'Install Node and npm from nodejs.org, then try again.'; exit 1; }
npm_cli="$(/usr/bin/python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$npm_path")"
parent_dir="$HOME/Library/Application Support/Atticus Dev"
mkdir -p "$parent_dir"
/usr/bin/python3 "$setup_dir/bootstrap_runtime.py" --output "$parent_dir/pi-runtime" --node "$node_path" --npm-cli "$npm_cli" --confirm-download
print 'Runtime setup finished. Open Atticus and enter your foreground key locally.'
