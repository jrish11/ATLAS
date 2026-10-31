"""Synthetic missing-destination lookup: cold Python import versus warm supervisor IPC."""
import json, os, statistics, subprocess, sys, tempfile, time, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def stats(values):
    values=sorted(values)
    return {'n':len(values),'median_ms':round(statistics.median(values),3),'p95_ms':round(values[(95*len(values)+99)//100-1],3)}
with tempfile.TemporaryDirectory(prefix='atticus-resident-bench-') as directory:
    env={'PATH':os.defpath,'HOME':directory,'ATTICUS_DIR':directory,'ATTICUS_POSTHOG_KEY':'','PYTHONPYCACHEPREFIX':str(Path(directory,'cache'))}
    command='open nonexistent fixture destination zz123'
    cold=[]
    code='import personal_commands,sys; assert personal_commands.resolve(sys.argv[1],sys.argv[2]) is None'
    for i in range(40):
        start=time.perf_counter_ns()
        subprocess.run([sys.executable,'-c',code,directory,command],cwd=ROOT,env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        cold.append((time.perf_counter_ns()-start)/1e6)
    p=subprocess.Popen([sys.executable,'-u','atticus.py','--agents'],cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,bufsize=1)
    try:
        def request():
            identifier=uuid.uuid4().hex
            p.stdin.write(json.dumps({'action':'personal-open','id':identifier,'text':command,'confirmed':True})+'\n');p.stdin.flush()
            while True:
                line=p.stdout.readline()
                if not line: raise RuntimeError('supervisor exited')
                event=json.loads(line)
                if event.get('id')==identifier:
                    assert event.get('matched') is False
                    return
        request()
        warm=[]
        for i in range(400):
            start=time.perf_counter_ns();request();warm.append((time.perf_counter_ns()-start)/1e6)
    finally:
        p.terminate();p.wait(timeout=5)
    print(json.dumps({'cold_python_import_and_lookup':stats(cold),'warm_supervisor_ipc_lookup':stats(warm),'note':'Missing synthetic destination only. No browser, model, network, microphone or UI. Cold comparison is a minimal module import, not the full upstream --fast route.'},indent=2))
