"""One owner-approved, bounded synthetic Pi request; no personal context."""
import json, math, os, subprocess, sys, tempfile, time
import foreground_openai, keychain_store

PROMPT = 'Reply with the single word READY.'
MODEL = 'gpt-6.1-terra'

def run(home, directory, helper, ledger, runner=subprocess.run):
    # Exclusive reservation prevents double-clicks and retries from spending again.
    fd = os.open(ledger, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'w') as f: json.dump({'reserved_usd': 0.01, 'state': 'reserved'}, f)
    pi = foreground_openai.resolve_pi(directory, home)
    if not pi: raise ValueError('Isolated Pi is unavailable.')
    with tempfile.TemporaryDirectory(prefix='atticus-foreground-smoke-') as ask:
        store = keychain_store.ProviderKeyStore(directory, keychain_store.KeychainStore(helper, slot='foreground-openai'), slot='foreground-openai')
        flags, env = foreground_openai.prepare(ask, MODEL, {'PATH':home+'/.local/bin:/usr/bin:/bin','HOME':home}, store.get)
        profile = env['PI_CODING_AGENT_DIR']
        with open(os.path.join(profile,'models.json'),'w') as f: json.dump(foreground_openai.terra_model_config(max_tokens=128),f)
        with open(os.path.join(profile,'settings.json'),'w') as f: json.dump({'retry':{'enabled':False,'provider':{'maxRetries':0}},'httpIdleTimeoutMs':30000},f)
        args=[pi,'--mode','json','--print',*flags,'--thinking','off','--system-prompt','Answer briefly.','--',PROMPT]
        start=time.monotonic()
        with open(ledger,'w') as f: json.dump({'reserved_usd':0.01,'state':'dispatching'},f)
        result=runner(args,env=env,cwd=ask,text=True,capture_output=True,timeout=50)
        elapsed=round(time.monotonic()-start,2); env.pop('OPENAI_API_KEY',None)
        answer=None; usage=None; reason=None
        for line in result.stdout.splitlines():
            try: event=json.loads(line)
            except ValueError: continue
            if not isinstance(event,dict) or event.get('type') != 'message_end': continue
            msg=event.get('message')
            if not isinstance(msg,dict) or msg.get('role') != 'assistant': continue
            blocks=msg.get('content')
            if not isinstance(blocks,list) or any(not isinstance(x,dict) for x in blocks): continue
            texts=[x.get('text') for x in blocks if x.get('type')=='text']
            if any(not isinstance(x,str) for x in texts): continue
            answer=' '.join(texts); raw=msg.get('usage'); reason=msg.get('stopReason')
            if isinstance(raw,dict):
                numeric=lambda v: type(v) in (int,float) and math.isfinite(v) and v >= 0
                usage={k:raw[k] for k in ('input','output','reasoning','cacheRead','cacheWrite','totalTokens') if k in raw and numeric(raw[k])}
                costs=raw.get('cost')
                if isinstance(costs,dict): usage['cost']={k:costs[k] for k in ('input','output','cacheRead','cacheWrite','total') if k in costs and numeric(costs[k])}
        if result.returncode or not answer or answer.strip()!='READY' or reason!='stop': raise ValueError('The bounded request did not return the expected response.')
        record={'reserved_usd':0.01,'state':'complete','model':MODEL,'elapsed_seconds':elapsed,'usage':usage,'response':'READY'}
        with open(ledger,'w') as f: json.dump(record,f)
        return record

if __name__ == '__main__':
    try:
        home=os.path.expanduser('~'); base=os.path.join(home,'Documents','Codex','2026-10-30','task-6')
        record=run(home,os.environ['ATTICUS_DIR'],os.environ['ATTICUS_DEV_KEYCHAIN_HELPER'],os.path.join(base,'atticus-terra-ui-smoke-ledger.json'))
        print(json.dumps(record))
    except Exception:
        print(json.dumps({'error':'Smoke test could not finish. Check Keychain authorization and the test ledger before retrying.'})); sys.exit(1)
