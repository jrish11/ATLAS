"""Private supervisor-side adapter for a future persistent companion bridge.

This adapter opens no listener and generates no credentials. The disabled
supervisor entry point requires its private native capability and native-channel
activation approval. Calls must pass the paired-device proof and session checks.
"""
import select, socket, threading
from remote_barrier import DurableBarrier
from remote_gate import RemoteGate
from remote_ipc import NativeRegistryBridge, NativeApprovalChannel

class CompanionRegistry:
    def __init__(self, manager, *, scope, folder, identity, origin, token, csrf,
                 expires, verify_scope, owner_confirm, barrier_directory, clock=None):
        self._closed=threading.Event();self._close_lock=threading.Lock()
        self.barrier=DurableBarrier(barrier_directory)
        try:
            self.bridge=NativeRegistryBridge(manager,scope=scope,folder=folder,identity=identity,expires=expires,
                verify_scope=verify_scope,owner_confirm=owner_confirm,clock=clock)
            self.gate=RemoteGate(clock=clock,barrier=self.barrier)
            self._auth={'host':origin.removeprefix('https://'),'origin':origin,'token':token,'csrf':csrf}
            self.gate.owner_enable(origin=origin,token=token,csrf=csrf,scope=scope,bridge=self.bridge,expires=expires)
        except Exception:
            self.barrier.close();raise
        if isinstance(owner_confirm,NativeApprovalChannel):
            self.owner=owner_confirm
            threading.Thread(target=self._watch,daemon=True).start()
        else:self.owner=None
    def _watch(self):
        try:probe=socket.fromfd(self.owner.sock.fileno(),socket.AF_UNIX,socket.SOCK_STREAM)
        except OSError:self.close();return
        try:
            while not self._closed.wait(.1):
                if self.bridge.clock()>=self.bridge.expires:self.close();return
                try:
                    ready,_,_=select.select([probe],[],[],0)
                    if ready and probe.recv(1,socket.MSG_PEEK|socket.MSG_DONTWAIT)==b'':self.close();return
                except BlockingIOError:continue
                except (OSError,ValueError):self.close();return
        finally:probe.close()
    def reviewable(self):
        with self.gate._lock:
            return (self._closed.is_set() and self.gate._session is None and
                    not any(row.get('inflight') for row in self.gate._requests.values()) and
                    not any(row.get('inflight') for row in self.gate._unresolved.values()))
    def recovery_clear(self):
        # Recheck under the gate lock so a concurrent dispatch cannot race this
        # observation. Any unreadable barrier or closing session fails closed.
        with self.gate._lock:
            try:
                return (not self._closed.is_set() and self.gate._session is not None and
                        self.gate._active is None and not self.gate._unresolved and
                        self.bridge.valid_scope(dict(self.bridge.scope)) and self.barrier.read() is None)
            except Exception:return False
    def submit(self, ident, task, deadline=None, wall_expiry=None):
        return self.gate.request(**self._auth,body={'id':ident,'task':task},deadline=deadline,wall_expiry=wall_expiry)
    def status(self, ident):
        return self.gate.status(**self._auth,ident=ident)
    def stop(self, ident):
        return self.gate.stop(**self._auth,ident=ident)
    def close(self):
        with self._close_lock:
            if self._closed.is_set():return
            self._closed.set()
        self.gate.owner_revoke()
        if self.owner is not None:self.owner.close()
