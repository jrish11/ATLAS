"""Disposable, credential-free Codex sandbox boundary fixture; no inference.

Run from a macOS account allowed to create a seatbelt sandbox. This creates only
fixture files in a temporary directory outside the git checkout and removes them.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

CHECK = '''import errno,json,socket
from pathlib import Path
root=Path(__file__).resolve().parents[1]; out={}
def check(name, fn):
 try: fn(); out[name]='allowed'
 except OSError as e: out[name]='denied' if e.errno in (errno.EACCES,errno.EPERM,errno.EROFS) else 'error:'+str(e.errno)
check('workspace_read',lambda:(root/'task'/'check.py').read_text())
check('workspace_write',lambda:(root/'task'/'written.txt').write_text('fixture'))
check('sibling_read',lambda:(root/'other'/'sentinel.txt').read_text())
check('symlink_read',lambda:(root/'task'/'outside-link').read_text())
check('sibling_write',lambda:(root/'other'/'created.txt').write_text('fixture'))
check('config_write',lambda:(root/'home'/'.codex'/'config.toml').write_text('# changed'))
def network():
 s=socket.socket();s.settimeout(.5)
 try:s.connect(('127.0.0.1',9))
 finally:s.close()
check('loopback_connect',network)
print(json.dumps(out,sort_keys=True))
'''

def main():
    if sys.platform != 'darwin': raise SystemExit('This fixture requires macOS.')
    codex=shutil.which('codex'); node=shutil.which('node')
    runtime=Path('/Library/Developer/CommandLineTools')
    python=Path(sys.executable).resolve()
    if not codex or not node or not runtime.is_dir() or runtime not in python.parents:
        raise SystemExit('This fixture requires Codex, Node, and the Command Line Tools Python runtime.')
    parent=Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='atticus-sandbox-fixture-',dir=parent) as temp:
        root=Path(temp); task=root/'task'; other=root/'other'; home=root/'home'; config=home/'.codex'
        for folder in (task,other,config):folder.mkdir(parents=True)
        (task/'check.py').write_text(CHECK);(other/'sentinel.txt').write_text('fixture only')
        (task/'outside-link').symlink_to(other/'sentinel.txt')
        (config/'config.toml').write_text('[permissions.atticus.filesystem]\n":minimal" = "read"\n":workspace_roots" = "write"\n"/Library/Developer/CommandLineTools" = "read"\n[permissions.atticus.network]\nenabled = false\n')
        env={'HOME':str(home),'CODEX_HOME':str(config),'PATH':str(Path(codex).parent)+os.pathsep+str(Path(node).parent)+':/usr/bin:/bin','TMPDIR':'/tmp'}
        command=[codex,'sandbox','-P','atticus','-C',str(task),str(python),str(task/'check.py')]
        result=subprocess.run(command,env=env,capture_output=True,text=True,timeout=20)
        if result.returncode: raise SystemExit('Sandbox fixture could not run: '+result.stderr.strip()[:500])
        values=json.loads(result.stdout)
        expected={'workspace_read':'allowed','workspace_write':'allowed','sibling_read':'denied','symlink_read':'denied','sibling_write':'denied','config_write':'denied','loopback_connect':'denied'}
        server=subprocess.Popen([codex,'app-server'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        def send(value):
            server.stdin.write(json.dumps(value)+'\n'); server.stdin.flush()
        def response(identifier):
            for line in server.stdout:
                value=json.loads(line)
                if value.get('id')==identifier and 'method' not in value: return value
            raise RuntimeError('app-server stopped')
        try:
            send({'id':1,'method':'initialize','params':{'clientInfo':{'name':'atticus-fixture','version':'0.1'},'capabilities':{'experimentalApi':True}}})
            if 'result' not in response(1): raise RuntimeError('initialize failed')
            send({'method':'initialized','params':{}})
            send({'id':2,'method':'thread/start','params':{'cwd':str(task),'runtimeWorkspaceRoots':[str(task)],'permissions':'atticus','approvalPolicy':'on-request','approvalsReviewer':'user'}})
            thread=response(2).get('result',{})
            profile_ok=(thread.get('activePermissionProfile') or {}).get('id')=='atticus' and thread.get('runtimeWorkspaceRoots')==[str(task)]
            send({'id':3,'method':'command/exec','params':{'cwd':str(task),'command':[str(python),str(task/'check.py')], 'permissionProfile':'atticus','timeoutMs':10000}})
            execution=response(3).get('result',{})
            observed=json.loads(execution.get('stdout','{}')) if execution.get('exitCode')==0 else {}
        finally:
            server.terminate();server.wait(timeout=5)
        passed = values == expected and profile_ok and observed == expected
        print(json.dumps({'cli_observed':values,'app_server_observed':observed,'profile_and_roots_verified':profile_ok,'expected':expected,'passed':passed},indent=2))
        if not passed: raise SystemExit(1)

if __name__=='__main__':main()
