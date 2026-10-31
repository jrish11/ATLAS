# Only versions exercised against the effective restricted configuration are allowed.
# CodexProvider.run rechecks effective MCP/apps/skills/hooks/read/network boundaries,
# ChatGPT account and the account-default model before starting any turn.
CODEX_VERIFIED_CLI_VERSIONS = frozenset({'0.155.1'})


def codex_scoped_readiness(row):
    if platform.system() != 'Darwin': return False, 'Scoped Codex tasks require the verified macOS runtime.'
    if pref('codexAuthMode', 'existing') != 'existing': return False, 'Choose Existing login for scoped Codex account tasks; API fallback is disabled.'
    if not isinstance(row, dict) or not isinstance(row.get('folder'), str) or not os.path.isdir(row['folder']):
        return False, 'Choose and confirm an existing project folder.'
    try: codex_provider.CodexProvider.validate_scope(row['folder'])
    except codex_provider.ProviderError as error: return False, str(error)
    executable = shutil.which('codex')
    if not executable: return False, 'Install the supported Codex CLI and sign in with your ChatGPT account.'
    try:
        version = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError): return False, 'Could not verify the installed Codex CLI version.'
    match = re.fullmatch(r'codex-cli ([0-9]+\.[0-9]+\.[0-9]+)\s*', version.stdout)
    if version.returncode or not match or match[1] not in CODEX_VERIFIED_CLI_VERSIONS:
        return False, 'This Codex CLI version has not passed the scoped adapter checks; no task was started.'
    return True, 'Version and project accepted; account, model and effective tool restrictions must pass adapter preflight.'

