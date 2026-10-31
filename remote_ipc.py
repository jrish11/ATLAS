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
        if self.owner_confirm(task,self.folder) is not True: raise NotDispatched('Owner did not approve.')
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

    def status(self, ident):
        with self._lock:
            row_id=self._committed.get(ident)
            with self.manager.lock:
                row=self.manager.rows.get(row_id) if row_id else None
                if not row:return 'unknown'
                if row.get('cancelReviewRequired'):return 'review-required'
                if row.get('cancelRequested'):return 'cancelling'
                return {'offered':'queued','queued':'queued','running':'running','needs-you':'needs-owner','waiting-screen':'needs-owner','done':'completed-unverified','failed':'failed','stopped':'stopped'}.get(row.get('status'),'unknown')

    def _cancel_committed(self, ident):
        row_id=self._committed.get(ident)
        if row_id and ident not in self._cancel_sent:
            self._cancel_sent.add(ident)
            self.manager.command({'action':'stop','id':row_id})

    def cancel(self, ident):
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
