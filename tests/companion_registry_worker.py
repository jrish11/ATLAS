"""Synthetic private-supervisor child; never opens a network listener."""
import json,os,socket,sys,threading
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import atticus
class FakeProvider:
 def __init__(self,**kwargs):self.release=threading.Event()
 def run(self,*args,**kwargs):self.release.wait(10);return {'status':'stopped','result':'synthetic','server_status':'interrupted'}
 def interrupt(self):self.release.set()
 def close(self):self.release.set()
root=Path(sys.argv[1]);owner_socket=socket.socket(fileno=os.dup(2));null=os.open(os.devnull,os.O_WRONLY);os.dup2(null,2);os.close(null);sys.stderr=open(root/'error.log','w',buffering=1)
atticus.DIR=str(root/'profile');atticus.trusted_native_context_parent=lambda:True;atticus.codex_scoped_readiness=lambda *args:(True,'');atticus.close_agent_window=lambda *args:None;atticus.codex_provider.CodexProvider=FakeProvider
lock=threading.Lock()
def emit(event):
 with lock:sys.stdout.write(json.dumps(event)+'\n');sys.stdout.flush()
manager=atticus.Agents(emit=emit,launch=Mock());atticus.Agents=lambda:manager
atticus.agents_service(remote_owner=owner_socket)
