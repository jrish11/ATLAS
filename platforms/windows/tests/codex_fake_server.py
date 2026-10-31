"""A deterministic fake of the small app-server protocol subset used in tests."""
import json
import os
import sys
import tempfile
import time

def send(value):
    print(json.dumps(value), flush=True)

for line in sys.stdin:
    m = json.loads(line); method = m.get('method'); ident = m.get('id')
    params = m.get('params') or {}
    if method == 'initialize': send({'id': ident, 'result': {'userAgent': 'fixture'}})
    elif method == 'account/read':
        send({'id':ident,'result':{'account':{'type':'apiKey' if os.environ.get('FIXTURE_WRONG_ACCOUNT') else 'chatgpt'}}})
    elif method == 'model/list':
        models=[] if os.environ.get('FIXTURE_NO_DEFAULT') else [{'model':'fixture-account-model','isDefault':True,'hidden':False}]
        if os.environ.get('FIXTURE_DUPLICATE_DEFAULT'):models.append({'model':'other','isDefault':True,'hidden':False})
        send({'id':ident,'result':{'data':models,'nextCursor':None}})
    elif method == 'config/read':
        servers = {'fixture': {'command': 'fixture', **({'enabled':False} if os.environ.get('FIXTURE_MCP_DISABLED') and not os.environ.get('FIXTURE_MCP_IGNORED') else {})}} if os.environ.get('FIXTURE_MCP') else {}
        if os.environ.get('FIXTURE_MCP_UNSAFE'): servers={'unsafe.name':{'command':'fixture'}}
        flags={k:False for k in ('hooks','plugins','apps','skill_search','remote_plugin','skill_mcp_dependency_install','shell_snapshot')}
        profile=os.environ.get('FIXTURE_PROFILE','missing')
        config={'mcp_servers':servers,'features':flags,'web_search':'disabled','allow_login_shell':False,
                'apps':{'_default':{'enabled':False}}, 'default_permissions':profile,
                'permissions':{profile:{'extends':None,'workspace_roots':None,'filesystem':{':minimal':'read',':workspace_roots':'write','/Library/Developer/CommandLineTools':'read'},'network':{'enabled':False}}},
                'shell_environment_policy':{'inherit':'none','ignore_default_excludes':False}}
        if os.environ.get('FIXTURE_WINDOWS'): config['permissions'][profile]['filesystem'].pop('/Library/Developer/CommandLineTools')
        if os.environ.get('FIXTURE_UNSAFE_CONFIG'): config['features']['apps']=True
        if os.environ.get('FIXTURE_APP_OVERRIDE'): config['apps']['fixture']={'enabled':'unexpected'}
        if os.environ.get('FIXTURE_APP_ENABLED'): config['apps']['example']={'enabled':not bool(os.environ.get('FIXTURE_APP_DISABLED'))}
        send({'id': ident, 'result': {'config':config, 'origins': {}}})
    elif method == 'mcpServerStatus/list':
        rows = [{'name':'fixture','tools':{},'resources':[],'resourceTemplates':[],'runtimeStatus':None}] if os.environ.get('FIXTURE_MCP') else []
        if os.environ.get('FIXTURE_MCP_ERROR') and rows: rows[0]['toolsError']='unavailable'
        if os.environ.get('FIXTURE_MCP_TOOL'):
            rows = [{'name':'fixture','tools':{'unexpected':{}},'resources':[],'resourceTemplates':[],'runtimeStatus':None}]
        send({'id':ident,'result':{'data':rows,'nextCursor':'unexpected' if os.environ.get('FIXTURE_MCP_CURSOR') else None}})
    elif method in ('hooks/list', 'skills/list'):
        field = 'hooks' if method == 'hooks/list' else 'skills'
        enabled = os.environ.get('FIXTURE_' + field.upper()) and (not os.environ.get('FIXTURE_OVERRIDE') or os.environ.get('FIXTURE_SKILLS_STUCK'))
        items = ([{'enabled': True, 'path': os.path.join(tempfile.gettempdir(), 'fixture', 'SKILL.md')}] if enabled else
                 [{'enabled': False, 'path': os.path.join(tempfile.gettempdir(), 'fixture', 'SKILL.md')}] if field == 'skills' and os.environ.get('FIXTURE_SKILLS') else [])
        send({'id': ident, 'result': {'data': [{'cwd': params['cwds'][0], field: items, 'errors': []}]}})
    elif method in ('thread/start', 'thread/resume'):
        assert 'sandbox' not in params and params['approvalPolicy'] == 'on-request'
        assert params['permissions'].startswith('atticus_') and params['runtimeWorkspaceRoots'] == [params['cwd']]
        profile = 'wrong' if os.environ.get('FIXTURE_WRONG_PROFILE') else params['permissions']
        send({'id': ident, 'result': {'thread': {'id': params.get('threadId', 'fixture-thread'), 'model': 'wrong' if os.environ.get('FIXTURE_WRONG_MODEL') else params.get('model')},
             'activePermissionProfile':{'id':profile}, 'runtimeWorkspaceRoots':params['runtimeWorkspaceRoots'],
             'approvalPolicy':'on-request', 'approvalsReviewer':'user'}})
    elif method == 'turn/start':
        assert params['input'][0]['type'] == 'text'
        if os.environ.get('FIXTURE_EARLY_APPROVAL'):
            send({'id':'early-approval','method':'item/commandExecution/requestApproval','params':{'threadId':params['threadId'],'turnId':'fixture-turn','command':'fixture'}})
            response=json.loads(sys.stdin.readline())
            assert response['id']=='early-approval' and response['result']['decision']=='cancel'
        if os.environ.get('FIXTURE_EARLY'):
            send({'method':'turn/started','params':{'threadId':params['threadId'],'turn':{'id':'stale-turn'}}})
            send({'method':'item/agentMessage/delta','params':{'threadId':params['threadId'],'turnId':'stale-turn','delta':'stale'}})
            send({'method':'turn/completed','params':{'threadId':params['threadId'],'turn':{'id':'stale-turn','status':'completed'}}})
            send({'method':'turn/started','params':{'threadId':params['threadId'],'turn':{'id':'fixture-turn'}}})
            send({'method':'item/agentMessage/delta','params':{'threadId':params['threadId'],'turnId':'fixture-turn','delta':'Early fixture. '}})
        send({'id': ident, 'result': {'turn': {'id': 'fixture-turn', 'status': 'inProgress'}}})
        if os.environ.get('FIXTURE_LATE'):
            send({'method':'turn/started','params':{'threadId':params['threadId'],'turn':{'id':'old-turn'}}})
            send({'method':'item/agentMessage/delta','params':{'threadId':params['threadId'],'turnId':'old-turn','delta':'old'}})
            send({'method':'turn/completed','params':{'threadId':params['threadId'],'turn':{'id':'old-turn','status':'completed'}}})
            send({'method':'turn/completed','params':{'threadId':'wrong-thread','turn':{'id':'fixture-turn','status':'completed'}}})
        if os.environ.get('FIXTURE_TURN_ERROR'):
            send({'method':'turn/completed','params':{'threadId':params['threadId'],'turn':{'id':'fixture-turn','status':'failed','error':{'codexErrorInfo':'other','message':'The model is not supported for a ChatGPT account. Authorization: Bearer fixture-secret /private/fixture'}}}})
            continue
        if os.environ.get('FIXTURE_HANG'):continue
        request = os.environ.get('FIXTURE_REQUEST') or ('item/commandExecution/requestApproval' if os.environ.get('FIXTURE_APPROVAL') else '')
        if request:
            send({'id': 'approval-1', 'method': request, 'params': {'threadId': 'wrong' if os.environ.get('FIXTURE_WRONG_APPROVAL_THREAD') else params['threadId'], 'turnId':'fixture-turn', 'command':'fixture'}})
        else:
            send({'method': 'item/agentMessage/delta', 'params': {'threadId': params['threadId'], 'turnId': 'fixture-turn', 'itemId': 'one', 'delta': 'Finished fixture.'}})
            send({'method': 'turn/completed', 'params': {'threadId': params['threadId'], 'turn': {'id':'fixture-turn', 'status': 'completed'}}})
    elif ident == 'approval-1':
        request = os.environ.get('FIXTURE_REQUEST', 'item/commandExecution/requestApproval')
        if request in ('item/commandExecution/requestApproval', 'item/fileChange/requestApproval'):
            assert m['result']['decision'] == ('accept' if os.environ.get('FIXTURE_ACCEPT') else 'cancel')
        elif request == 'item/permissions/requestApproval': assert m['result']['permissions'] == {}
        elif request == 'item/tool/requestUserInput': assert m['result']['answers'] == {}
        else: assert m['error']['code'] == -32601
        if os.environ.get('FIXTURE_ACCEPT'):
            send({'method':'item/agentMessage/delta','params':{'threadId':'fixture-thread','turnId':'fixture-turn','itemId':'one','delta':'Approved fixture.'}})
        send({'method': 'turn/completed', 'params': {'threadId': 'fixture-thread', 'turn': {'id':'fixture-turn', 'status': 'completed' if os.environ.get('FIXTURE_ACCEPT') else 'interrupted'}}})
    elif method == 'turn/interrupt':
        if os.environ.get('FIXTURE_INTERRUPT_DISCONNECT'): sys.exit(0)
        if os.environ.get('FIXTURE_INTERRUPT_NO_ACK'): continue
        if os.environ.get('FIXTURE_INTERRUPT_DELAY'): time.sleep(.3)
        send({'id': ident, 'result': {}})
        status = 'completed' if os.environ.get('FIXTURE_INTERRUPT_RACE') else 'interrupted'
        send({'method': 'turn/completed', 'params': {'threadId': params['threadId'], 'turn': {'id':params['turnId'], 'status': status}}})
