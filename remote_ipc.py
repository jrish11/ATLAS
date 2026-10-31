"""Synthetic private-IPC adapter for the existing Agents registry.

No listener, pairing, credential, native UI or live bridge is created here.
Only a future native owner can hold the private endpoint and supply the scope,
confirmation callback and expiry. Do not expose this adapter to web input.
"""
import math
import threading
import uuid
import approval_channel
from remote_gate import NotDispatched

class NativeRegistryBridge:
    """Bound to an owner-selected scope; manager remains the sole task registry."""
    def __init__(self, manager, *, scope, folder, identity, expires, verify_scope, owner_confirm, clock=None):
        if not isinstance(scope,dict) or set(scope)!={'id','revision'} or not all(isinstance(v,str) and v for v in scope.values()): raise ValueError('Invalid scope.')
        if not isinstance(folder,str) or not folder.startswith('/') or not isinstance(identity,dict) or set(identity)!={'device','inode'} or any(type(v) is not int for v in identity.values()): raise ValueError('Invalid project.')
        if type(expires) not in (int,float) or not math.isfinite(expires): raise ValueError('Invalid expiry.')
        if not callable(verify_scope) or not callable(owner_confirm): raise ValueError('Native owner channel unavailable.')
        self.manager=manager;self.scope=dict(scope);self.folder=folder;self.identity=dict(identity);self.expires=expires
        self.verify_scope=verify_scope;self.owner_confirm=owner_confirm;self.clock=clock or approval_channel.shared_clock
        self._lock=threading.RLock();self._committed={};self._cancel_sent=set()

    def valid_scope(self, scope):
        return scope==self.scope and self.clock()<self.expires and self.verify_scope(self.folder,dict(self.identity)) is True

    def _request_id(self, ident):
        if not isinstance(ident,str) or len(ident)!=32: raise NotDispatched('Invalid request ID.')
        try: value=uuid.UUID(hex=ident)
        except (ValueError,AttributeError): raise NotDispatched('Invalid request ID.')
        if value.version!=4 or value.variant!=uuid.RFC_4122 or value.hex!=ident: raise NotDispatched('Invalid request ID.')
        return str(value)

    def _receipt(self, request_id):
        with self.manager.lock:
            return next((r for r in self.manager.rows.values() if r.get('codexClientRequest')==request_id),None)

    def submit(self, ident, task, scope, cancelled, expires):
        request_id=self._request_id(ident)
        if scope!=self.scope or expires!=self.expires or not isinstance(task,str) or not task.strip() or len(task)>4000 or '\x00' in task: raise NotDispatched('Invalid request.')
        with self._lock:
            existing=self._receipt(request_id)
            if existing:
                if existing.get('folder')!=self.folder or existing.get('brief')!=task or existing.get('codexProjectIdentity')!=self.identity: raise NotDispatched('Request ID conflict.')
                self._committed[ident]=existing['id'];return 'existing'
        if cancelled.is_set() or not self.valid_scope(scope): raise NotDispatched('Cancelled or scope changed.')
        # This callback must be implemented by the native owner UI; no web
        # field, model message or stored preference can substitute for it.
        if isinstance(self.owner_confirm,NativeApprovalChannel):
            accepted=self.owner_confirm.confirm_task(task,self.folder,getattr(cancelled,'deadline',None))
        else:accepted=self.owner_confirm(task,self.folder)
        if accepted is not True: raise NotDispatched('Owner did not approve.')
        with self._lock:
            if cancelled.is_set() or not self.valid_scope(scope): raise NotDispatched('Cancelled, expired or scope changed.')
            existing=self._receipt(request_id)
            if existing:
                if existing.get('folder')!=self.folder or existing.get('brief')!=task or existing.get('codexProjectIdentity')!=self.identity: raise NotDispatched('Request ID conflict.')
                self._committed[ident]=existing['id'];return 'existing'
            if not hasattr(cancelled,'try_commit') or not cancelled.try_commit(): raise NotDispatched('Cancelled before dispatch commit.')
            # The manager persists codexClientRequest before it launches a task.
            # Exceptions after this call begins are uncertain to the caller.
            self.manager.command({'action':'codex-start','folder':self.folder,'folderIdentity':dict(self.identity),
                                  'task':task,'confirmed':True,'requestId':request_id})
            row=self._receipt(request_id)
            if not row: raise RuntimeError('No durable task receipt; inspect before retrying.')
            self._committed[ident]=row['id']
            if cancelled.is_set():self._cancel_committed(ident)
            return 'submitted'

    def _recover_row(self, ident):
        # Only the existing Agents registry is a receipt. A request ID alone is
        # never authority to act on a row from another project or identity.
        try: request_id=self._request_id(ident)
        except NotDispatched: return None
        with self.manager.lock:
            matches=[row for row in self.manager.rows.values() if row.get('codexClientRequest')==request_id]
            if len(matches)!=1:return None
            row=matches[0]
            if (row.get('provider')!='codex' or row.get('folder')!=self.folder or
                row.get('codexProjectIdentity')!=self.identity or not isinstance(row.get('id'),str)):
                return None
            self._committed[ident]=row['id']
            return dict(row)

    def status(self, ident):
        with self._lock:
            row=self._recover_row(ident)
            if not row:return 'unknown'
            if row.get('cancelReviewRequired'):return 'review-required'
            if row.get('cancelRequested'):return 'cancelling'
            return {'offered':'queued','queued':'queued','running':'running','needs-you':'needs-owner','waiting-screen':'needs-owner','done':'completed-unverified','failed':'failed','stopped':'stopped'}.get(row.get('status'),'unknown')

    def _cancel_committed(self, ident):
        row=self._recover_row(ident)
        row_id=row['id'] if row else None
        if row_id and ident not in self._cancel_sent:
            self._cancel_sent.add(ident)
            self.manager.command({'action':'stop','id':row_id})

    def cancel(self, ident):
        # Closing the inherited owner channel also dismisses a pending native
        # sheet. This ends the remote session; it never grants another request.
        if isinstance(self.owner_confirm,NativeApprovalChannel): self.owner_confirm.close()
        with self._lock:self._cancel_committed(ident)

def serve_one(sock, bridge, cancelled):
    """Read one private socket frame; this is not an HTTP or network listener."""
    try:
        message=approval_channel._read(sock)
        if not isinstance(message,dict) or set(message)!={'kind','id','task'} or message['kind']!='submit': raise ValueError('Invalid frame.')
        result=bridge.submit(message['id'],message['task'],dict(bridge.scope),cancelled,bridge.expires)
        approval_channel._send(sock,{'status':'existing' if result=='existing' else 'submitted'})
    except NotDispatched:
        approval_channel._send(sock,{'status':'cancelled'})
    except (OSError,EOFError,ValueError):
        try:approval_channel._send(sock,{'status':'invalid'})
        except OSError:pass
    except Exception:
        try:approval_channel._send(sock,{'status':'unknown'})
        except OSError:pass

class NativeApprovalChannel:
    """Correlated owner confirmation over an already inherited private socket.

    The creator must keep the other endpoint exclusively in the native app and
    must close it on Stop or process exit. No listener or endpoint is created
    here. Remote input cannot supply the socket or write owner responses.
    """
    def __init__(self, sock, *, scope, identity, expires, clock=None, timeout=60):
        if not isinstance(sock, __import__('socket').socket): raise ValueError('Private channel required.')
        if not isinstance(scope,dict) or set(scope)!={'id','revision'} or not all(isinstance(v,str) and v for v in scope.values()): raise ValueError('Invalid scope.')
        if not isinstance(identity,dict) or set(identity)!={'device','inode'} or any(type(v) is not int for v in identity.values()): raise ValueError('Invalid identity.')
        if type(expires) not in (int,float) or not math.isfinite(expires) or type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=60: raise ValueError('Invalid deadline.')
        self.sock=sock;self.scope=dict(scope);self.identity=dict(identity);self.expires=expires;self.clock=clock or approval_channel.shared_clock;self.timeout=timeout
        self._lock=threading.Lock();self._closed=False;self._device=None
    def bind_device(self, device):
        import re
        if not isinstance(device,dict) or set(device)!={'id','name','generation','fingerprint','macFingerprint','macName'}:return False
        try: valid_id=str(uuid.UUID(device['id']))==device['id']
        except (ValueError,TypeError,AttributeError):return False
        if not valid_id or not all(isinstance(device[k],str) and device[k].strip() and len(device[k].encode())<=80 and not any(ord(c)<32 or ord(c)==127 for c in device[k]) for k in ('name','macName')) or type(device['generation']) is not int or not 0<device['generation']<=9007199254740991 or not all(isinstance(device[k],str) and re.fullmatch(r'[0-9a-f]{64}',device[k]) for k in ('fingerprint','macFingerprint')):return False
        with self._lock:
            if self._closed or self._device is not None or self.clock()>=self.expires:return False
            self._device=dict(device);return True
    def __call__(self, task, folder):
        return self.confirm_task(task,folder,None)
    def confirm_task(self, task, folder, request_expires):
        if not isinstance(task,str) or not task.strip() or len(task)>4000 or '\x00' in task or not isinstance(folder,str) or not folder.startswith('/') or '\x00' in folder: return False
        target={'action':'remote-codex-task','task':task,'folder':folder,'scope':dict(self.scope),'identity':dict(self.identity),'expires':self.expires}
        if self._device is not None:target['pairedDevice']=dict(self._device)
        if request_expires is not None:
            if type(request_expires) not in (int,float) or not math.isfinite(request_expires) or not self.clock()<request_expires<=self.expires:return False
            target['requestExpires']=request_expires
        return self._confirm(target)
    def confirm_pair(self, device, folder):
        if not isinstance(device,str) or not device.strip() or len(device)>80 or any(ord(c)<32 or ord(c)==127 for c in device) or not isinstance(folder,str) or not folder.startswith('/') or '\x00' in folder:return False
        target={'action':'remote-pair','device':device,'folder':folder,'scope':dict(self.scope),'identity':dict(self.identity),'expires':self.expires}
        return self._confirm(target)
    def confirm_enable(self, folder, origin, token, csrf, invitation):
        if not all(isinstance(v,str) and v for v in (folder,origin,token,csrf,invitation)): return False
        target={'action':'remote-enable','folder':folder,'scope':dict(self.scope),'identity':dict(self.identity),'expires':self.expires,
                'origin':origin,'credentials':{'token':token,'csrf':csrf,'invitation':invitation}}
        return self._confirm(target)
    def _confirm(self, target):
        with self._lock:
            request_expiry=target.get('requestExpires',self.expires)
            if self._closed or self.clock()>=request_expiry:return False
            requester=approval_channel.Requester(self.sock)
            try:
                monotonic=__import__('time').monotonic;deadline=monotonic()+self.timeout
                requester.request(target,deadline)
                while not self._closed and self.clock()<request_expiry and monotonic()<deadline:
                    ready,_,_=__import__('select').select([self.sock],[],[],min(.1,max(0,deadline-monotonic())))
                    if ready:return requester.receive() is True and not self._closed and self.clock()<request_expiry
                return False
            except (OSError,EOFError,ValueError):
                self._closed=True;return False
    def close(self):
        # shutdown interrupts a pending receive; never wait for the UI lock.
        self._closed=True
        try:self.sock.shutdown(__import__('socket').SHUT_RDWR)
        except OSError:pass
        self.sock.close()
