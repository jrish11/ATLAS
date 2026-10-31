"""In-memory remote request gate; inert until a trusted native bridge is integrated.

This module opens no socket and creates no credential. The experimental native
supervisor provides activation and the bridge only after owner confirmation.
"""
import hashlib
import hmac
import math
import re
import threading
import time
import approval_channel
from urllib.parse import urlsplit

_ID = re.compile(r'^[a-f0-9]{32}$')
MAX_TASK = 4000

class RemoteError(ValueError):
    pass

class NotDispatched(Exception):
    """Trusted bridge confirms it declined before committing any dispatch."""
    pass

class DispatchToken:
    """Linearizes Stop against the decision to commit one dispatch."""
    def __init__(self, deadline=None, wall_expiry=None, clock=None):
        self._lock=threading.Lock();self._cancelled=False;self._committed=False
        self.deadline=deadline;self.wall_expiry=wall_expiry;self._clock=clock or approval_channel.shared_clock
    def _expired(self):
        return ((self.deadline is not None and self._clock()>=self.deadline) or
                (self.wall_expiry is not None and time.time()>=self.wall_expiry))
    def set(self):
        with self._lock:self._cancelled=True
    def is_set(self):
        with self._lock:return self._cancelled or self._expired()
    def try_commit(self):
        with self._lock:
            if self._cancelled or self._committed or self._expired():return False
            self._committed=True;return True

def valid_origin(origin):
    if not isinstance(origin,str) or len(origin)>253 or any(c in origin for c in '\r\n\t'): return False
    try:
        u=urlsplit(origin); port=u.port
    except ValueError: return False
    if port is not None and not 1<=port<=65535: return False
    return (u.scheme=='https' and bool(u.hostname) and not u.username and not u.password and
            not u.path and not u.query and not u.fragment and u.netloc==u.netloc.lower() and
            bool(re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?',u.netloc)))

class RemoteGate:
    """Owner-supplied session and scope; no web request can enable or change either."""
    def __init__(self, clock=None, barrier=None):
        self._barrier=barrier
        self._clock=clock or approval_channel.shared_clock;self._lock=threading.RLock();self._session=None
        self._active=None;self._requests={};self._generation=0;self._used_tokens=set();self._unresolved={}

    def owner_enable(self, *, origin, token, csrf, scope, bridge, expires):
        # Called only by a future trusted native channel. No real bridge currently
        # implements this interface. Do not expose this method to a web client.
        if not valid_origin(origin): raise RemoteError('Invalid HTTPS origin.')
        if not all(isinstance(v,str) and 32<=len(v)<=256 and v.isascii() for v in (token,csrf)): raise RemoteError('Invalid session.')
        if not isinstance(scope,dict) or set(scope)!={'id','revision'} or not all(isinstance(v,str) and v for v in scope.values()): raise RemoteError('Invalid project scope.')
        if type(expires) not in (int,float) or not math.isfinite(expires) or not self._clock()<expires<=self._clock()+3600: raise RemoteError('Invalid session expiry.')
        if not all(callable(getattr(bridge,k,None)) for k in ('valid_scope','submit','cancel')): raise RemoteError('Native bridge unavailable.')
        digest=hashlib.sha256(token.encode('ascii')).digest()
        with self._lock:
            if self._session is not None or self._active is not None: raise RemoteError('Revoke the existing session first.')
            if self._unresolved: raise RemoteError('Review the previous task outcome before pairing again.')
            if self._barrier is not None:
                try: pending=self._barrier.read()
                except Exception as exc: raise RemoteError('Task barrier unavailable; review required.') from exc
                if pending is not None: raise RemoteError('Review the previous task outcome before pairing again.')
            if digest in self._used_tokens: raise RemoteError('A fresh pairing token is required.')
            self._used_tokens.add(digest)
            self._generation+=1
            self._session={'origin':origin,'token':token,'csrf':csrf,'scope':dict(scope),'bridge':bridge,'expires':expires,'generation':self._generation}
            self._requests={}

    def _authorized(self, host, origin, token, csrf):
        session=self._session
        if not session or self._clock()>=session['expires']: return False
        expected=urlsplit(session['origin']).netloc
        return (host==expected and origin==session['origin'] and isinstance(token,str) and token.isascii() and isinstance(csrf,str) and csrf.isascii() and
                hmac.compare_digest(token,session['token']) and hmac.compare_digest(csrf,session['csrf']))

    def _current(self, ident, row, session):
        return (self._session is session and self._active==ident and
                self._requests.get(ident) is row and row['generation']==session['generation'])

    def request(self, *, host, origin, token, csrf, body, deadline=None, wall_expiry=None):
        with self._lock:
            if not self._authorized(host,origin,token,csrf): raise RemoteError('Unauthorized or expired session.')
            if not isinstance(body,dict) or set(body)!={'id','task'}: raise RemoteError('Invalid request.')
            ident,task=body['id'],body['task']
            if not isinstance(ident,str) or not _ID.fullmatch(ident) or not isinstance(task,str) or not task.strip() or len(task)>MAX_TASK or '\x00' in task: raise RemoteError('Invalid request.')
            previous=self._requests.get(ident)
            if previous:
                if previous['task']!=task: raise RemoteError('Request ID conflict.')
                return {'id':ident,'status':previous['status']}
            if self._active or self._unresolved: raise RemoteError('A task is active or needs review.')
            if len(self._requests)>=1000: raise RemoteError('Session task limit reached.')
            session=self._session
            if deadline is not None or wall_expiry is not None:
                if (type(deadline) not in (int,float) or not math.isfinite(deadline) or
                    type(wall_expiry) is not int or not self._clock()<deadline<=min(session['expires'],self._clock()+30) or
                    not time.time()<wall_expiry<=time.time()+30): raise RemoteError('Request expired.')
            cancelled=DispatchToken(deadline=deadline,wall_expiry=wall_expiry,clock=self._clock)
            row={'task':task,'status':'validating','generation':session['generation'],'cancelled':cancelled,'inflight':False}
            self._requests[ident]=row;self._active=ident
        try: scope_ok=session['bridge'].valid_scope(dict(session['scope'])) is True
        except Exception: scope_ok=False
        with self._lock:
            if not self._current(ident,row,session):
                row['status']='cancelled';return {'id':ident,'status':'cancelled'}
            if cancelled.is_set() or not self._authorized(host,origin,token,csrf):
                self._active=None;row['status']='cancelled';return {'id':ident,'status':'cancelled'}
            if not scope_ok:
                self._active=None;row['status']='failed';return {'id':ident,'status':'failed'}
            row['status']='reserving';row['inflight']=True
        if self._barrier is not None:
            try: self._barrier.reserve(ident,dict(session['scope']))
            except Exception:
                with self._lock:
                    row['inflight']=False;row['status']='unknown';self._unresolved[(row['generation'],ident)]=row
                return {'id':ident,'status':'unknown'}
        with self._lock:
            if not self._current(ident,row,session) or cancelled.is_set() or not self._authorized(host,origin,token,csrf):
                row['inflight']=False
                try:
                    if self._barrier is not None:self._barrier.clear(ident)
                    row['status']='cancelled'
                    if self._current(ident,row,session):self._active=None
                except Exception:
                    row['status']='unknown';self._unresolved[(row['generation'],ident)]=row
                return {'id':ident,'status':row['status']}
            row['status']='dispatching'
        # A trusted bridge MUST check cancellation, the continuous-clock deadline
        # and project revision at its own final dispatch boundary.
        try: outcome=session['bridge'].submit(ident,task,dict(session['scope']),cancelled,session['expires'])
        except NotDispatched:
            with self._lock:
                row['inflight']=False
                try:
                    if self._barrier is not None:self._barrier.clear(ident)
                    row['status']='cancelled';self._unresolved.pop((row['generation'],ident),None)
                    if self._current(ident,row,session):self._active=None
                except Exception:
                    row['status']='unknown';self._unresolved[(row['generation'],ident)]=row
                return {'id':ident,'status':row['status']}
        except Exception:
            with self._lock:
                row['inflight']=False
                if row['status'] not in ('completed','failed','cancelled'):
                    row['status']='unknown';self._unresolved[(row['generation'],ident)]=row
                return {'id':ident,'status':row['status']}
        with self._lock:
            row['inflight']=False
            if (outcome=='existing' or outcome not in (None,'submitted')) and row['status']=='dispatching':
                row['status']='unknown';self._unresolved[(row['generation'],ident)]=row
            elif self._current(ident,row,session) and not cancelled.is_set() and row['status']=='dispatching':row['status']='submitted'
            return {'id':ident,'status':row['status']}

    def owner_result(self, ident, generation, status):
        if status not in ('completed','failed','cancelled','unknown'): raise RemoteError('Invalid status.')
        with self._lock:
            key=(generation,ident);row=self._unresolved.get(key)
            if row is None:
                row=self._requests.get(ident)
                if not row or row['generation']!=generation or self._active!=ident: return False
            if status=='unknown':
                row['status']='unknown';self._unresolved[key]=row;return True
            if row['inflight']: return False
            try:
                if self._barrier is not None:self._barrier.clear(ident)
            except Exception:
                row['status']='unknown';self._unresolved[key]=row;return False
            row['status']=status;self._unresolved.pop(key,None)
            if self._requests.get(ident) is row and self._active==ident:self._active=None
            return True

    def owner_reconcile(self, ident, generation, *, confirmed, outcome):
        # Native owner review only; no web operation exposes reconciliation.
        if confirmed is not True or outcome not in ('completed','failed','cancelled','not_started'): raise RemoteError('Owner review required.')
        with self._lock:
            key=(generation,ident);row=self._unresolved.get(key)
            if row is None or row['inflight']: raise RemoteError('Task outcome is still pending.')
            if self._barrier is not None:
                try:self._barrier.clear(ident)
                except Exception as exc:raise RemoteError('Task barrier unavailable; review required.') from exc
            row['status']=outcome;self._unresolved.pop(key)
            if self._requests.get(ident) is row and self._active==ident:self._active=None

    def status(self, *, host, origin, token, csrf, ident):
        with self._lock:
            if not self._authorized(host,origin,token,csrf): raise RemoteError('Unauthorized or expired session.')
            row=self._requests.get(ident)
            if not row: raise RemoteError('Unknown task.')
            session=self._session; state=row['status']
        if state in ('submitted','cancelling') and callable(getattr(session['bridge'],'status',None)):
            try: observed=session['bridge'].status(ident)
            except Exception: observed='unknown'
            if observed in ('queued','running','needs-owner','completed-unverified','failed','stopped','cancelling','review-required','unknown'):
                state=observed
        with self._lock:
            if not self._authorized(host,origin,token,csrf) or self._session is not session or self._requests.get(ident) is not row:
                raise RemoteError('Unauthorized or expired session.')
            # A concurrent Stop or uncertain dispatch supersedes an old observation.
            if row['status'] not in ('submitted','cancelling'): state=row['status']
            elif row['status']=='cancelling' and state not in ('stopped','review-required','unknown'): state='cancelling'
            return {'id':ident,'status':state}

    def _cancel_in_background(self, session, ident, row):
        def cancel():
            try: session['bridge'].cancel(ident)
            except Exception:
                with self._lock:
                    if row['status'] not in ('completed','failed','cancelled','not_started'):
                        row['status']='unknown';self._unresolved[(row['generation'],ident)]=row
        threading.Thread(target=cancel,daemon=True).start()

    def stop(self, *, host, origin, token, csrf, ident):
        with self._lock:
            if not self._authorized(host,origin,token,csrf): raise RemoteError('Unauthorized or expired session.')
            if self._active!=ident: raise RemoteError('Task is not active.')
            session=self._session;row=self._requests[ident]
            if row['status']=='cancelling': return {'id':ident,'status':'cancelling'}
            if row['status']=='unknown': return {'id':ident,'status':'unknown'}
            row['status']='cancelling';row['cancelled'].set()
        self._cancel_in_background(session,ident,row)
        return {'id':ident,'status':'cancelling'}

    def expire_if_needed(self):
        with self._lock:
            session=self._session
            expired=bool(session and self._clock()>=session['expires'])
        if expired:self.owner_revoke(expected_generation=session['generation'])
        return expired

    def owner_revoke(self, expected_generation=None):
        with self._lock:
            session=self._session
            if not session or (expected_generation is not None and session['generation']!=expected_generation):return False
            ident=self._active;row=self._requests.get(ident) if ident else None
            self._session=None;self._generation+=1
            if row:
                if row['status'] in ('dispatching','submitted','cancelling','unknown'):
                    self._unresolved[(row['generation'],ident)]=row
                row['status']='cancelling';row['cancelled'].set()
            self._active=None
        if ident:self._cancel_in_background(session,ident,row)
        return True
