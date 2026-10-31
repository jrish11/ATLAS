"""Private socket-pair approval protocol; no filesystem or environment tokens.

Both endpoints must be created by a trusted parent and explicitly passed only to
trusted children. This module does not choose peers or authorize actions.
"""
import hashlib
import json
import math
import secrets
import socket
import struct
import time
import sys

MAX_FRAME=8192

def shared_clock():
 """Host-wide monotonic seconds, matching native mach_continuous_time on macOS, including sleep.

 Some Python builds normalize time.monotonic() to a process-local epoch, so it
 must not be used to compare deadlines produced by another process.
 """
 if sys.platform != 'darwin': return time.monotonic()
 try:
  import ctypes
  class Scale(ctypes.Structure): _fields_=[('numer',ctypes.c_uint32),('denom',ctypes.c_uint32)]
  lib=ctypes.CDLL('/usr/lib/libSystem.B.dylib');lib.mach_continuous_time.restype=ctypes.c_uint64
  scale=Scale()
  if lib.mach_timebase_info(ctypes.byref(scale)) != 0 or not scale.denom: return float('inf')
  return lib.mach_continuous_time()*scale.numer/scale.denom/1_000_000_000
 except (OSError,AttributeError,ValueError): return float('inf')

def _digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def _send(sock,obj):
 data=json.dumps(obj,sort_keys=True,separators=(',',':')).encode()
 if len(data)>MAX_FRAME: raise ValueError('Frame too large')
 sock.sendall(struct.pack('!I',len(data))+data)

def _read(sock):
 def exact(n):
  result=b''
  while len(result)<n:
   chunk=sock.recv(n-len(result))
   if not chunk: raise EOFError('Approval channel closed')
   result+=chunk
  return result
 size=struct.unpack('!I',exact(4))[0]
 if not 0<size<=MAX_FRAME: raise ValueError('Invalid frame')
 data=json.loads(exact(size))
 if not isinstance(data,dict):raise ValueError('Invalid message')
 return data

class Requester:
 def __init__(self,sock,clock=time.monotonic,session=None,shared=shared_clock):
  self.sock=sock;self.clock=clock;self.shared=shared;self.session=session;self.pending=None;self.closed=False;self.authorizationDeadline=None;self.authorizationRevision=None
 def request(self,target,deadline):
  if self.closed or self.pending is not None or not isinstance(target,dict) or not isinstance(deadline,(int,float)) or deadline<=self.clock():raise ValueError('Invalid or pending request')
  nonce=secrets.token_hex(32);revision=_digest(target);self.pending=(nonce,revision,deadline)
  message={'kind':'request','id':nonce,'revision':revision,'target':target}
  if self.session is not None: message['session']=self.session
  _send(self.sock,message)
 def receive(self):
  if self.closed or self.pending is None:raise ValueError('No pending request')
  nonce,revision,deadline=self.pending;self.pending=None
  remaining=deadline-self.clock()
  if remaining<=0: self.closed=True;return False
  try:
   self.sock.settimeout(remaining);response=_read(self.sock)
  except (EOFError,OSError,ValueError): self.closed=True;return False
  finally: self.sock.settimeout(None)
  expected={'kind':'decision','id':nonce,'revision':revision,'allow':True}
  if self.session is not None: expected['session']=self.session
  expiry=response.get('expires');target_revision=response.get('targetRevision')
  if expiry is not None:
   if type(expiry) not in (int,float) or not math.isfinite(expiry) or not self.shared() < expiry <= self.shared()+600: return False
   if not isinstance(target_revision,str) or not target_revision or len(target_revision)>4096 or any(c in target_revision for c in '\r\n'): return False
   expected['expires']=expiry;expected['targetRevision']=target_revision
  elif target_revision is not None: return False
  valid=self.clock()<deadline and type(response.get('allow')) is bool and response==expected
  if valid: self.authorizationDeadline=expiry;self.authorizationRevision=target_revision
  return valid
 def cancel(self): self.pending=None;self.closed=True;self.sock.close()

class Owner:
 def __init__(self,sock,session=None): self.sock=sock;self.session=session;self.seen=set();self.pending=None
 def receive(self):
  message=_read(self.sock)
  expected={'kind','id','revision','target'} | ({'session'} if self.session is not None else set())
  if set(message)!=expected or (self.session is not None and message.get('session')!=self.session) or message['kind']!='request' or not isinstance(message['id'],str) or len(message['id'])!=64 or not isinstance(message['target'],dict) or message['revision']!=_digest(message['target']) or message['id'] in self.seen or self.pending is not None:raise ValueError('Invalid or replayed request')
  self.seen.add(message['id']);self.pending=message;return message['target']
 def respond(self,allow,expires=None,target_revision=None):
  if self.pending is None or type(allow) is not bool:raise ValueError('No pending request')
  msg=self.pending;self.pending=None
  response={'kind':'decision','id':msg['id'],'revision':msg['revision'],'allow':allow}
  if self.session is not None: response['session']=self.session
  if expires is not None: response['expires']=expires;response['targetRevision']=target_revision
  _send(self.sock,response)

class Approval(str):
 def __new__(cls, value, deadline=None, revision=None):
  obj=super().__new__(cls,value);obj.deadline=deadline;obj.revision=revision;return obj

def authorized(decision, clock=shared_clock):
 import select
 deadline=getattr(decision,'deadline',None)
 if decision!='y' or (deadline is not None and clock()>=deadline): return False
 if not isinstance(decision,Approval): return True
 try:
  probe=socket.fromfd(TOOL_FD,socket.AF_UNIX,socket.SOCK_STREAM)
  try:
   ready,_,_=select.select([probe],[],[],0)
   return not ready  # EOF or unexpected pending data both fail closed.
  finally: probe.close()
 except OSError: return False

# Descriptor 198 is deliberately fixed: the descriptor itself is the capability;
# no nonce, path, or descriptor capability is placed in an environment variable.
TOOL_FD=198

def tool_approval(question, timeout=60):
 if not isinstance(question,dict) or set(question)!={'q','cmd'}: return None
 try:
  sock=socket.socket(fileno=TOOL_FD);sock.settimeout(timeout)
  _send(sock,{'kind':'hello'})
  greeting=_read(sock)
  if set(greeting)!={'kind','nonce'} or greeting['kind']!='session' or not isinstance(greeting['nonce'],str) or len(greeting['nonce'])!=64: return None
  requester=Requester(sock,session=greeting['nonce']);requester.request(question,time.monotonic()+timeout)
  return Approval('y',requester.authorizationDeadline,requester.authorizationRevision) if requester.receive() else 'n'
 except (OSError,ValueError,EOFError): return None
 finally:
  try: sock.settimeout(None);sock.detach()
  except (NameError,OSError): pass

def native_broker(sock, input_stream, output_stream, timeout=60):
 """Forward one-at-a-time private requests to native via its inherited pipes."""
 import select
 session=secrets.token_hex(32);owner=Owner(sock,session=session)
 try:
  while True:
   if _read(sock)!={'kind':'hello'}: return
   _send(sock,{'kind':'session','nonce':session})
   target=owner.receive()
   if set(target)!={'q','cmd'} or any(not isinstance(target[k],str) or not target[k] or len(target[k])>800 or any(c in target[k] for c in '\r\n\t') for k in ('q','cmd')): return
   request=owner.pending
   output_stream.write('? '+target['q']+'\t'+target['cmd']+'\tchannel:'+request['id']+':'+request['revision']+'\n');output_stream.flush()
   ready,_,_=select.select([input_stream],[],[],timeout)
   if not ready: return
   raw=input_stream.readline(4097)
   if not raw or len(raw)>4096: return
   reply=json.loads(raw)
   if not isinstance(reply,dict): return
   expected={'id':request['id'],'revision':request['revision'],'allow':reply.get('allow')}
   expires=reply.get('expires');target_revision=reply.get('targetRevision')
   if expires is not None: expected['expires']=expires;expected['targetRevision']=target_revision
   if type(reply.get('allow')) is not bool or reply!=expected or (expires is not None and (reply['allow'] is not True or type(expires) not in (int,float) or not math.isfinite(expires) or not isinstance(target_revision,str) or not target_revision or len(target_revision)>4096)) or (expires is None and target_revision is not None): return
   owner.respond(reply['allow'],expires,target_revision)
 except (EOFError,OSError,ValueError,TypeError,KeyError): pass
 finally:
  try: sock.shutdown(socket.SHUT_RDWR)
  except OSError: pass
