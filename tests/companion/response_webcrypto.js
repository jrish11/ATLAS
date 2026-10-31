'use strict';
const {execFileSync}=require('child_process'),{webcrypto}=require('crypto'),assert=require('assert');const subtle=webcrypto.subtle,enc=new TextEncoder();
function packed(...items){return Buffer.concat(items.map(x=>{x=Buffer.from(x);const n=Buffer.alloc(4);n.writeUInt32BE(x.length);return Buffer.concat([n,x]);}));}
(async()=>{const fixture=JSON.parse(execFileSync(process.argv[2],{encoding:'utf8'})),i=fixture.response.intent;
 const data=packed(enc.encode('atlas-response-proof-v1'),enc.encode(i.hostID.toLowerCase()),enc.encode(i.deviceID.toLowerCase()),enc.encode(i.requestID.toLowerCase()),enc.encode(String(i.generation)),enc.encode(i.action),enc.encode(i.method),enc.encode(i.path),enc.encode(i.status),Buffer.from(i.payloadDigest,'base64'),Buffer.from(i.requestNonce,'base64'),enc.encode(String(i.expiresAt)));
 const key=await subtle.importKey('raw',Buffer.from(fixture.publicKey,'base64'),{name:'ECDSA',namedCurve:'P-256'},false,['verify']);
 assert(await subtle.verify({name:'ECDSA',hash:'SHA-256'},key,Buffer.from(fixture.response.signature,'base64'),data));
 assert.deepEqual(Buffer.from(await subtle.digest('SHA-256',Buffer.from(fixture.payload,'base64'))),Buffer.from(i.payloadDigest,'base64'));
 data[data.length-1]^=1;assert.equal(await subtle.verify({name:'ECDSA',hash:'SHA-256'},key,Buffer.from(fixture.response.signature,'base64'),data),false);
 console.log('synthetic signed-response WebCrypto interop ok');
})().catch(e=>{console.error(e);process.exitCode=1});
