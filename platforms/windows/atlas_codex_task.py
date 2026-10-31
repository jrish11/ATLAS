"""Experimental Codex task path. Disabled pending Windows native verification."""
import os
import shutil
import threading
import codex_provider

# This cannot be enabled by settings or environment variables. Change only after
# native Windows review validates sandbox, job cancellation, and process launch.
WINDOWS_CODEX_VERIFIED = False


def run_task(task, workspace, emit, provider_factory=codex_provider.CodexProvider, verified=None, cancel_path=None):
    """Run one explicitly scoped turn. No screenshots, Claude tools, or MCP bridging.

    `verified` is an injection point for tests, never supplied by the app route.
    Approval requests are always denied; accepting actions is not wired yet.
    """
    if verified is None: verified = WINDOWS_CODEX_VERIFIED
    if not verified:
        return {'status': 'unavailable', 'result': 'Codex tasks are disabled until the Windows safety and cancellation checks are verified.'}
    if not isinstance(workspace, str) or not os.path.isabs(workspace) or not os.path.isdir(workspace):
        return {'status': 'failed', 'result': 'Select an existing project folder before using Codex.'}
    executable = shutil.which('codex')
    if not executable: return {'status': 'failed', 'result': 'Codex CLI was not found.'}
    try:
        provider = provider_factory(executable=executable, emit=emit, platform_profile='windows')
        finished = threading.Event()
        def watch_cancel():
            while not finished.wait(.1):
                if cancel_path and os.path.isfile(cancel_path):
                    provider.interrupt()
                    return
        if cancel_path: threading.Thread(target=watch_cancel, daemon=True).start()
        try: return provider.run(workspace, task)
        finally: finished.set()
    except codex_provider.ProviderError as exc:
        return {'status': 'failed', 'result': str(exc)}
