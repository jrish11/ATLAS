"""Owner-created experimental remote session in the existing Agents process.

No entrypoint starts this module. Only the supervisor's trusted native control
path may construct it; HTTP cannot enable, pair, alter scope or reconcile.
"""
import select
import socket
import threading
import time
from remote_barrier import DurableBarrier
from remote_gate import RemoteGate
from remote_ipc import NativeApprovalChannel, NativeRegistryBridge
from remote_loopback import LoopbackServer, Pairing

class RemoteSession:
    def __init__(self, manager, *, owner_socket, folder, identity, scope, origin,
                 token, csrf, expires, barrier_directory, verify_scope, clock=None, invitation=None):
        import approval_channel
        self.clock=clock or approval_channel.shared_clock
        self.barrier=DurableBarrier(barrier_directory)
        self.owner=None;self.server=None;self._closed=threading.Event();self._close_lock=threading.Lock()
        try:
            self.owner=NativeApprovalChannel(owner_socket,scope=scope,identity=identity,expires=expires,clock=self.clock)
            self.bridge=NativeRegistryBridge(manager,scope=scope,folder=folder,identity=identity,expires=expires,
                                             verify_scope=verify_scope,owner_confirm=self.owner,clock=self.clock)
            self.gate=RemoteGate(clock=self.clock,barrier=self.barrier)
            self.gate.owner_enable(origin=origin,token=token,csrf=csrf,scope=scope,bridge=self.bridge,expires=expires)
            pairing=None
            if invitation is not None:
                self.invitation=Pairing(origin,self.clock,expires,code=invitation)
                pairing=lambda code,device:self.invitation.redeem(code,device,lambda name:self.owner.confirm_pair(name,folder),token,csrf)
            self.server=LoopbackServer(self.gate,origin,pairing=pairing)
        except Exception:
            if self.owner:self.owner.close()
            self.barrier.close()
            raise
        self._server_thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self._server_thread.start()
        self._watcher=threading.Thread(target=self._watch,daemon=True);self._watcher.start()

    @property
    def port(self): return self.server.server_port

    def reviewable(self):
        # Revocation alone is not proof that a dispatch thread has returned.
        # No review may clear its durable barrier while that outcome is moving.
        with self.gate._lock:
            return (self._closed.is_set() and self.gate._session is None and
                    not any(row.get('inflight') for row in self.gate._requests.values()) and
                    not any(row.get('inflight') for row in self.gate._unresolved.values()))

    def _watch(self):
        # Peek only. The approval reader retains exclusive ownership of frames.
        try:
            probe=socket.fromfd(self.owner.sock.fileno(),socket.AF_UNIX,socket.SOCK_STREAM)
        except OSError:
            self.close();return
        try:
            while not self._closed.wait(.1):
                if self.clock()>=self.bridge.expires:
                    self.close();return
                try:
                    ready,_,_=select.select([probe],[],[],0)
                    if ready and probe.recv(1,socket.MSG_PEEK|socket.MSG_DONTWAIT)==b'':
                        self.close();return
                except BlockingIOError:
                    continue
                except (OSError,ValueError):
                    self.close();return
        finally: probe.close()

    def close(self):
        with self._close_lock:
            if self._closed.is_set():return
            self._closed.set()
        self.gate.owner_revoke()
        self.owner.close()
        self.server.shutdown();self.server.server_close()
        # Requests in flight may still be using the barrier. Do not close its fd
        # here; it remains owned until the session itself is discarded.
