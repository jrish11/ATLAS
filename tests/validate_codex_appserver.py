"""Exercise adapter preflight and scoped app-server execution with no login or model turn."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from codex_provider import CodexProvider
from validate_codex_sandbox import CHECK


def main():
    codex=shutil.which('codex');node=shutil.which('node');python=Path(sys.executable).resolve()
    if not codex or not node or Path('/Library/Developer/CommandLineTools') not in python.parents:
        raise SystemExit('Requires Codex, Node and Command Line Tools Python.')
    with tempfile.TemporaryDirectory(prefix='atticus-appserver-fixture-',dir=ROOT.parent) as temp:
        root=Path(temp);task=root/'task';other=root/'other';home=root/'home';config=home/'.codex'
        for folder in (task,other,config):folder.mkdir(parents=True)
        (task/'check.py').write_text(CHECK);(other/'sentinel.txt').write_text('fixture only');(task/'outside-link').symlink_to(other/'sentinel.txt');(config/'config.toml').write_text('# fixture\n')
        env={'HOME':str(home),'CODEX_HOME':str(config),'PATH':str(Path(codex).parent)+os.pathsep+str(Path(node).parent)+':/usr/bin:/bin','TMPDIR':'/tmp','ATTICUS_FIXTURE_TOKEN':'fixture-only'}
        provider=CodexProvider(executable=codex)
        try:
            provider._launch(env)
            skills=provider._preflight(str(task))
            if skills:
                override='skills.config=['+','.join('{path='+json.dumps(path)+',enabled=false}' for path in skills)+']'
                provider.close();provider._launch(env,override)
            if provider._preflight(str(task)): raise RuntimeError('Skills still enabled')
            params={'cwd':str(task),'runtimeWorkspaceRoots':[str(task)],'permissions':provider.profile,'approvalPolicy':'on-request','approvalsReviewer':'user'}
            response=provider._request('thread/start',params)
            verified=((response.get('activePermissionProfile') or {}).get('id')==provider.profile and response.get('runtimeWorkspaceRoots')==[str(task)] and response.get('approvalPolicy')=='on-request' and response.get('approvalsReviewer')=='user')
            result=provider._request('command/exec',{'cwd':str(task),'command':[str(python),str(task/'check.py')],'permissionProfile':provider.profile,'timeoutMs':10000})
            observed=json.loads(result.get('stdout','{}')) if result.get('exitCode')==0 else {}
            expected={'workspace_read':'allowed','workspace_write':'allowed','sibling_read':'denied','symlink_read':'denied','sibling_write':'denied','config_write':'denied','loopback_connect':'denied'}
            env_result=provider._request('command/exec',{'cwd':str(task),'command':[str(python),'-c','import os; print("present" if "ATTICUS_FIXTURE_TOKEN" in os.environ else "absent")'],'permissionProfile':provider.profile,'timeoutMs':10000})
            token_hidden=env_result.get('exitCode')==0 and env_result.get('stdout','').strip()=='absent'
            passed=verified and observed==expected and token_hidden
            print(json.dumps({'skills_initially_enabled':len(skills),'skills_after_restart_enabled':0,'profile_and_roots_verified':verified,'sensitive_env_hidden':token_hidden,'observed':observed,'passed':passed},indent=2))
            if not passed:raise SystemExit(1)
        finally:provider.close()

if __name__=='__main__':main()
