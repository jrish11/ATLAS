"""Fake JSONL provider for native integration tests; never uses network or tools."""
import json
import os
import sys

profile = os.environ['ATLAS_FIXTURE_PROFILE']
project = os.environ['ATLAS_FIXTURE_PROJECT']
mode = os.environ.get('ATLAS_FIXTURE_MODE', 'ok')
if mode == 'never_read':
    import time
    time.sleep(30)
    raise SystemExit(0)
if mode == 'delayed_read':
    import time
    time.sleep(1)
    for line in sys.stdin:
        value = json.loads(line)
        if value.get('result', {}).get('decision') == 'accept':
            with open(os.environ['ATLAS_FIXTURE_MARKER'], 'w', encoding='utf-8') as marker:
                marker.write('unexpected accept')
            break
    raise SystemExit(0)
features = {name: False for name in ('hooks', 'plugins', 'apps', 'skill_search', 'remote_plugin', 'skill_mcp_dependency_install', 'shell_snapshot')}
config = {'mcp_servers': {}, 'apps': {'_default': {'enabled': False}}, 'default_permissions': profile,
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
        send({'id': 'approval', 'method': 'item/fileChange/requestApproval', 'params': {'threadId': 'thread', 'turnId': 'stale' if mode == 'stale' else 'turn'}})
