"""Small, approval-bound foreground control policy; never executes model shell text."""
import re
import os, stat, hashlib, plistlib
import approval_channel

BUNDLE_ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9-]*(?:\.[A-Za-z0-9][A-Za-z0-9-]*)+$')



def app_revision(app):
    """Match native selected bundle path, executable path and content hash."""
    try:
        path=os.path.realpath(app['path'])
        if path!=app['path'] or not path.endswith('.app'): return None
        with open(os.path.join(path,'Contents','Info.plist'),'rb') as f: info=plistlib.load(f)
        name=info.get('CFBundleExecutable')
        if info.get('CFBundleIdentifier')!=app['bundle_id'] or not isinstance(name,str) or not name or os.path.basename(name)!=name: return None
        executable=os.path.realpath(os.path.join(path,'Contents','MacOS',name))
        if not executable.startswith(path+'/'): return None
        h=hashlib.sha256()
        with open(executable,'rb') as f:
            before=os.fstat(f.fileno())
            if not stat.S_ISREG(before.st_mode): return None
            for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
            after=os.fstat(f.fileno())
        current=os.stat(executable)
        if any((x.st_ino,x.st_size,x.st_mtime_ns)!=(before.st_ino,before.st_size,before.st_mtime_ns) for x in (after,current)): return None
        return path+'|'+executable+'|'+h.hexdigest()
    except (OSError,ValueError,KeyError,TypeError,plistlib.InvalidFileException): return None

def handle(request, lookup, approve, launch, focus, click, cancelled, automatic=None, verify_revision=app_revision, background_only=False, background_check=None):
    if not isinstance(request, dict): return {'status':'blocked','text':'Invalid control request.'}
    action=request.get('action'); required={'action','bundle_id'} | ({'target'} if action=='click' else set())
    if action not in ('open_app','focus_app','click') or set(request)!=required:
        return {'status':'blocked','text':'Unsupported control action.'}
    bundle=request.get('bundle_id')
    if not isinstance(bundle,str) or len(bundle)>200 or not BUNDLE_ID.fullmatch(bundle): return {'status':'blocked','text':'An exact installed app identifier is required.'}
    target=request.get('target')
    if action=='click' and (not isinstance(target,str) or not target.strip() or len(target)>120 or target.strip().isdigit() or any(c in target for c in '\r\n>')):
        return {'status':'blocked','text':'An exact named control is required.'}
    if cancelled(): return {'status':'cancelled','text':'The request was cancelled; nothing was done.'}
    active = background_check or (lambda: background_only)
    if active() and action in ('open_app','focus_app'):
        return {'status':'needs_foreground','text':'This action needs an app brought forward. Turn off Do not interrupt my work to proceed.'}
    app=lookup(bundle)
    if not isinstance(app,dict) or app.get('bundle_id')!=bundle or not isinstance(app.get('path'),str) or not app['path'].startswith('/'):
        return {'status':'blocked','text':'The installed app could not be identified.'}
    if action in ('focus_app','click') and (type(app.get('pid')) is not int or app['pid']<=0 or not isinstance(app.get('started'),str) or not app['started']):
        return {'status':'blocked','text':'The app is not running uniquely.'}
    if action=='click':
        inspection=approve({'q':'Inspect this app to find one named control?', 'cmd':bundle+' — '+target+'; no screen text is sent to the model'})
        if inspection!='y' or getattr(inspection,'deadline',None) is not None:
            return {'status':'cancelled','text':'The app was not inspected.'}
        if lookup(bundle)!=app or cancelled() or not approval_channel.authorized(inspection) or active()!=background_only: return {'status':'cancelled','text':'The app or setting changed, or the request was cancelled.'}
        def approve_target(check):
            if cancelled() or not isinstance(check,dict) or check.get('args')!=['click',target] or type(check.get('pid')) is not int or check['pid'] != app.get('pid'):
                return False
            if not isinstance(check.get('windowID'),str) or not check['windowID'].isdigit() or int(check['windowID'])<=0 or check.get('secure') is not False or type(check.get('risky')) is not bool:
                return False
            labels=check.get('labels'); at=check.get('at')
            if not isinstance(labels,list) or len(labels)!=1 or not isinstance(labels[0],str) or labels[0].strip().casefold()!=target.strip().casefold() or not isinstance(at,list) or len(at)!=1:
                return False
            if lookup(bundle)!=app: return False
            window=check.get('window')
            if not isinstance(window,str) or len(window)>200: return False
            question={'q':'Allow this potentially consequential action?' if check['risky'] else 'Allow this control action?', 'cmd':bundle+' · '+(window or 'Untitled')+' · window '+check['windowID']+' · '+labels[0]}
            decision=approve(question)
            if decision!='y' or getattr(decision,'deadline',None) is not None: return False
            return lookup(bundle)==app and not cancelled() and approval_channel.authorized(decision) and active()==background_only
        result=click(bundle,target,approve_target)
        return result if isinstance(result,dict) else {'status':'unverified','text':'The action outcome is unknown; inspect before retrying.'}
    if automatic is not None:
        outcome=automatic(action,app)
        if outcome is not None: return outcome
    decision=approve({'q':'Open this installed app?' if action=='open_app' else 'Focus this running app?', 'cmd':bundle+' — '+app['path']})
    if decision!='y':
        return {'status':'cancelled','text':'The app action was not performed.'}
    revision=getattr(decision,'revision',None)
    if lookup(bundle)!=app or (getattr(decision,'deadline',None) is not None and (not revision or verify_revision(app)!=revision)) or cancelled() or not approval_channel.authorized(decision): return {'status':'cancelled','text':'The app changed, authorization expired, or the request was cancelled.'}
    if active(): return {'status':'needs_foreground','text':'The setting changed; this action needs the foreground. Nothing was done.'}
    result=(launch if action=='open_app' else focus)(app)
    return result if isinstance(result,dict) else {'status':'unverified','text':'The app action could not be verified.'}
