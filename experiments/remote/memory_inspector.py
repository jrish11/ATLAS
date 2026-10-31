"""Read-only index of existing Atticus memory stores; never reads Keychain or vault files."""
import hashlib, json, os, re
from pathlib import Path
import memory_rules_store
import personal_commands

SENSITIVE = re.compile(r'\b(ssn|social security|credit card|debit card|card number|cvv|password|passcode|pin|health|medical|money|income|salary|bank|routing)\b', re.I)

CATEGORIES=('profile','rules','destinations','projects','workflows','corrections','tasks','sessions')
def read_json(path, default):
    try:
        if os.path.islink(path) or os.path.getsize(path)>8_000_000:return default
        with open(path,encoding='utf-8') as f:return json.load(f)
    except (OSError,ValueError,TypeError):return default

def in_scope(path, excluded):
    if not excluded:return True
    if not isinstance(path,str) or not os.path.isabs(path):return False
    path=os.path.realpath(path)
    try:return not any(os.path.commonpath((path,os.path.realpath(x)))==os.path.realpath(x) for x in excluded)
    except (ValueError,TypeError):return False

def inspect(directory, excluded=()):
    if not isinstance(excluded,(list,tuple)) or any(not isinstance(x,str) or not os.path.isabs(x) for x in excluded):raise ValueError('Invalid folder exclusions.')
    root=Path(directory); out=[]
    def add(category, title, **metadata):
        if not isinstance(title,str) or not title.strip():return
        clean={k:v for k,v in metadata.items() if k in ('source','confirmed','confidence','scope','updated','status','identifier','revision','editValue','folder') and isinstance(v,(str,int,float,bool))}
        if isinstance(metadata.get('aliases'), list) and all(isinstance(x, str) for x in metadata['aliases']): clean['aliases'] = metadata['aliases']
        out.append({'category':category,'title':title[:300],**clean})
    def revision(value):
        return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    profile=read_json(root/'me.json',{})
    if isinstance(profile,dict):
        facts=profile.get('facts',[])
        if profile.get('version') != 2:
            if isinstance(profile.get('name'),str) and profile['name']:add('profile','Legacy name',source='you',scope='local',confirmed=True)
            if isinstance(profile.get('about'),str) and profile['about']:add('profile','Legacy about',source='you',scope='local',confirmed=True)
            if isinstance(facts,list):
                for f in facts:
                    if isinstance(f,str) and f:add('profile','Legacy fact',source='learned',scope='local',confirmed=False)
        if isinstance(facts,list):
            for f in facts:
                if isinstance(f,dict) and not f.get('sensitive') and isinstance(f.get('kind'),str):
                    add('profile',f.get('kind',''),source=f.get('source','unknown'),scope='local',confirmed=f.get('source')=='you',updated=f.get('date',''), **({'identifier':f['id'],'revision':revision(f),'editValue':f['value']} if profile.get('version') == 2 and set(profile) == {'version','facts'} and isinstance(f.get('id'),str) and f['id'] and isinstance(f.get('value'),str) and not SENSITIVE.search(f['kind'] + ' ' + f['value']) and not (set(f)-{'id','category','kind','value','source','date','sensitive'}) else {}))
    try:
        if (root/'memory.md').is_symlink():raise OSError('Symlinked memory store')
        with open(root/'memory.md','rb') as f: data=f.read(8_000_001)
        if len(data)>8_000_000: raise ValueError('Rule store is too large.')
        if data.startswith(memory_rules_store.HEADER.encode()):
            rules=memory_rules_store.parse(data)
            for row in rules:
                if len(out)>=1000:break
                rule=row['text']; add('rules',rule,source='local',scope='local',identifier='rule:'+row['id'],revision=revision(row),editValue=rule)
        else:
            for line in data.decode('utf-8').splitlines(keepends=True):
                if len(out)>=1000:break
                rule=line.removeprefix('- ').strip()
                add('rules',rule,source='local',scope='local', **({'identifier':rule,'revision':revision(rule),'editValue':rule} if line == '- '+rule+'\n' and rule else {}))
    except (OSError,ValueError,UnicodeError):pass
    destinations=read_json(root/'destinations.json',[])
    if isinstance(destinations,list):
        for r in destinations:
            if not isinstance(r,dict) or r.get('confirmed') is not True:continue
            add('destinations',r.get('label'),source=r.get('source','unknown'),scope=r.get('scope','device'),confirmed=True,confidence=r.get('confidence',0),updated=r.get('updated',0))
            for item in r.get('corrections',[]) if isinstance(r.get('corrections'),list) else []:
                if isinstance(item,dict):
                    editable = isinstance(r.get('label'),str) and ('id' not in item or isinstance(item['id'],str))
                    identifier = (('correction:' + item['id']) if item.get('id') else 'legacy:' + revision([r.get('label'),item])) if editable else ''
                    safe_url = item.get('url','') if personal_commands.validate_url(item.get('url','')) else ''
                    add('corrections',r.get('label'),source=item.get('source','unknown'),scope='device',confirmed=item.get('confirmed') is True,updated=item.get('corrected_at',0), **({'identifier':identifier,'revision':revision(item),'editValue':safe_url} if editable else {}))
    projects=read_json(root/'projects.json',[])
    if isinstance(projects,list):
        for r in projects:
            if isinstance(r,dict) and r.get('confirmed') is True and in_scope(r.get('folder'),excluded):
                editable = isinstance(r.get('label'),str) and bool(r['label']) and isinstance(r.get('folder'),str) and isinstance(r.get('aliases'),list) and all(isinstance(x,str) for x in r['aliases']) and not (set(r)-{'label','folder','aliases','confirmed','source','scope','updated'})
                add('projects',r.get('label'),source=r.get('source','unknown'),scope=r.get('scope','device'),confirmed=True,updated=r.get('updated',0), **({'identifier':r['label'],'revision':revision(r),'folder':r['folder'],'aliases':r['aliases']} if editable else {}))
    for filename in ('skills.json','workflows.json'):
        rows=read_json(root/filename,{})
        if isinstance(rows,dict):
            for key,value in rows.items():
                evidence=value.get('evidence',{}) if isinstance(value,dict) else {}
                if not isinstance(evidence,dict):evidence={}
                editable = isinstance(key,str) and ((filename=='workflows.json' and isinstance(value,str)) or (filename=='skills.json' and isinstance(value,dict) and isinstance(value.get('cmds'),list) and all(isinstance(c,str) for c in value['cmds'])))
                shown = value if filename=='workflows.json' else '\n'.join(value['cmds']) if editable else ''
                add('workflows',key,source=evidence.get('source','legacy'),scope='local',confirmed=evidence.get('confirmed') is True,confidence=evidence.get('confidence',0),updated=evidence.get('updated',0), **({'identifier':filename.removesuffix('.json')+':'+key,'revision':revision({'key':key,'record':value}),'editValue':shown} if editable else {}))
    agents=root/'agents'
    try: agent_dirs=[] if agents.is_symlink() else list(agents.iterdir())[:1000]
    except OSError:agent_dirs=[]
    for folder in agent_dirs:
        if len(folder.name)!=32 or any(c not in '0123456789abcdef' for c in folder.name) or folder.is_symlink():continue
        r=read_json(folder/'state.json',{})
        if isinstance(r,dict) and in_scope(r.get('folder'),excluded):add('tasks',r.get('title'),source=r.get('provider','unknown'),scope='local',status=r.get('status','unknown'),updated=r.get('created',0))
    # Recent turns have no reliable project scope. Exclusions therefore hide them.
    if not excluded:
        try:
            if (root/'recent.jsonl').is_symlink():raise OSError('Symlinked session store')
            with open(root/'recent.jsonl',encoding='utf-8') as f:
                for line in f:
                    try:r=json.loads(line)
                    except ValueError:continue
                    if isinstance(r,dict) and isinstance(r.get('q'),str):add('sessions',r['q'],source='user',scope='local',updated=r.get('t',0))
                    if len(out)>=1000:break
        except OSError:pass
    return out[:1000]

def export_metadata(rows,categories):
    if not isinstance(categories,list) or any(c not in CATEGORIES for c in categories):raise ValueError('Invalid export categories.')
    # Strict enumerations and numeric values only: no arbitrary text, paths, URLs or IDs.
    sources={'you','contacts','mail','learned','owner','legacy','local','user','claude','codex','unknown'}
    scopes={'local','device','shared','unknown'}
    statuses={'offered','queued','running','needs-you','waiting-screen','done','failed','stopped','unknown'}
    items=[]
    for r in rows:
        if r.get('category') not in categories:continue
        item={'category':r['category'], 'source':r.get('source') if isinstance(r.get('source'),str) and r.get('source') in sources else 'unknown',
              'scope':r.get('scope') if isinstance(r.get('scope'),str) and r.get('scope') in scopes else 'unknown'}
        if type(r.get('confirmed')) is bool:item['confirmed']=r['confirmed']
        if type(r.get('confidence')) in (int,float) and 0<=r['confidence']<=1:item['confidence']=r['confidence']
        if r.get('category')=='tasks':item['status']=r.get('status') if isinstance(r.get('status'),str) and r.get('status') in statuses else 'unknown'
        items.append(item)
    return {'version':1,'type':'memory-metadata','items':items}
