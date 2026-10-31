'use strict';
// Node's WebCrypto checks wire compatibility; it does not establish Safari support.
const assert=require('assert'),{spawn}=require('child_process'),readline=require('readline'),{webcrypto}=require('crypto');
const subtle=webcrypto.subtle,enc=new TextEncoder(),b64=b=>Buffer.from(b).toString('base64');
function field(...items){return Buffer.concat(items.map(x=>{x=Buffer.from(x);let n=Buffer.alloc(4);n.writeUInt32BE(x.length);return Buffer.concat([n,x])}));}
(async()=>{
 const child=spawn(process.argv[2],[],{stdio:['pipe','pipe','inherit']}),lines=readline.createInterface({input:child.stdout})[Symbol.asyncIterator]();
 const challenge=JSON.parse((await lines.next()).value);
 const ecdh=await subtle.generateKey({name:'ECDH',namedCurve:'P-256'},false,['deriveBits']);
 const pub=await subtle.exportKey('raw',ecdh.publicKey),peer=await subtle.importKey('raw',Buffer.from(challenge.macEphemeral,'base64'),{name:'ECDH',namedCurve:'P-256'},false,[]);
 const shared=await subtle.deriveBits({name:'ECDH',public:peer},ecdh.privateKey,256);
 const response={phoneName:'Synthetic phone',nonce:challenge.nonce,phoneEphemeral:b64(pub)};
 const transcript=field(enc.encode('atlas-enrollment-v1'),enc.encode(challenge.hostID.toLowerCase()),enc.encode(challenge.origin),enc.encode(challenge.macName),Buffer.from(challenge.nonce,'base64'),Buffer.from(challenge.macEphemeral,'base64'),Buffer.from(challenge.macSigningPublic,'base64'),enc.encode(response.phoneName),Buffer.from(response.nonce,'base64'),Buffer.from(response.phoneEphemeral,'base64'));
 const salt=await subtle.digest('SHA-256',transcript),material=await subtle.importKey('raw',shared,'HKDF',false,['deriveKey']);
 const hmac=await subtle.deriveKey({name:'HKDF',hash:'SHA-256',salt,info:enc.encode('atlas-pair-channel-v1')},material,{name:'HMAC',hash:'SHA-256',length:256},false,['sign']);
 const tag=Buffer.from(await subtle.sign('HMAC',hmac,field(enc.encode('compare'),transcript)));const code=String(tag.readUInt32BE(0)&0x3fffffff).padStart(10,'0');
 const signing=await subtle.generateKey({name:'ECDSA',namedCurve:'P-256'},false,['sign','verify']);
 await assert.rejects(()=>subtle.exportKey('pkcs8',signing.privateKey));
 const signingPublic=await subtle.exportKey('raw',signing.publicKey),signature=await subtle.sign({name:'ECDSA',hash:'SHA-256'},signing.privateKey,enc.encode('atlas-webcrypto-interop-v1'));
 child.stdin.end(JSON.stringify({response,signingPublic:b64(signingPublic),signature:b64(signature)})+'\n');
 assert.equal((await lines.next()).value,code);const exit=await new Promise(resolve=>child.on('exit',resolve));assert.equal(exit,0);console.log('synthetic Swift/WebCrypto interop ok');
})().catch(e=>{console.error(e);process.exitCode=1});
