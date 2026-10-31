"""Disabled-by-default loopback transport fixture for RemoteGate.

This module is not started by ATLAS. Its caller must supply a trusted bridge and
owner-created session. It never configures a network proxy or persists secrets.
"""
import hmac
import json
import secrets
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from remote_gate import RemoteError, valid_origin

MAX_BODY = 8192

class Pairing:
    """One-use in-memory invitation; trusted owner must explicitly construct it."""
    def __init__(self, origin, clock, expires, *, code=None):
        if not valid_origin(origin) or not clock() < expires <= clock()+3600:
            raise ValueError('Invalid pairing scope or expiry')
        self.origin, self.clock, self.expires = origin, clock, expires
        if code is not None and (not isinstance(code,str) or not code.isascii() or len(code)<32 or len(code)>256): raise ValueError('Invalid invitation')
        self._code = code or secrets.token_urlsafe(32)
        self._lock = threading.Lock()
        self._used = False

    @property
    def invitation(self):
        return self._code

    def consume(self, code):
        with self._lock:
            if self._used or self.clock() >= self.expires or not isinstance(code,str) or not code.isascii() or not hmac.compare_digest(code,self._code):
                raise RemoteError('Invalid or expired invitation')
            self._used = True
            return secrets.token_urlsafe(32), secrets.token_urlsafe(32)

    def redeem(self, code, device, confirm, token, csrf):
        # Claim first: denial, interruption and concurrent requests all consume
        # the invitation. Only a native decision can release the credentials.
        with self._lock:
            if self._used or self.clock() >= self.expires or not isinstance(code,str) or not code.isascii() or not hmac.compare_digest(code,self._code):
                raise RemoteError('Invalid or expired invitation')
            self._used=True
        if not isinstance(device,str) or not device.strip() or len(device)>80 or any(ord(c)<32 or ord(c)==127 for c in device): raise RemoteError('Invalid device')
        if confirm(device) is not True or self.clock()>=self.expires: raise RemoteError('Pairing denied or expired')
        return token,csrf

class LoopbackServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False
    def __init__(self, gate, origin, port=0, pairing=None):
        if not valid_origin(origin): raise ValueError('Invalid origin')
        self.gate, self.origin, self.pairing = gate, origin, pairing
        self.paired=pairing is None
        super().__init__(('127.0.0.1', port), Handler)

class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args): pass
    def do_GET(self):
        if self.path!='/' or self.server.pairing is None or self.headers.get_all('Host') != [urlsplit(self.server.origin).netloc]:
            self.reply(403,{'error':'Request rejected'});return
        try: data=(Path(__file__).parent/'ui'/'remote-phone.html').read_bytes()
        except OSError: self.reply(503,{'error':'Unavailable'});return
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.send_header('Cache-Control','no-store');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Length',str(len(data)));self.send_header('Connection','close');self.end_headers()
        try:self.wfile.write(data)
        except OSError:pass
        self.close_connection=True
    def do_POST(self):
        # No CORS, redirects, cookies, query parameters or web-accessible enable.
        try:
            if self.path not in ('/task','/status','/stop','/pair'): raise ValueError()
            if self.headers.get_all('Host') != [urlsplit(self.server.origin).netloc] or self.headers.get_all('Origin') != [self.server.origin]: raise ValueError()
            if self.headers.get_all('Content-Type') != ['application/json']: raise ValueError()
            lengths = self.headers.get_all('Content-Length')
            if not lengths or len(lengths)!=1 or not lengths[0].isdigit() or not 0<int(lengths[0])<=MAX_BODY or self.headers.get('Transfer-Encoding') is not None: raise ValueError()
            self.connection.settimeout(3)
            def pairs(items):
                result={}
                for k,v in items:
                    if k in result: raise ValueError()
                    result[k]=v
                return result
            body=json.loads(self.rfile.read(int(lengths[0])), object_pairs_hook=pairs)
            if self.path=='/pair':
                if self.server.pairing is None or not isinstance(body,dict) or set(body)!={'code','device'}: raise ValueError()
                token,csrf=self.server.pairing(body['code'],body['device'])
                self.server.paired=True
                self.reply(200,{'token':token,'csrf':csrf});return
            if not self.server.paired: raise ValueError()
            token=self.headers.get_all('X-Atlas-Token'); csrf=self.headers.get_all('X-Atlas-CSRF')
            if not token or len(token)!=1 or not csrf or len(csrf)!=1: raise ValueError()
            args=dict(host=self.headers['Host'],origin=self.headers['Origin'],token=token[0],csrf=csrf[0])
            if self.path=='/task': result=self.server.gate.request(**args,body=body)
            else:
                if not isinstance(body,dict) or set(body)!={'id'}: raise ValueError()
                result=(self.server.gate.status if self.path=='/status' else self.server.gate.stop)(**args,ident=body['id'])
            self.reply(200,result)
        except (ValueError, RemoteError, TimeoutError, OSError): self.reply(403,{'error':'Request rejected'})
    def reply(self, status, obj):
        data=json.dumps(obj,separators=(',',':')).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(data)));self.send_header('Connection','close');self.end_headers()
        try:self.wfile.write(data)
        except OSError:pass
        self.close_connection=True
