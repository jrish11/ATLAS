"""Synthetic child of the Swift owner: no registry, listener, or external calls."""
import os, socket, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from remote_ipc import NativeApprovalChannel
sock=socket.socket(fileno=0)
channel=NativeApprovalChannel(sock,scope={'id':'fixture','revision':'r1'},identity={'device':1,'inode':2},expires=float(sys.argv[1]),timeout=5)
folder='/tmp/other' if sys.argv[3]=='scope' else '/tmp/project'
allowed=channel('synthetic task',folder)
second=channel('second task',folder) if sys.argv[3]=='deny' else False
with open(sys.argv[2],'w') as result: result.write(('allow' if allowed else 'deny')+(' second' if second else ''))
channel.close()
