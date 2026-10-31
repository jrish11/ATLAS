'use strict';
const {spawn}=require('child_process'),readline=require('readline'),{webcrypto}=require('crypto'),assert=require('assert');
const subtle=webcrypto.subtle,enc=new TextEncoder(),b64=b=>Buffer.from(b).toString('base64');
function packed(...items){return Buffer.concat(items.map(x=>{x=Buffer.from(x);const n=Buffer.alloc(4);n.writeUInt32BE(x.length);return Buffer.concat([n,x]);}));}
(async()=>{
 const keys=await subtle.generateKey({name:'ECDSA',namedCurve:'P-256'},false,['sign','verify']);await assert.rejects(()=>subtle.exportKey('pkcs8',keys.privateKey));
 const child=spawn(process.argv[2],[],{stdio:['pipe','pipe','inherit']}),lines=readline.createInterface({input:child.stdout})[Symbol.asyncIterator]();
 const hostID=webcrypto.randomUUID(),deviceID=webcrypto.randomUUID();child.stdin.write(JSON.stringify({hostID,deviceID,signingPublic:b64(await subtle.exportKey('raw',keys.publicKey))})+'\n');
 const c=JSON.parse((await lines.next()).value),i=c.intent;
 const data=packed(enc.encode('atlas-request-proof-v1'),enc.encode(i.hostID.toLowerCase()),enc.encode(i.deviceID.toLowerCase()),enc.encode(String(i.generation)),enc.encode(i.scopeID),enc.encode(i.scopeRevision),enc.encode(i.action),enc.encode(i.method),enc.encode(i.path),enc.encode(String(i.expiresAt)),Buffer.from(i.payloadDigest,'base64'),Buffer.from(c.nonce,'base64'));
 child.stdin.end(JSON.stringify({signature:b64(await subtle.sign({name:'ECDSA',hash:'SHA-256'},keys.privateKey,data))})+'\n');
 assert.equal(JSON.parse((await lines.next()).value).status,'verified-then-revoked');assert.equal(await new Promise(resolve=>child.on('exit',resolve)),0);console.log('synthetic WebCrypto signed request and revocation ok');
})().catch(e=>{console.error(e);process.exitCode=1});
