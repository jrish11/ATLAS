"""Small Codex app-server adapter, using JSONL stdio and no credential handling.

One instance owns one thread/turn at a time. Its caller owns persistence and UI.
No server-requested permission is granted by this adapter.
"""
import json
import os
import stat
import queue
import re
import subprocess
import threading
import time
import uuid


class ProviderError(Exception):
    pass


def classify_turn_error(error):
    """Return fixed, non-sensitive diagnostics; never echo provider text or paths."""
    if not isinstance(error, dict):
        return 'unknown', 'Codex reported a failed turn without a diagnostic category.'
    info = error.get('codexErrorInfo')
    code = info if isinstance(info, str) else next(iter(info), '') if isinstance(info, dict) and len(info) == 1 else ''
    messages = {
        'contextWindowExceeded': ('context_limit', 'Codex could not complete the turn because its context limit was exceeded.'),
        'sessionBudgetExceeded': ('session_budget', 'Codex stopped because the session budget was exceeded.'),
        'usageLimitExceeded': ('usage_limit', 'Codex reported that the account usage limit was reached.'),
        'rateLimitExceeded': ('rate_limit', 'Codex reported a rate limit.'),
        'serverOverloaded': ('service_overloaded', 'Codex reported that the service is overloaded.'),
        'unauthorized': ('authentication', 'Codex could not authorize the account or model request.'),
        'badRequest': ('invalid_request', 'Codex rejected the request as invalid.'),
        'sandboxError': ('sandbox', 'Codex could not start or use the requested sandbox.'),
        'httpConnectionFailed': ('connection', 'Codex could not connect to the service.'),
        'responseStreamConnectionFailed': ('connection', 'Codex could not establish the response stream.'),
        'responseStreamDisconnected': ('connection', 'The Codex response stream disconnected.'),
        'responseTooManyFailedAttempts': ('connection', 'Codex could not complete the response after connection failures.'),
        'cyberPolicy': ('policy', 'Codex declined the request under a safety policy.'),
        'misalignmentPolicyViolation': ('policy', 'Codex declined the request under a safety policy.'),
    }
    # A generic protocol category can carry a more useful non-secret model mismatch.
    message = error.get('message')
    if isinstance(message, str) and re.search(r'\bmodel\b', message, re.I) and re.search(r'not supported|unsupported|not available|unavailable', message, re.I):
        if re.search(r'chatgpt', message, re.I):
            return 'model_unavailable_account', 'The selected Codex model is not supported for the current ChatGPT account.'
        return 'model_unavailable', 'The selected Codex model is not available for this request.'
    return messages.get(code, ('unknown', 'Codex reported a failed turn; no safe diagnostic category was available.'))


class CodexProvider:
    def __init__(self, executable='codex', popen=subprocess.Popen, emit=None, auth_mode='existing', api_key_resolver=None, approval_handler=None, turn_timeout=600):
        if type(turn_timeout) not in (int,float) or not 1 <= turn_timeout <= 3600:raise ValueError('Turn timeout must be between 1 and 3600 seconds.')
        self.turn_timeout = turn_timeout
        self.executable, self.popen = executable, popen
        self.auth_mode, self.api_key_resolver = auth_mode, api_key_resolver
        self.approval_handler = approval_handler
        self.profile = 'atticus_' + uuid.uuid4().hex
        self.emit = emit or (lambda event: None)
        self.process = None
        self.thread_id = self.turn_id = None
        self._messages = queue.Queue()
        self._write_lock = threading.RLock()
        self._sequence = 0
        self._stopped = False
        self._scope_binding = None
        self.approval_denied = False
        self.text = ''
        self._completed = None
        self._early_turn_events = []
        self._turn_started_emitted = False

    def _send(self, payload):
        with self._write_lock:
            if payload.get('method') in ('thread/start', 'thread/resume', 'turn/start'):
                if self._stopped: raise ProviderError('Codex task was cancelled before dispatch.')
                self._verify_project()
            if not self.process or self.process.poll() is not None:
                raise ProviderError('Codex app-server stopped.')
            try:
                self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + '\n')
                self.process.stdin.flush()
            except (OSError, ValueError) as e:
                raise ProviderError('Could not communicate with Codex app-server.') from e

    def _reader(self, process, messages):
        try:
            for line in process.stdout:
                try: message = json.loads(line)
                except (ValueError, TypeError): continue
                if isinstance(message, dict): messages.put(message)
        finally:
            messages.put(None)

    def _launch(self, environment, override=None):
        self._messages = queue.Queue()
        args = [self.executable, 'app-server', '--disable', 'hooks', '--disable', 'plugins',
                '--disable', 'apps', '--disable', 'skill_search', '--disable', 'remote_plugin',
                '--disable', 'skill_mcp_dependency_install', '--disable', 'shell_snapshot']
        profile = 'permissions.' + self.profile
        args += ['-c', profile + '.filesystem={":minimal"="read",":workspace_roots"="write","/Library/Developer/CommandLineTools"="read"}',
                 '-c', profile + '.network.enabled=false', '-c', 'default_permissions=' + json.dumps(self.profile), '-c', 'allow_login_shell=false',
                 '-c', 'shell_environment_policy.inherit="none"', '-c', 'shell_environment_policy.ignore_default_excludes=false',
                 '-c', 'web_search="disabled"', '-c', 'apps._default.enabled=false']
        if override:
            for item in ([override] if isinstance(override, str) else override): args += ['-c', item]
        with self._write_lock:
            if self._stopped: raise ProviderError('Codex task was cancelled before launch.')
            if self._scope_binding is not None: self._verify_project()
            self.process = self.popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True, bufsize=1, env=environment)
        threading.Thread(target=self._reader, args=(self.process, self._messages), daemon=True).start()
        self._request('initialize', {'clientInfo': {'name': 'atticus', 'version': '0.1.0'}, 'capabilities': {'experimentalApi': True}})
        self._send({'method': 'initialized', 'params': {}})

    def _preflight(self, cwd):
        effective = self._request('config/read', {'cwd': cwd, 'includeLayers': False})
        settings = effective.get('config')
        if not isinstance(settings, dict) or not isinstance(settings.get('mcp_servers'), dict):
            raise ProviderError('Codex configuration could not be verified; no task was started.')
        servers = settings['mcp_servers']
        if any(not isinstance(value, dict) or value.get('enabled') is not False for value in servers.values()):
            raise ProviderError('Configured MCP servers are not disabled; no task was started.')
        # The inventory can include disabled entries; none may expose tools or resources.
        inventory = self._request('mcpServerStatus/list', {'detail':'toolsAndAuthOnly','limit':100})
        rows = inventory.get('data')
        if not isinstance(rows, list) or inventory.get('nextCursor'):
            raise ProviderError('Codex MCP tool inventory could not be verified; no task was started.')
        found = set()
        for row in rows:
            if (not isinstance(row, dict) or not isinstance(row.get('name'), str) or row['name'] in found or
                    row['name'] not in servers or row.get('runtimeStatus') not in (None,'disabled') or
                    row.get('tools') != {} or row.get('resources') != [] or row.get('resourceTemplates') != [] or
                    row.get('toolsError') is not None):
                raise ProviderError('Codex MCP tool inventory was not empty; no task was started.')
            found.add(row['name'])
        if found != set(servers):
            raise ProviderError('Codex MCP tool inventory was incomplete; no task was started.')
        apps = settings.get('apps')
        if (not isinstance(apps, dict) or not isinstance(apps.get('_default'), dict) or
                apps['_default'].get('enabled') is not False or
                any(not isinstance(value, dict) or (value.get('enabled') is not None and value.get('enabled') is not False)
                    for key, value in apps.items() if key != '_default')):
            raise ProviderError('Codex app restrictions could not be verified; no task was started.')
        profile = (settings.get('permissions') or {}).get(self.profile)
        if not isinstance(profile, dict) or settings.get('default_permissions') != self.profile:
            raise ProviderError('Codex permission profile could not be verified; no task was started.')
        filesystem = profile.get('filesystem')
        network = profile.get('network')
        expected_fs = {':minimal':'read', ':workspace_roots':'write', '/Library/Developer/CommandLineTools':'read'}
        if (profile.get('extends') is not None or profile.get('workspace_roots') is not None or
                not isinstance(filesystem, dict) or {k:v for k,v in filesystem.items() if k != 'glob_scan_max_depth'} != expected_fs or
                not isinstance(network, dict) or network.get('enabled') is not False or
                any(value not in (None, False, {}, []) for key, value in network.items() if key != 'enabled')):
            raise ProviderError('Codex permission profile could not be verified; no task was started.')
        features = settings.get('features')
        shell = settings.get('shell_environment_policy')
        disabled = ('hooks', 'plugins', 'apps', 'skill_search', 'remote_plugin', 'skill_mcp_dependency_install', 'shell_snapshot')
        if (not isinstance(features, dict) or any(features.get(name) is not False for name in disabled) or
                settings.get('web_search') != 'disabled' or settings.get('allow_login_shell') is not False or
                not isinstance(shell, dict) or shell.get('inherit') != 'none' or shell.get('ignore_default_excludes') is not False):
            raise ProviderError('Codex effective safety settings could not be verified; no task was started.')
        enabled = []
        for method, field in (('hooks/list', 'hooks'), ('skills/list', 'skills')):
            params = {'cwds': [cwd]}
            if field == 'skills': params['forceReload'] = True
            rows = self._request(method, params).get('data')
            if not isinstance(rows, list) or not rows:
                raise ProviderError('Codex ' + field + ' could not be verified; no task was started.')
            for row in rows:
                if not isinstance(row, dict) or row.get('errors') or not isinstance(row.get(field), list):
                    raise ProviderError('Codex ' + field + ' could not be verified; no task was started.')
                for item in row[field]:
                    if field == 'hooks': raise ProviderError('Inherited Codex hooks are not approved; no task was started.')
                    if not isinstance(item, dict) or type(item.get('enabled')) is not bool:
                        raise ProviderError('Codex skills could not be verified; no task was started.')
                    if item['enabled']:
                        path = item.get('path')
                        if not isinstance(path, str) or not os.path.isabs(path) or not path.endswith('/SKILL.md'):
                            raise ProviderError('Codex skill paths could not be verified; no task was started.')
                        enabled.append(path)
        if self.approval_denied:
            raise ProviderError('Codex made an unexpected request before task start; no task was started.')
        return sorted(set(enabled))

    def _request(self, method, params, timeout=30):
        self._sequence += 1
        request_id = self._sequence
        self._send({'id': request_id, 'method': method, 'params': params})
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise ProviderError('Codex app-server did not respond to ' + method + '.')
            message = self._next(remaining)
            if type(message.get('id')) is int and message.get('id') == request_id and 'method' not in message:
                if 'error' in message: raise ProviderError('Codex rejected ' + method + '.')
                result = message.get('result')
                if not isinstance(result, dict): raise ProviderError('Codex returned an invalid ' + method + ' response.')
                return result
            # Notifications can precede turn/start's response.  Until that
            # response establishes the turn ID, no notification may select it.
            if (method == 'turn/start' and 'id' not in message and
                    message.get('method') in ('turn/started','turn/completed','item/agentMessage/delta')):
                if len(self._early_turn_events) >= 1024:
                    raise ProviderError('Too many early Codex events; no result was accepted.')
                self._early_turn_events.append(message)
            else:
                self._handle(message)

    def _next(self, timeout=None):
        try: message = self._messages.get(timeout=timeout)
        except queue.Empty as e: raise ProviderError('Codex app-server timed out.') from e
        if message is None: raise ProviderError('Codex app-server stopped before the task finished.')
        return message

    def _handle(self, message):
        if not isinstance(message, dict): return None
        method, raw = message.get('method'), message.get('params')
        params = raw if isinstance(raw, dict) else {}
        if isinstance(method, str) and 'id' in message:
            if type(message['id']) not in (str, int): return None
            # Server requests are denied unless both identifiers match an active turn.
            if method in ('item/commandExecution/requestApproval', 'item/fileChange/requestApproval'):
                decision = 'cancel'
                if (isinstance(raw, dict) and self.approval_handler and not self._stopped and
                        self._completed is None and isinstance(self.thread_id, str) and self.thread_id and
                        isinstance(self.turn_id, str) and self.turn_id and
                        params.get('threadId') == self.thread_id and params.get('turnId') == self.turn_id):
                    try: choice = self.approval_handler({'id':message['id'], 'method':method, 'params':params})
                    except Exception: choice = 'cancel'
                    if isinstance(choice, str) and choice in ('accept', 'decline', 'cancel'): decision = choice
                if decision != 'accept':
                    self.approval_denied = True; self.emit({'type': 'approval_denied', 'method': method})
                result = {'decision': decision}
            elif method == 'item/permissions/requestApproval':
                self.approval_denied = True; self.emit({'type': 'approval_denied', 'method': method})
                result = {'permissions': {}}
            elif method == 'item/tool/requestUserInput':
                self.approval_denied = True; self.emit({'type': 'approval_denied', 'method': method})
                result = {'answers': {}}
            else:
                self.approval_denied = True; self.emit({'type': 'approval_denied', 'method': method})
                self._send({'id': message['id'], 'error': {'code': -32601, 'message': 'Unsupported request; no permission granted.'}})
                return None
            with self._write_lock:
                if result.get('decision') == 'accept' and (self._stopped or self._completed is not None or params.get('threadId') != self.thread_id or params.get('turnId') != self.turn_id):
                    result = {'decision':'cancel'}
                    self.approval_denied = True
                    self.emit({'type':'approval_denied','method':method})
                self._send({'id': message['id'], 'result': result})
        elif (isinstance(raw, dict) and isinstance(self.thread_id, str) and self.thread_id and
              isinstance(self.turn_id, str) and self.turn_id and params.get('threadId') == self.thread_id and
              self._completed is None):
            if method == 'item/agentMessage/delta' and params.get('turnId') == self.turn_id:
                delta = params.get('delta')
                if isinstance(delta, str):
                    self.text += delta; self.emit({'type': 'text', 'text': delta})
            elif method in ('turn/started', 'turn/completed'):
                turn = params.get('turn')
                if not isinstance(turn, dict) or turn.get('id') != self.turn_id: return None
                if method == 'turn/started':
                    if not self._turn_started_emitted:
                        self._turn_started_emitted = True; self.emit({'type': 'turn', 'id': self.turn_id})
                else:
                    if turn.get('status') not in ('completed', 'interrupted', 'failed'): return None
                    self._completed = turn
                    return turn
        return None

    @staticmethod
    def validate_scope(cwd):
        if not isinstance(cwd,str) or not os.path.isabs(cwd) or not os.path.isdir(cwd):
            raise ProviderError('Choose an existing absolute project folder before starting Codex.')
        home=os.path.expanduser('~')
        protected=[os.path.join(home,p) for p in ('.codex','.ssh','.aws','.gnupg','.config/atticus','.config/atticus-personal-dev','Library/Keychains')]
        protected += [p for p in (os.environ.get('CODEX_HOME'),os.environ.get('ATTICUS_DIR')) if isinstance(p,str) and p]
        protected.append(os.path.dirname(os.path.abspath(__file__)))
        for normalize in (os.path.abspath,os.path.realpath):
            project=normalize(cwd);owner=normalize(home)
            if os.path.commonpath((project,owner))==project:
                raise ProviderError('The project must not contain the home directory or account state.')
            dev_root=normalize(os.path.join(home,'.config','atticus-personal-dev'))
            managed_root=os.path.join(dev_root,'workspaces')
            task_name=os.path.basename(project)
            managed_ok=(os.path.dirname(project)==managed_root and
                        re.fullmatch(r'task-[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}',task_name) is not None and
                        normalize(os.environ.get('ATTICUS_DIR',''))==dev_root and os.path.realpath(cwd)==os.path.abspath(cwd))
            for path in protected:
                path=normalize(os.path.expanduser(path))
                if managed_ok and path==dev_root: continue
                if os.path.commonpath((project,path)) in (project,path):
                    raise ProviderError('The project overlaps protected account or Atticus state.')
        return os.path.realpath(cwd)

    def _verify_project(self):
        binding = self._scope_binding
        if not binding: raise ProviderError('No confirmed project identity; no task was started.')
        path, device, inode = binding
        try:
            info = os.stat(path, follow_symlinks=False)
            if os.path.realpath(path) != path or not stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != (device, inode):
                raise ProviderError('The confirmed project folder changed or is unavailable.')
        except (OSError, ValueError, TypeError) as exc:
            raise ProviderError('The confirmed project folder changed or is unavailable.') from exc

    def run(self, cwd, task, thread_id=None, expected_identity=None):
        scoped = self.validate_scope(cwd)
        if not isinstance(task, str) or not task.strip(): raise ProviderError('A task description is required.')
        try:
            info = os.stat(scoped, follow_symlinks=False)
        except OSError as exc: raise ProviderError('The confirmed project folder is unavailable.') from exc
        if expected_identity is None: expected_identity = {'device':info.st_dev, 'inode':info.st_ino}
        if not isinstance(expected_identity,dict) or set(expected_identity) != {'device','inode'} or any(type(expected_identity[k]) is not int for k in expected_identity):
            raise ProviderError('The confirmed project identity is invalid.')
        self._scope_binding = (scoped, expected_identity['device'], expected_identity['inode'])
        with self._write_lock:
            if self._stopped: raise ProviderError('Codex task was cancelled before launch.')
            self._verify_project()
        try:
            if self.auth_mode not in ('existing', 'api_key'):
                raise ProviderError('Choose an available Codex authentication mode.')
            environment = os.environ.copy()
            for name in list(environment):
                if re.search(r'(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD)$', name, re.I): environment.pop(name, None)
            if self.auth_mode == 'api_key':
                if not self.api_key_resolver: raise ProviderError('No Codex API key is configured.')
                try: key = self.api_key_resolver()
                except Exception as e: raise ProviderError('The Codex API key is unavailable.') from e
                if not isinstance(key, str) or not key: raise ProviderError('The Codex API key is unavailable.')
                environment['OPENAI_API_KEY'] = key
            self._launch(environment)
            # Discover configured server keys without starting a thread, then
            # disable them in this child process only. Unsafe keys fail closed.
            initial = self._request('config/read', {'cwd':os.path.realpath(cwd), 'includeLayers':False})
            settings = initial.get('config')
            servers = settings.get('mcp_servers') if isinstance(settings, dict) else None
            if not isinstance(servers, dict) or len(servers) > 100 or any(not isinstance(k,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',k) for k in servers):
                raise ProviderError('Inherited MCP server names could not be safely scoped; no task was started.')
            apps = settings.get('apps')
            if not isinstance(apps, dict) or len(apps) > 100 or any(not isinstance(k,str) or not re.fullmatch(r'[A-Za-z0-9_-]+',k) for k in apps):
                raise ProviderError('Inherited app settings could not be safely scoped; no task was started.')
            overrides = ['mcp_servers.' + name + '.enabled=false' for name in sorted(servers)]
            overrides += ['apps.' + name + '.enabled=false' for name in sorted(apps) if name != '_default']
            if overrides:
                self.close(); self._launch(environment, overrides)
            enabled_skills = self._preflight(os.path.realpath(cwd))
            with self._write_lock:
                if self._stopped: raise ProviderError('Codex task was cancelled before launch.')
                self._verify_project()
            if enabled_skills:
                # These overrides belong only to this child process.
                overrides.append('skills.config=[' + ','.join('{path=' + json.dumps(path) + ',enabled=false}' for path in enabled_skills) + ']')
                self.close(); self._launch(environment, overrides)
                if self._preflight(os.path.realpath(cwd)):
                    raise ProviderError('Inherited Codex skills remain enabled; no task was started.')
                with self._write_lock:
                    if self._stopped: raise ProviderError('Codex task was cancelled before launch.')
                    self._verify_project()
            # Select the account picker's explicit default rather than inheriting
            # an unrelated global model. Listing is not proof of entitlement.
            if self.auth_mode == 'existing':
                account = self._request('account/read', {'refreshToken':False}).get('account')
                if not isinstance(account, dict) or account.get('type') != 'chatgpt':
                    raise ProviderError('Sign in to Codex with the existing ChatGPT account before starting a task.')
            listing = self._request('model/list', {'includeHidden':False, 'limit':100})
            models = listing.get('data')
            if not isinstance(models, list) or listing.get('nextCursor'):
                raise ProviderError('The Codex account default model could not be verified; no task was started.')
            defaults = [m for m in models if isinstance(m, dict) and m.get('isDefault') is True and m.get('hidden') is not True]
            model = defaults[0].get('model') if len(defaults) == 1 else None
            if not isinstance(model,str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,128}',model):
                raise ProviderError('The Codex account default model could not be verified; no task was started.')
            scoped = os.path.realpath(cwd)
            config = {'cwd': scoped, 'runtimeWorkspaceRoots': [scoped], 'permissions': self.profile,
                      'approvalPolicy': 'on-request', 'approvalsReviewer': 'user', 'model':model}
            if thread_id: config['threadId'] = thread_id
            reply = self._request('thread/resume' if thread_id else 'thread/start', config)
            if ((reply.get('activePermissionProfile') or {}).get('id') != self.profile or
                    reply.get('runtimeWorkspaceRoots') != [scoped] or reply.get('approvalPolicy') != 'on-request' or
                    reply.get('approvalsReviewer') != 'user'):
                raise ProviderError('Codex did not confirm the requested sandbox and approval scope; no turn was started.')
            thread = reply.get('thread') or {}
            if not isinstance(thread, dict) or thread.get('model') != model:
                raise ProviderError('Codex did not confirm the account default model; no turn was started.')
            self.thread_id = thread.get('id')
            if not isinstance(self.thread_id, str) or not self.thread_id: raise ProviderError('Codex did not return a thread identifier.')
            self.emit({'type': 'thread', 'id': self.thread_id})
            turn = self._request('turn/start', {'threadId': self.thread_id, 'input': [{'type': 'text', 'text': task, 'text_elements': []}]})
            started = turn.get('turn') if isinstance(turn, dict) else None
            identifier = started.get('id') if isinstance(started, dict) else None
            if not isinstance(identifier, str) or not identifier:
                raise ProviderError('Codex did not confirm the active turn; no result was accepted.')
            self.turn_id = identifier
            self._turn_started_emitted = True
            self.emit({'type': 'turn', 'id': self.turn_id})
            for event in self._early_turn_events: self._handle(event)
            self._early_turn_events.clear()
            deadline = time.monotonic() + self.turn_timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.interrupt()
                    return {'status':'stopped','result':'Codex turn timed out; interruption is not confirmed. Inspect the project before retrying.','error_category':'timeout'}
                try:
                    completed = self._completed or self._handle(self._next(remaining))
                except ProviderError:
                    if time.monotonic() < deadline:raise
                    self.interrupt()
                    return {'status':'stopped','result':'Codex turn timed out; interruption is not confirmed. Inspect the project before retrying.','error_category':'timeout'}
                if completed is not None:
                    status = completed.get('status')
                    if self._stopped:
                        if status == 'completed':
                            return {'status': 'stopped', 'result': 'Cancellation was requested, but Codex reported the turn completed. Inspect the project for partial changes.', 'server_status': status}
                        if status == 'interrupted':
                            return {'status': 'stopped', 'result': 'Codex confirmed the turn was interrupted. Inspect the project for partial changes.', 'server_status': status}
                        return {'status': 'stopped', 'result': 'Cancellation was requested; Codex did not confirm interruption. Inspect the project for partial changes.', 'server_status': status}
                    if self.approval_denied: return {'status': 'failed', 'result': 'Codex requested approval; the request was not granted. Review it before retrying.'}
                    if status == 'completed': return {'status': 'done', 'result': self.text or 'Codex completed the turn without a text summary.'}
                    if status == 'interrupted': return {'status': 'stopped', 'result': 'Codex turn interrupted.'}
                    category, diagnostic = classify_turn_error(completed.get('error'))
                    return {'status': 'failed', 'result': diagnostic, 'error_category': category}
        except OSError as e:
            raise ProviderError('Could not start Codex app-server.') from e
        finally:
            self.close()

    def interrupt(self):
        with self._write_lock:
            self._stopped = True
        if self.thread_id and self.turn_id:
            try:
                self._sequence += 1
                self._send({'id': self._sequence, 'method': 'turn/interrupt',
                            'params': {'threadId': self.thread_id, 'turnId': self.turn_id}})
                return
            except ProviderError: pass
        self.close()

    def close(self):
        p = self.process
        if p:
            if p.poll() is None:
                try: p.terminate(); p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    p.kill(); p.wait(timeout=2)
                except OSError: pass
            for stream in (p.stdin, p.stdout):
                if stream:
                    try: stream.close()
                    except OSError: pass
