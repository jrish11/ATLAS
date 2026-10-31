'use strict';
const {spawn}=require('child_process'),readline=require('readline'),{webcrypto}=require('crypto'),assert=require('assert'),http=require('http');
const subtle=webcrypto.subtle,enc=new TextEncoder(),b64=b=>Buffer.from(b).toString('base64'),from=s=>Buffer.from(s,'base64');
function packed(...items){return Buffer.concat(items.map(x=>{x=Buffer.from(x);const n=Buffer.alloc(4);n.writeUInt32BE(x.length);return Buffer.concat([n,x]);}));}
function identity(role,binding,host,phone,macPub,phonePub){return packed(enc.encode('atlas-identity-proof-v1'),enc.encode(role),binding,enc.encode(host.toLowerCase()),enc.encode(phone.toLowerCase()),enc.encode('1'),macPub,phonePub);}
function aad(role,binding){return packed(enc.encode('atlas-enrollment-aead-v1'),enc.encode(role),binding);}
(async()=>{
 const child=spawn(process.argv[2],[],{stdio:['pipe','pipe','inherit']}),lines=readline.createInterface({input:child.stdout})[Symbol.asyncIterator](),write=x=>child.stdin.write(JSON.stringify(x)+'\n');
 let server=null,port=null;
 if(process.argv[3]==='--loopback') {
  server=http.createServer(async(req,res)=>{if(req.method!=='POST'||req.headers.host!==`127.0.0.1:${port}`||req.headers.origin!=='https://atlas-desktop.joelr2.chatgpt.site'||!['/v1/enrollment/join','/v1/enrollment/finish','/v1/enrollment/ack'].includes(req.url)){res.writeHead(403);res.end();return;}let body='';for await(const chunk of req){body+=chunk;if(body.length>8192){res.writeHead(413);res.end();return;}}try{write(JSON.parse(body));const reply=await lines.next();res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(reply.value);}catch(e){res.writeHead(400);res.end();}});
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));port=server.address().port;
  const bad=await fetch(`http://127.0.0.1:${port}/v1/enrollment/join`,{method:'POST',headers:{Origin:'https://evil.example'},body:'{}'});assert.equal(bad.status,403);
 }
 const exchange=async(path,value)=>{if(!server){write(value);return JSON.parse((await lines.next()).value);}const response=await fetch(`http://127.0.0.1:${port}${path}`,{method:'POST',headers:{Origin:'https://atlas-desktop.joelr2.chatgpt.site','Content-Type':'application/json'},body:JSON.stringify(value)});assert.equal(response.status,200);return response.json();};
 const c=JSON.parse((await lines.next()).value),phoneID=webcrypto.randomUUID(),ephemeral=await subtle.generateKey({name:'ECDH',namedCurve:'P-256'},false,['deriveBits']);
 const phoneEph=await subtle.exportKey('raw',ephemeral.publicKey),macEph=await subtle.importKey('raw',from(c.macEphemeral),{name:'ECDH',namedCurve:'P-256'},false,[]);
 const shared=await subtle.deriveBits({name:'ECDH',public:macEph},ephemeral.privateKey,256),response={phoneName:'Synthetic phone',nonce:c.nonce,phoneEphemeral:b64(phoneEph)};
 const transcript=packed(enc.encode('atlas-enrollment-v1'),enc.encode(c.hostID.toLowerCase()),enc.encode(c.origin),enc.encode(c.macName),from(c.nonce),from(c.macEphemeral),from(c.macSigningPublic),enc.encode(response.phoneName),from(response.nonce),from(response.phoneEphemeral));
 const binding=Buffer.from(await subtle.digest('SHA-256',transcript)),material=await subtle.importKey('raw',shared,'HKDF',false,['deriveKey']),hkdf={name:'HKDF',hash:'SHA-256',salt:binding,info:enc.encode('atlas-pair-channel-v1')};
 const hmac=await subtle.deriveKey(hkdf,material,{name:'HMAC',hash:'SHA-256',length:256},false,['sign']),channel=await subtle.deriveKey(hkdf,material,{name:'AES-GCM',length:256},false,['encrypt','decrypt']);
 const tag=Buffer.from(await subtle.sign('HMAC',hmac,packed(enc.encode('compare'),transcript))),code=String(tag.readUInt32BE(0)&0x3fffffff).padStart(10,'0');
 const compare=await exchange('/v1/enrollment/join',response);assert.equal(compare.code,code);assert.equal(compare.fingerprint,Buffer.from(await subtle.digest('SHA-256',from(c.macSigningPublic))).toString('hex'));
 const key=await subtle.generateKey({name:'ECDSA',namedCurve:'P-256'},false,['sign','verify']);await assert.rejects(()=>subtle.exportKey('pkcs8',key.privateKey));
 const phonePub=Buffer.from(await subtle.exportKey('raw',key.publicKey)),macPub=from(c.macSigningPublic),sign=async role=>subtle.sign({name:'ECDSA',hash:'SHA-256'},key.privateKey,identity(role,binding,c.hostID,phoneID,macPub,phonePub));
 const seal=async(role,value)=>{const iv=webcrypto.getRandomValues(new Uint8Array(12)),cipher=await subtle.encrypt({name:'AES-GCM',iv,additionalData:aad(role,binding)},channel,enc.encode(JSON.stringify(value)));return {iv:b64(iv),ciphertext:b64(cipher)};};
 const envelope=await exchange('/v1/enrollment/finish',await seal('phone',{deviceID:phoneID.toUpperCase(),generation:1,publicKey:b64(phonePub),signature:b64(await sign('phone'))})),mac=JSON.parse(Buffer.from(await subtle.decrypt({name:'AES-GCM',iv:from(envelope.iv),additionalData:aad('mac',binding)},channel,from(envelope.ciphertext))).toString());
 assert.deepEqual(from(mac.publicKey),macPub);assert.equal(mac.deviceID.toLowerCase(),c.hostID.toLowerCase());
 const verifyKey=await subtle.importKey('raw',macPub,{name:'ECDSA',namedCurve:'P-256'},false,['verify']);assert(await subtle.verify({name:'ECDSA',hash:'SHA-256'},verifyKey,from(mac.signature),identity('mac',binding,c.hostID,phoneID,macPub,phonePub)));
 assert.equal((await exchange('/v1/enrollment/ack',await seal('ack',{signature:b64(await sign('ack'))}))).status,'verified-in-memory');if(server)await new Promise(resolve=>server.close(resolve));child.stdin.end();const exit=await new Promise(resolve=>child.on('exit',resolve));assert.equal(exit,0);console.log('synthetic encrypted Swift/WebCrypto completion ok');
})().catch(e=>{console.error(e);process.exitCode=1});
