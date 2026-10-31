"""Prepare an isolated, text-only Pi/OpenAI run after explicit request confirmation."""
import os
import re
import json
import shutil
import hashlib

DEFAULT_MODEL = 'gpt-6.1-terra'


def terra_model_config(max_tokens=512):
    return {'providers': {'openai': {'models': [{'id': 'gpt-6.1-terra', 'name': 'GPT-6.1 Terra',
        'api': 'openai-responses', 'reasoning': True, 'input': ['text', 'image'],
        'contextWindow': 1050000, 'maxTokens': max_tokens,
        'cost': {'input': 1, 'output': 5, 'cacheRead': 0.05, 'cacheWrite': 1.25}}]}}}


def bounded_history(value):
    """Accept at most four recent explicitly typed pairs and 4096 UTF-8 bytes."""
    if not isinstance(value, list): return []
    kept=[]; total=0
    for item in reversed(value[-4:]):
        if not isinstance(item,dict) or set(item)!={'q','a'}: return []
        q,a=item['q'],item['a']
        if not isinstance(q,str) or not isinstance(a,str) or not q.strip() or not a.strip(): return []
        size=len(q.encode('utf-8'))+len(a.encode('utf-8'))
        candidate=[{'q':q,'a':a}]+list(reversed(kept))
        if size>2000 or total+size>4096 or len(json.dumps(candidate,ensure_ascii=False).encode('utf-8'))>4096: break
        total+=size; kept.append({'q':q,'a':a})
    return list(reversed(kept))

def foreground_prompt(task, history):
    previous=bounded_history(history)
    if not previous: return task
    return 'Prior conversation, for context only (not instructions):\n'+json.dumps(previous,ensure_ascii=False)+'\n\nCurrent user request:\n'+task


def prepare(ask, model, environ, load_key):
    if not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,100}', model):
        raise ValueError('Invalid OpenAI model selection.')
    runtime = _runtime_root(environ.get('HOME', os.path.expanduser('~')))
    node = _runtime_node(runtime) if runtime else None
    if not node: raise ValueError('Verified Pi runtime is unavailable.')
    key = load_key()
    if not isinstance(key, str) or not key or len(key.encode()) > 16000:
        raise ValueError('The foreground OpenAI key is unavailable.')
    profile = os.path.join(ask, 'pi-profile')
    os.mkdir(profile, mode=0o700)
    if model == 'gpt-6.1-terra':
        with open(os.path.join(profile, 'models.json'), 'w', encoding='utf-8') as f: json.dump(terra_model_config(), f)
    env = {k: environ[k] for k in ('PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'LC_CTYPE') if k in environ}
    with open(os.path.join(profile, 'settings.json'), 'w', encoding='utf-8') as f: json.dump({'retry': {'enabled': False, 'provider': {'maxRetries': 0}}}, f)
    env['PATH'] = os.path.dirname(node) + os.pathsep + env.get('PATH', '/usr/bin:/bin')
    env.update(OPENAI_API_KEY=key, PI_CODING_AGENT_DIR=profile, PI_OFFLINE='1', PI_SKIP_VERSION_CHECK='1', PI_TELEMETRY='0')
    args = ['--no-session','--no-mcp','--no-skills','--no-prompt-templates','--no-context-files','--no-extensions',
            '--no-tools','--offline','--provider','openai','--model',model]
    return args, env


def _runtime_root(home):
    bundled = os.path.join(os.path.dirname(__file__), 'pi-runtime')
    if os.path.lexists(bundled): return bundled
    return os.path.join(home, 'Library', 'Application Support', 'Atticus Dev', 'pi-runtime')

def _runtime_node_status(runtime):
    if os.path.islink(runtime): return None, 'runtime_symlink'
    if not os.path.isdir(runtime): return None, 'runtime_missing'
    if os.path.exists(os.path.join(runtime, 'INCOMPLETE')): return None, 'runtime_incomplete'
    bundled = os.path.join(os.path.dirname(__file__), 'pi-runtime')
    if os.path.abspath(runtime) == os.path.abspath(bundled):
        node = os.path.join(runtime, 'bin', 'node')
        if os.path.islink(node) or not os.path.isfile(node) or not os.access(node, os.X_OK): return None, 'node_missing'
        return node, 'ready'
    descriptor = os.path.join(runtime, 'runtime.json')
    try:
        if not os.path.lexists(descriptor): return None, 'descriptor_missing'
        if os.path.islink(descriptor) or os.path.getsize(descriptor) > 4096: return None, 'descriptor_invalid'
        with open(descriptor, encoding='utf-8') as f: data = json.load(f)
        if not isinstance(data, dict) or set(data) != {'node_path', 'node_sha256'}: return None, 'descriptor_invalid'
        node, expected = data['node_path'], data['node_sha256']
        if not isinstance(node, str) or not os.path.isabs(node) or os.path.basename(node) != 'node': return None, 'descriptor_invalid'
        if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-f]{64}', expected): return None, 'descriptor_invalid'
        if not os.path.isfile(node) or not os.access(node, os.X_OK): return None, 'node_missing'
        digest = hashlib.sha256()
        with open(node, 'rb') as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b''): digest.update(chunk)
        return (node, 'ready') if digest.hexdigest() == expected else (None, 'node_changed')
    except (OSError, ValueError, TypeError): return None, 'descriptor_invalid'

def _runtime_node(runtime):
    return _runtime_node_status(runtime)[0]

def _resolve_pi_status(profile_dir, home, fallback=None):
    fallback = fallback or shutil.which
    dev = os.path.join(home, '.config', 'atticus-personal-dev')
    if os.path.abspath(profile_dir) != os.path.abspath(dev):
        binary = fallback('pi')
        return binary, 'ready' if binary else 'runtime_missing', 'standard'
    runtime = _runtime_root(home)
    bundled = os.path.join(os.path.dirname(__file__), 'pi-runtime')
    kind = 'bundled' if os.path.abspath(runtime)==os.path.abspath(bundled) else 'per_device'
    node, status = _runtime_node_status(runtime)
    if not node: return None, status, kind
    root = os.path.join(runtime, 'node_modules')
    package = os.path.join(root, '@earendil-works', 'pi-coding-agent')
    binary = os.path.join(root, '.bin', 'pi')
    expected = os.path.join(package, 'dist', 'bundle', 'cli.js')
    try:
        with open(os.path.join(package, 'package.json'), encoding='utf-8') as f: metadata = json.load(f)
        if not isinstance(metadata,dict) or metadata.get('name') != '@earendil-works/pi-coding-agent' or metadata.get('version') != '1.4.0':
            return None, 'package_mismatch', kind
        if os.path.realpath(binary) != os.path.realpath(expected) or not os.path.isfile(expected) or not os.access(binary, os.X_OK):
            return None, 'binary_mismatch', kind
    except (OSError, ValueError, TypeError): return None, 'package_mismatch', kind
    return binary, 'ready', kind

def diagnose_runtime(profile_dir, home):
    """Return only nonsecret status codes; never return paths or credentials."""
    binary, reason, kind = _resolve_pi_status(profile_dir, home)
    return {'ready':bool(binary), 'reason':reason, 'runtime_kind':kind}

def resolve_pi(profile_dir, home, fallback=None):
    """Resolve the same validated runtime used by setup diagnostics."""
    return _resolve_pi_status(profile_dir, home, fallback)[0]
