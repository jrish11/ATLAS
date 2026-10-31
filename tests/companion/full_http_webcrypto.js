'use strict';
// Synthetic loopback shim. Native owner decisions use the child control pipe,
// not HTTP. No real Keychain, Tailscale, persistent route, or live task is used.
const {spawn}=require('child_process'),readline=require('readline'),{webcrypto}=require('crypto'),http=require('http'),assert=require('assert'),fs=require('fs'),os=require('os'),pathUtil=require('path');
const subtle=webcrypto.subtle,enc=new TextEncoder(),b64=x=>Buffer.from(x).toString('base64'),from=x=>Buffer.from(x,'base64'),origin='https://atlas-desktop.joelr2.chatgpt.site';
function packed(...items){return Buffer.concat(items.map(x=>{x=Buffer.from(x);let n=Buffer.alloc(4);n.writeUInt32BE(x.length);return Buffer.concat([n,x])}));}
function identity(role,binding,host,phone,macPub,phonePub){return packed(enc.encode('atlas-identity-proof-v1'),enc.encode(role),binding,enc.encode(host.toLowerCase()),enc.encode(phone.toLowerCase()),enc.encode('1'),macPub,phonePub);}
function aad(role,binding){return packed(enc.encode('atlas-enrollment-aead-v1'),enc.encode(role),binding);}
function reqProof(c){let i=c.intent;return packed(enc.encode('atlas-request-proof-v1'),enc.encode(i.hostID.toLowerCase()),enc.encode(i.deviceID.toLowerCase()),enc.encode(String(i.generation)),enc.encode(i.scopeID),enc.encode(i.scopeRevision),enc.encode(i.action),enc.encode(i.method),enc.encode(i.path),enc.encode(String(i.expiresAt)),from(i.payloadDigest),from(c.nonce));}
function respProof(i){return packed(enc.encode('atlas-response-proof-v1'),enc.encode(i.hostID.toLowerCase()),enc.encode(i.deviceID.toLowerCase()),enc.encode(i.requestID.toLowerCase()),enc.encode(String(i.generation)),enc.encode(i.action),enc.encode(i.method),enc.encode(i.path),enc.encode(i.status),from(i.payloadDigest),from(i.requestNonce),enc.encode(String(i.expiresAt)));}
function receiptProof(d){return packed(enc.encode('atlas-pair-receipt-v1'),enc.encode(d.hostID.toLowerCase()),enc.encode(d.phoneID.toLowerCase()),enc.encode(d.phoneName),enc.encode(String(d.generation)),from(d.binding),from(d.macPublic),from(d.phonePublic));}
(async()=>{
 const loss=process.argv[3]==='--ack-loss',httpRecovery=process.argv[3]==='--http-recovery',durable=loss||process.argv[3]==='--durable',temp=durable?fs.mkdtempSync(pathUtil.join(os.tmpdir(),'atlas-synthetic-pair-')):null;
 const child=spawn(process.argv[2],durable?(loss?[temp,'--lose-ack']:[temp]):[],{stdio:['pipe','pipe','inherit']}),exited=new Promise(resolve=>child.on('exit',resolve)),lines=readline.createInterface({input:child.stdout})[Symbol.asyncIterator](),write=x=>child.stdin.write(JSON.stringify(x)+'\n'),control=async x=>{write(x);return JSON.parse((await lines.next()).value);};
 const challenge=JSON.parse((await lines.next()).value),macPub=from(challenge.macSigningPublic),fingerprint=Buffer.from(await subtle.digest('SHA-256',macPub)).toString('hex');assert.equal(challenge.origin,'https://atlas.example');
 const server=http.createServer(async(req,res)=>{let body=[];for await(const b of req)body.push(b);try{const wire=await control({kind:'http',method:req.method,path:req.url,host:req.headers.host,origin:req.headers.origin||'',body:b64(Buffer.concat(body))});res.writeHead(wire.code,wire.headers);res.end(from(wire.body));}catch(e){res.writeHead(500);res.end();}});
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const port=server.address().port;
 function post(path,value,originHeader=origin){return new Promise((resolve,reject)=>{const data=Buffer.from(JSON.stringify(value)),req=http.request({host:'127.0.0.1',port,path,method:'POST',headers:{Host:'atlas.example',Origin:originHeader,'Content-Type':'application/json','Content-Length':data.length}},res=>{let chunks=[];res.on('data',x=>chunks.push(x));res.on('end',()=>{try{resolve({status:res.statusCode,body:JSON.parse(Buffer.concat(chunks).toString())});}catch(e){reject(e);}});});req.on('error',reject);req.end(data);});}
 const ecdh=await subtle.generateKey({name:'ECDH',namedCurve:'P-256'},false,['deriveBits']),ephemeral=await subtle.exportKey('raw',ecdh.publicKey),peer=await subtle.importKey('raw',from(challenge.macEphemeral),{name:'ECDH',namedCurve:'P-256'},false,[]),shared=await subtle.deriveBits({name:'ECDH',public:peer},ecdh.privateKey,256);
 const response={phoneName:'Synthetic phone',nonce:challenge.nonce,phoneEphemeral:b64(ephemeral)};
 const transcript=packed(enc.encode('atlas-enrollment-v1'),enc.encode(challenge.hostID.toLowerCase()),enc.encode(challenge.origin),enc.encode(challenge.macName),from(challenge.nonce),from(challenge.macEphemeral),macPub,enc.encode(response.phoneName),from(response.nonce),from(response.phoneEphemeral)),binding=Buffer.from(await subtle.digest('SHA-256',transcript));
 const material=await subtle.importKey('raw',shared,'HKDF',false,['deriveKey']),hkdf={name:'HKDF',hash:'SHA-256',salt:binding,info:enc.encode('atlas-pair-channel-v1')},hmac=await subtle.deriveKey(hkdf,material,{name:'HMAC',hash:'SHA-256',length:256},false,['sign']),channel=await subtle.deriveKey(hkdf,material,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);
 const code=String(Buffer.from(await subtle.sign('HMAC',hmac,packed(enc.encode('compare'),transcript))).readUInt32BE(0)&0x3fffffff).padStart(10,'0');
 assert.equal((await post('/v1/enrollment/join',response,'https://evil.example')).status,403);
 const joined=await post('/v1/enrollment/join',response);assert.equal(joined.status,200);assert.equal(joined.body.state,'pending');const attemptID=joined.body.attemptID;
 assert.equal((await control({kind:'owner-approve',attemptID,code,fingerprint})).status,'approved-locally');
 const seal=async(role,value)=>{const iv=webcrypto.getRandomValues(new Uint8Array(12)),cipher=await subtle.encrypt({name:'AES-GCM',iv,additionalData:aad(role,binding)},channel,enc.encode(JSON.stringify(value)));return {iv:b64(iv),ciphertext:b64(cipher)};};
 const open=async(role,e)=>JSON.parse(Buffer.from(await subtle.decrypt({name:'AES-GCM',iv:from(e.iv),additionalData:aad(role,binding)},channel,from(e.ciphertext))).toString());
 const status=await post('/v1/enrollment/status',{attemptID});assert.equal((await open('approval',status.body)).state,'approved');
 const phone=await subtle.generateKey({name:'ECDSA',namedCurve:'P-256'},false,['sign','verify']);await assert.rejects(()=>subtle.exportKey('pkcs8',phone.privateKey));const phoneID=webcrypto.randomUUID(),phonePub=Buffer.from(await subtle.exportKey('raw',phone.publicKey));
 const sign=async role=>subtle.sign({name:'ECDSA',hash:'SHA-256'},phone.privateKey,identity(role,binding,challenge.hostID,phoneID,macPub,phonePub));
 const finish=await post('/v1/enrollment/finish',await seal('phone',{deviceID:phoneID,generation:1,publicKey:b64(phonePub),signature:b64(await sign('phone'))})),macClaim=await open('mac',finish.body),mac=await subtle.importKey('raw',macPub,{name:'ECDSA',namedCurve:'P-256'},false,['verify']);
 assert(await subtle.verify({name:'ECDSA',hash:'SHA-256'},mac,from(macClaim.signature),identity('mac',binding,challenge.hostID,phoneID,macPub,phonePub)));
 const ackEnvelope=await seal('ack',{signature:b64(await sign('ack'))});
 if(loss){
  let uncertain=false;try{await post('/v1/enrollment/ack',ackEnvelope);}catch(e){uncertain=true;}assert(uncertain);assert.equal(await exited,0);
  const recovery=spawn(process.argv[2],['--recover',temp,phoneID],{stdio:['pipe','pipe','inherit']}),recoveryExit=new Promise(resolve=>recovery.on('exit',resolve)),recoveryLines=readline.createInterface({input:recovery.stdout})[Symbol.asyncIterator]();
  const c=JSON.parse((await recoveryLines.next()).value),d=c.descriptor;assert.equal(d.hostID.toLowerCase(),challenge.hostID.toLowerCase());assert.equal(d.phoneID.toLowerCase(),phoneID);assert.deepEqual(from(d.macPublic),macPub);assert.deepEqual(from(d.phonePublic),phonePub);assert.deepEqual(from(d.binding),binding);
  const recoveryMessage=packed(enc.encode('atlas-pair-recovery-v1'),enc.encode(d.hostID.toLowerCase()),enc.encode(d.phoneID.toLowerCase()),enc.encode(String(d.generation)),from(d.binding),from(c.nonce));
  recovery.stdin.end(JSON.stringify({signature:b64(await subtle.sign({name:'ECDSA',hash:'SHA-256'},phone.privateKey,recoveryMessage))})+'\n');
  const receipt=JSON.parse((await recoveryLines.next()).value);assert(await subtle.verify({name:'ECDSA',hash:'SHA-256'},mac,from(receipt.signature),receiptProof(receipt.descriptor)));assert.equal(await recoveryExit,0);
  await new Promise(resolve=>server.close(resolve));fs.rmSync(temp,{recursive:true,force:true});console.log('synthetic durable ack-loss recovery ok');return;
 }
 if(httpRecovery){
  const committed=await post('/v1/enrollment/ack',ackEnvelope);assert.equal(committed.status,200); // Deliberately discard the receipt.
  assert.equal((await post('/v1/enrollment/recovery/challenge',{phoneID})).status,403);
  assert.equal((await control({kind:'owner-review'})).status,'reviewed-locally');
  assert.equal((await control({kind:'owner-recovery',phoneID})).status,'recovery-approved-locally');
  const start=await post('/v1/enrollment/recovery/challenge',{phoneID});assert.equal(start.status,200);
  const c=start.body,d=c.descriptor;assert.equal(d.phoneID.toLowerCase(),phoneID);assert.deepEqual(from(d.macPublic),macPub);assert.deepEqual(from(d.phonePublic),phonePub);assert.deepEqual(from(d.binding),binding);
  const message=packed(enc.encode('atlas-pair-recovery-v1'),enc.encode(d.hostID.toLowerCase()),enc.encode(d.phoneID.toLowerCase()),enc.encode(String(d.generation)),from(d.binding),from(c.nonce));
  const request={challenge:c,signature:b64(await subtle.sign({name:'ECDSA',hash:'SHA-256'},phone.privateKey,message))},result=await post('/v1/enrollment/recovery/finish',request);
  assert.equal(result.status,200);assert(await subtle.verify({name:'ECDSA',hash:'SHA-256'},mac,from(result.body.signature),receiptProof(result.body.descriptor)));assert.equal((await post('/v1/enrollment/recovery/finish',request)).status,403);
  child.stdin.end();await new Promise(resolve=>server.close(resolve));assert.equal(await exited,0);console.log('synthetic WebCrypto HTTP pairing recovery ok');return;
 }
 const ack=await post('/v1/enrollment/ack',ackEnvelope),receipt=await open('receipt',ack.body),d=receipt.descriptor;
 assert(await subtle.verify({name:'ECDSA',hash:'SHA-256'},mac,from(receipt.signature),receiptProof(d)));assert.equal(d.phoneID.toLowerCase(),phoneID);assert.equal((await control({kind:'owner-session'})).status,'session-approved-locally');
 const taskID=webcrypto.randomUUID();
 async function op(action,path,payload){const bytes=enc.encode(JSON.stringify(payload)),intent={hostID:challenge.hostID,deviceID:phoneID,generation:1,scopeID:'project',scopeRevision:'one',action,method:'POST',path,expiresAt:1020,payloadDigest:b64(await subtle.digest('SHA-256',bytes))};
  const c=await post('/v1/session/challenge',{intent});assert.equal(c.status,200);const sig=await subtle.sign({name:'ECDSA',hash:'SHA-256'},phone.privateKey,reqProof(c.body)),body={challenge:c.body,signature:b64(sig),payload:b64(bytes)},result=await post(path,body);assert.equal(result.status,200);
  let r=result.body.signed.intent;assert.equal(r.requestID.toLowerCase(),taskID);assert.equal(r.requestNonce,c.body.nonce);assert(await subtle.verify({name:'ECDSA',hash:'SHA-256'},mac,from(result.body.signed.signature),respProof(r)));assert.deepEqual(Buffer.from(await subtle.digest('SHA-256',from(result.body.payload))),from(r.payloadDigest));return {body,status:r.status};}
 const sent=await op('submit','/v1/tasks',{id:taskID,task:'synthetic'});assert.equal(sent.status,'submitted');assert.equal((await post('/v1/tasks',sent.body)).status,403);
 assert.equal((await op('status','/v1/tasks/status',{id:taskID})).status,'submitted');assert.equal((await op('stop','/v1/tasks/stop',{id:taskID})).status,'stopped');assert.equal((await control({kind:'owner-revoke'})).status,'revoked-locally');
 const staleIntent={hostID:challenge.hostID,deviceID:phoneID,generation:1,scopeID:'project',scopeRevision:'one',action:'status',method:'POST',path:'/v1/tasks/status',expiresAt:1020,payloadDigest:b64(await subtle.digest('SHA-256',enc.encode('{}')))};assert.equal((await post('/v1/session/challenge',{intent:staleIntent})).status,403);
 child.stdin.end();await new Promise(resolve=>server.close(resolve));assert.equal(await exited,0);if(temp)fs.rmSync(temp,{recursive:true,force:true});console.log('strict HTTP synthetic WebCrypto full flow ok');
})().catch(e=>{console.error(e);process.exitCode=1});
