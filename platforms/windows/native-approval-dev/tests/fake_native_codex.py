"""Fake JSONL provider for native integration tests; never uses network or tools."""
import json
import os
import sys

profile = os.environ['ATLAS_FIXTURE_PROFILE']
project = os.environ['ATLAS_FIXTURE_PROJECT']
mode = os.environ.get('ATLAS_FIXTURE_MODE', 'ok')
if mode == 'stderr_probe':
    print('FAKE_MXC_DIAGNOSTIC', file=sys.stderr, flush=True)
    raise SystemExit(0)
if mode == 'sandbox_fake':
    with open(os.environ['ATLAS_FAKE_INSIDE'], 'w', encoding='utf-8') as output:
        output.write('fixture')
    raise SystemExit(0)
if mode == 'argv_echo':
    print(json.dumps({'arguments': sys.argv[1:]}), flush=True)
    raise SystemExit(0)
if mode == 'handle_canary':
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.SetEvent.argtypes = [ctypes.c_void_p]
    kernel.SetEvent(ctypes.c_void_p(int(os.environ['ATLAS_CANARY_HANDLE'])))
    print(json.dumps({'canary_attempted': True}), flush=True)
    raise SystemExit(0)
if mode == 'start_marker':
    with open(os.environ['ATLAS_FIXTURE_MARKER'], 'w', encoding='utf-8') as marker:
        marker.write('started')
    raise SystemExit(0)
if mode == 'spawn_child':
    import subprocess
    import time
    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], close_fds=True)
    print(json.dumps({'child_pid': child.pid}), flush=True)
    time.sleep(60)
    raise SystemExit(0)
if mode == 'never_read':
    import time
    time.sleep(30)
    raise SystemExit(0)
if mode in ('delayed_read', 'synchronized_read'):
    import time
    if mode == 'delayed_read':
        time.sleep(1)
    for line in sys.stdin:
        value = json.loads(line)
        if mode == 'synchronized_read' and 'data' in value:
            print(json.dumps({'fixture': 'filler-consumed'}), flush=True)
            continue
        if value.get('result', {}).get('decision') == 'accept' or value.get('method') in ('thread/start', 'turn/start'):
            with open(os.environ['ATLAS_FIXTURE_MARKER'], 'w', encoding='utf-8') as marker:
                marker.write('unexpected accept')
            break
    raise SystemExit(0)
features = {name: False for name in ('hooks', 'plugins', 'apps', 'skill_search', 'remote_plugin', 'skill_mcp_dependency_install', 'shell_snapshot')}
config = {'windows': {'sandbox': 'unelevated' if mode == 'weak_sandbox' else 'mxc'}, 'mcp_servers': {}, 'apps': {'_default': {'enabled': False}}, 'default_permissions': profile,
          'permissions': {profile: {'filesystem': {':minimal': 'read', ':workspace_roots': 'write'}, 'network': {'enabled': mode == 'unsafe'}}},
          'features': features, 'web_search': 'disabled', 'allow_login_shell': False,
          'shell_environment_policy': {'inherit': 'none', 'ignore_default_excludes': False}}
def send(data):
    print(json.dumps(data), flush=True)
for line in sys.stdin:
    message = json.loads(line)
    method = message.get('method')
    if method == 'initialized':
        continue
    if 'result' in message or 'error' in message:
        if mode == 'stale' and message.get('result', {}).get('decision') == 'accept':
            raise SystemExit('stale request was accepted')
        send({'method': 'turn/completed', 'params': {'threadId': 'thread', 'turn': {'id': 'turn', 'status': 'completed'}}})
        continue
    if method == 'turn/interrupt':
        send({'id': message['id'], 'result': {}})
        send({'method': 'turn/completed', 'params': {'threadId': 'thread', 'turn': {'id': 'turn', 'status': 'interrupted'}}})
        continue
    replies = {'initialize': {}, 'config/read': {'config': config}, 'mcpServerStatus/list': {'data': [], 'nextCursor': None},
               'hooks/list': {'data': [{'errors': [], 'hooks': []}]}, 'skills/list': {'data': [{'errors': [], 'skills': []}]},
               'account/read': {'account': {'type': 'chatgpt'}}, 'model/list': {'data': [{'isDefault': True, 'model': 'fixture'}], 'nextCursor': None},
               'thread/start': {'activePermissionProfile': {'id': profile}, 'runtimeWorkspaceRoots': [project], 'approvalPolicy': 'on-request', 'approvalsReviewer': 'user', 'thread': {'id': 'thread', 'model': 'fixture'}},
               'turn/start': {'turn': {'id': 'turn'}}}
    if method not in replies:
        raise SystemExit('unexpected request')
    send({'id': message['id'], 'result': replies[method]})
    if method == 'turn/start':
        request = {'id': 'approval', 'method': 'item/fileChange/requestApproval', 'params': {'threadId': 'thread', 'turnId': 'stale' if mode == 'stale' else 'turn'}}
        if mode == 'late':
            send({'method': 'turn/completed', 'params': {'threadId': 'thread', 'turn': {'id': 'turn', 'status': 'completed'}}})
        send(request)
        if mode in ('duplicate', 'conflict', 'duplicate_cancel'):
            if mode == 'conflict':
                request = {**request, 'params': {**request['params'], 'changed': 'conflicting payload'}}
            send(request)
