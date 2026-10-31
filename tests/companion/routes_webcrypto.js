'use strict';
// Synthetic loopback shim: no production listener, Keychain, or live provider.
const {spawn}=require('child_process'),readline=require('readline'),{webcrypto}=require('crypto'),http=require('http'),assert=require('assert');
const subtle=webcrypto.subtle,enc=new TextEncoder(),b64=b=>Buffer.from(b).toString('base64'),from=s=>Buffer.from(s,'base64');
function packed(...items){return Buffer.concat(items.map(x=>{x=Buffer.from(x);const n=Buffer.alloc(4);n.writeUInt32BE(x.length);return Buffer.concat([n,x]);}));}
function requestBytes(c){const i=c.intent;return packed(enc.encode('atlas-request-proof-v1'),enc.encode(i.hostID.toLowerCase()),enc.encode(i.deviceID.toLowerCase()),enc.encode(String(i.generation)),enc.encode(i.scopeID),enc.encode(i.scopeRevision),enc.encode(i.action),enc.encode(i.method),enc.encode(i.path),enc.encode(String(i.expiresAt)),from(i.payloadDigest),from(c.nonce));}
function responseBytes(i){return packed(enc.encode('atlas-response-proof-v1'),enc.encode(i.hostID.toLowerCase()),enc.encode(i.deviceID.toLowerCase()),enc.encode(i.requestID.toLowerCase()),enc.encode(String(i.generation)),enc.encode(i.action),enc.encode(i.method),enc.encode(i.path),enc.encode(i.status),from(i.payloadDigest),from(i.requestNonce),enc.encode(String(i.expiresAt)));}
(async()=>{
 const child=spawn(process.argv[2],[],{stdio:['pipe','pipe','inherit']}),lines=readline.createInterface({input:child.stdout})[Symbol.asyncIterator](),write=x=>child.stdin.write(JSON.stringify(x)+'\n');let port;
 const server=http.createServer(async(req,res)=>{let body='';for await(const c of req){body+=c;if(body.length>16384){res.writeHead(413);res.end();return;}}try{const parsed=JSON.parse(body);write({route:req.url,host:req.headers.host,origin:req.headers.origin||'',method:req.method,...parsed});const value=JSON.parse((await lines.next()).value);res.writeHead(value.error?403:200,{'Content-Type':'application/json'});res.end(JSON.stringify(value));}catch(e){res.writeHead(400);res.end();}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));port=server.address().port;
 const keys=await subtle.generateKey({name:'ECDSA',namedCurve:'P-256'},false,['sign','verify']),hostID=webcrypto.randomUUID(),deviceID=webcrypto.randomUUID(),id=webcrypto.randomUUID();
 write({hostID,deviceID,signingPublic:b64(await subtle.exportKey('raw',keys.publicKey)),expectedHost:`127.0.0.1:${port}`});const bootstrap=JSON.parse((await lines.next()).value),mac=await subtle.importKey('raw',from(bootstrap.macPublic),{name:'ECDSA',namedCurve:'P-256'},false,['verify']);
 async function post(path,body,origin='https://atlas-desktop.joelr2.chatgpt.site'){return fetch(`http://127.0.0.1:${port}${path}`,{method:'POST',headers:{Origin:origin,'Content-Type':'application/json'},body:JSON.stringify(body)});}
 async function operation(action,path,payload){
  const bytes=enc.encode(JSON.stringify(payload)),digest=await subtle.digest('SHA-256',bytes),intent={hostID,deviceID,generation:1,scopeID:'project',scopeRevision:'one',action,method:'POST',path,expiresAt:1020,payloadDigest:b64(digest)};
  const c=await (await post('/v1/session/challenge',{intent})).json(),signature=await subtle.sign({name:'ECDSA',hash:'SHA-256'},keys.privateKey,requestBytes(c)),body={operation:{challenge:c,signature:b64(signature),payload:b64(bytes)}};
  const response=await post(path,body);assert.equal(response.status,200);const wire=await response.json(),signed=wire.signed.intent;
  assert.equal(signed.hostID.toLowerCase(),hostID);assert.equal(signed.deviceID.toLowerCase(),deviceID);assert.equal(signed.requestID.toLowerCase(),id);assert.equal(signed.path,path);assert.equal(signed.requestNonce,c.nonce);
  assert.deepEqual(Buffer.from(await subtle.digest('SHA-256',from(wire.payload))),from(signed.payloadDigest));assert(await subtle.verify({name:'ECDSA',hash:'SHA-256'},mac,from(wire.signed.signature),responseBytes(signed)));
  return {body,status:signed.status};
 }
 const first=await operation('submit','/v1/tasks',{id,task:'synthetic'});assert.equal(first.status,'submitted');assert.equal((await post('/v1/tasks',first.body)).status,403);
 assert.equal((await operation('status','/v1/tasks/status',{id})).status,'submitted');assert.equal((await operation('stop','/v1/tasks/stop',{id})).status,'stopped');
 assert.equal((await post('/v1/session/challenge',{intent:{}},'https://evil.example')).status,403);
 assert.equal((await post('/test/revoke',{})).status,200);
 const rejected=await post('/v1/session/challenge',{intent:{hostID,deviceID,generation:1,scopeID:'project',scopeRevision:'one',action:'status',method:'POST',path:'/v1/tasks/status',expiresAt:1020,payloadDigest:b64(await subtle.digest('SHA-256',enc.encode('{}')))}});assert.equal(rejected.status,403);
 child.stdin.end();await new Promise(resolve=>server.close(resolve));assert.equal(await new Promise(resolve=>child.on('exit',resolve)),0);console.log('synthetic signed routes loopback and revocation ok');
})().catch(e=>{console.error(e);process.exitCode=1});
