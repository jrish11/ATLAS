"""Pure policy for an owner-authorized, short-lived autonomy session.

The native owner must supply verified targets and a fresh per-run token. This module
cannot activate sessions, access apps, or execute actions.
"""
import hashlib
import hmac
import json
import math
import re
import secrets

MAX_SECONDS = 900
ACTIONS = {'open_app': 'app', 'focus_app': 'app', 'open_url': 'destination'}
BUNDLE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+$')
HEX = re.compile(r'^[0-9a-f]{64}$')


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def create(run_id, targets, now, expires, confirmed=False):
    if confirmed is not True: raise ValueError('Owner confirmation required.')
    if not isinstance(run_id, str) or not HEX.fullmatch(run_id): raise ValueError('Invalid run identity.')
    if type(now) not in (int, float) or type(expires) not in (int, float) or not math.isfinite(now) or not math.isfinite(expires) or not 0 < expires-now <= MAX_SECONDS: raise ValueError('Invalid session duration.')
    if not isinstance(targets, list) or not 1 <= len(targets) <= 20: raise ValueError('Choose one or more targets.')
    seen=set(); checked=[]
    for t in targets:
        if not isinstance(t,dict) or set(t)!={'type','id','revision'} or not isinstance(t['type'],str) or t['type'] not in ('app','destination') or not isinstance(t['id'],str) or not 0 < len(t['id']) <= 200 or not isinstance(t['revision'],str) or not HEX.fullmatch(t['revision']): raise ValueError('Invalid target.')
        if t['type']=='app' and not BUNDLE.fullmatch(t['id']): raise ValueError('Invalid app identifier.')
        key=(t['type'],t['id'])
        if key in seen: raise ValueError('Duplicate target.')
        seen.add(key); checked.append(dict(t))
    return {'version':1,'run_id':run_id,'session_id':secrets.token_hex(32),'expires':expires,'targets':checked,'revoked':False}


def permitted(session, run_id, action, target, now):
    if not isinstance(session,dict) or set(session)!={'version','run_id','session_id','expires','targets','revoked'}: return False
    if session['version']!=1 or session['revoked'] is not False or not isinstance(run_id,str) or not isinstance(session['run_id'],str) or not hmac.compare_digest(session['run_id'],run_id): return False
    expiry=session['expires']
    if type(now) not in (int,float) or type(expiry) not in (int,float) or not math.isfinite(now) or not math.isfinite(expiry) or now>=expiry or expiry-now>MAX_SECONDS: return False
    if not isinstance(action,str) or action not in ACTIONS or not isinstance(target,dict) or set(target)!={'type','id','revision'} or target.get('type')!=ACTIONS[action]: return False
    return isinstance(session['targets'],list) and any(isinstance(t,dict) and t==target for t in session['targets'])


def revoke(session):
    return dict(session, revoked=True)


def serialized_dispatch(lock, read_state, run_id, action, target, now, dispatch, audit):
    """Call only while holding a shared session lock across check and dispatch.

    A stop takes the same lock to revoke. Work waiting behind stop cannot dispatch;
    work already inside dispatch has already crossed the authorization boundary.
    """
    with lock:
        state = read_state()
        if not permitted(state, run_id, action, target, now()):
            audit('blocked', action, fingerprint(target)); return False
        audit('dispatch', action, fingerprint(target))
        dispatch()
        return True


def serialized_revoke(lock, read_state, write_state, audit):
    with lock:
        current=read_state()
        if not isinstance(current,dict): return False
        write_state(revoke(current)); audit('revoked', '', '')
        return True

# The store is per app run; all mutations and dispatches use one cross-process lock.
class SessionStore:
    def __init__(self, directory, run_id):
        import os
        if not isinstance(run_id,str) or not HEX.fullmatch(run_id): raise ValueError('Invalid app run.')
        self.directory=directory; self.run_id=run_id
        self.path=os.path.join(directory,'autonomy-'+run_id+'.json')
        self.lock_path=os.path.join(directory,'autonomy-'+run_id+'.lock')
        self.audit_path=os.path.join(directory,'autonomy-audit.jsonl')
        self.stop_path=os.path.join(directory,'autonomy-'+run_id+'.stopped')
    def locked(self):
        import fcntl, os
        class Lock:
            def __enter__(inner):
                fd=os.open(self.lock_path,os.O_CREAT|os.O_RDWR|getattr(os,'O_NOFOLLOW',0),0o600)
                inner.f=os.fdopen(fd,'r+'); fcntl.flock(fd,fcntl.LOCK_EX); return inner
            def __exit__(inner,*args): inner.f.close()
        return Lock()
    def read(self):
        import os
        try:
            fd=os.open(self.path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
            with os.fdopen(fd) as f: return json.load(f)
        except (OSError,ValueError): return None
    def write(self, state):
        import os, tempfile
        fd,p=tempfile.mkstemp(prefix='.autonomy-',dir=self.directory)
        try:
            with os.fdopen(fd,'w') as f:
                os.fchmod(f.fileno(),0o600);json.dump(state,f);f.flush();os.fsync(f.fileno())
            os.replace(p,self.path)
        finally:
            if os.path.exists(p): os.unlink(p)
    def audit(self,event,action,target_hash):
        import os,time
        fd=os.open(self.audit_path,os.O_WRONLY|os.O_CREAT|os.O_APPEND|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'a') as f: f.write(json.dumps({'time':time.time(),'event':event,'action':action,'target_hash':target_hash})+'\n')
    def activate(self,targets,now,expires,confirmed):
        with self.locked():
            import os
            state=create(self.run_id,targets,now,expires,confirmed);self.write(state)
            try: os.unlink(self.stop_path)
            except FileNotFoundError: pass
            self.audit('activated','','')
    def stop(self):
        import os
        fd=os.open(self.stop_path,os.O_CREAT|os.O_WRONLY|getattr(os,'O_NOFOLLOW',0),0o600);os.close(fd)
        return serialized_revoke(self.locked(),self.read,self.write,self.audit)
    def dispatch(self,action,target,clock,callback):
        import os
        initial=self.read()
        def current():
            state=self.read()
            return state if not os.path.lexists(self.stop_path) and state == initial else None
        return serialized_dispatch(self.locked(),current,self.run_id,action,target,clock,callback,self.audit)
