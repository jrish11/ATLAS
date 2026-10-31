import Cocoa
import CryptoKit
import Darwin
final class MemoryStorage:SecureDeviceStorage {let storageIdentifier=UUID().uuidString;var data:Data?;func read()throws->Data?{data};func write(_ d:Data)throws{data=d};func delete()throws{data=nil}}
struct AttemptReply:Decodable {let attemptID:UUID;let state:String}
@main struct Fixture {
 static func main() throws {
  let repo=CommandLine.arguments[1],requestedRoot=CommandLine.arguments[2]
  try FileManager.default.createDirectory(atPath:requestedRoot,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])
  guard let canonical=realpath(requestedRoot,nil) else {throw ProofError.invalid};let root=String(cString:canonical);free(canonical)
  for dir in [root,root+"/profile",root+"/project"] {try FileManager.default.createDirectory(atPath:dir,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700])}
  let attrs=try FileManager.default.attributesOfItem(atPath:root+"/project"),dev=(attrs[.systemNumber] as! NSNumber).intValue,ino=(attrs[.systemFileNumber] as! NSNumber).intValue
  var scale=mach_timebase_info_data_t();mach_timebase_info(&scale)
  let clock:()->Double={Double(mach_continuous_time())*Double(scale.numer)/Double(scale.denom)/1_000_000_000},expiry=clock()+60
  let scope=RemoteNativeOwner.Scope(folder:root+"/project",id:"project",revision:"r1",device:dev,inode:ino,expires:expiry)
  let activation=RemoteNativeOwner.Activation(origin:"https://atlas.example",token:String(repeating:"t",count:32),csrf:String(repeating:"c",count:32),invitation:String(repeating:"i",count:32))
  var approvals=0
  let owner=RemoteNativeOwner(scope:scope,clock:clock,activation:activation,requiresDevice:true,decide:{target,done in precondition(target["task"] as? String == "synthetic task");let device=target["pairedDevice"] as? [String:Any];precondition(device?["name"] as? String == "Synthetic Phone" && device?["macFingerprint"] != nil && device?["fingerprint"] != nil && device?["macName"] as? String == "Mac");approvals += 1;done(true)})
  var fds:[Int32]=[-1,-1];precondition(socketpair(AF_UNIX,SOCK_STREAM,0,&fds)==0);_ = fcntl(fds[0],F_SETFD,FD_CLOEXEC);_ = fcntl(fds[1],F_SETFD,FD_CLOEXEC)
  let p=Process(),input=Pipe(),output=Pipe(),child=FileHandle(fileDescriptor:fds[1],closeOnDealloc:true)
  p.executableURL=URL(fileURLWithPath:"/usr/bin/python3");p.arguments=[repo+"/tests/companion_registry_worker.py",root];p.standardInput=input;p.standardOutput=output;p.standardError=child
  var env=ProcessInfo.processInfo.environment;env["PYTHONPYCACHEPREFIX"]=root+"/cache";p.environment=env
  try p.run();try child.close()
  let bootstrap=try JSONSerialization.data(withJSONObject:["kind":"native-authority","key":String(repeating:"a",count:64)]),n=bootstrap.count
  var frame=Data([UInt8((n>>24)&255),UInt8((n>>16)&255),UInt8((n>>8)&255),UInt8(n&255)]);frame.append(bootstrap);try FileHandle(fileDescriptor:fds[0],closeOnDealloc:false).write(contentsOf:frame);try owner.attach(fd:fds[0])
  let writeLock=NSLock()
  func send(_ msg:[String:Any])->Bool {var m=msg;m["nativeAuthority"]=String(repeating:"a",count:64);guard let data=try? JSONSerialization.data(withJSONObject:m) else{return false};writeLock.lock();defer{writeLock.unlock()};do{try input.fileHandleForWriting.write(contentsOf:data+Data([10]));return true}catch{return false}}
  let bridge=NativeCompanionTransport(timeout:5,send:send,stop:{_ = send(["action":"remote-stop"])})
  let forged=CommandLine.arguments.contains("--forged"),mismatched=CommandLine.arguments.contains("--mismatch")
  var ready=false,failed=false,buffer=Data()
  output.fileHandleForReading.readabilityHandler={file in let data=file.availableData;DispatchQueue.main.async {buffer.append(data);while let i=buffer.firstIndex(of:10) {let one=Data(buffer[..<i]);buffer.removeSubrange(...i);if let e=try? JSONSerialization.jsonObject(with:one) as? [String:Any] {if e["event"] as? String == "remote-companion-ready" {ready=true};if e["event"] as? String == "remote-error" {failed=true};bridge.receive(e)}}}}
  precondition(send(["action":"remote-companion-enable","folder":scope.folder,"identity":["device":dev,"inode":ino],"scope":["id":"project","revision":"r1"],"origin":activation.origin,"token":forged ? String(repeating:"x",count:32) : activation.token,"csrf":activation.csrf,"invitation":activation.invitation,"expires":expiry]))
  let readyUntil=Date().addingTimeInterval(8);while !ready && !failed && Date()<readyUntil {RunLoop.current.run(until:Date().addingTimeInterval(0.01))}
  if forged {precondition(failed && !ready);owner.stop();try? input.fileHandleForWriting.close();p.terminate();output.fileHandleForReading.readabilityHandler=nil;print("forged native companion activation rejected");return};precondition(ready)
  let host=UUID(),mac=P256.Signing.PrivateKey(),phone=P256.Signing.PrivateKey(),phoneID=UUID(),macPub=mac.publicKey.x963Representation,vault=MemoryStorage(),journal=MemoryStorage()
  let handler=try PairingHTTPHandler(hostID:host,macKey:mac,expectedHost:"atlas.example",expectedOrigin:"https://atlas-desktop.joelr2.chatgpt.site",privateOrigin:"https://atlas.example",macName:"Mac",storage:vault,journalStorage:journal,clock:clock,wallClock:{Int64(Date().timeIntervalSince1970)},ownerStarted:true,routeFactory:{h,host,origin,peer,scope,deadline,clock,wall in RegistryRoutes(hostID:h,expectedHost:host,expectedOrigin:origin,peer:peer,scope:scope,sessionDeadline:deadline,clock:clock,wallClock:wall,transport:bridge)},recoveryCheck:{bridge.recoveryClear()},ownerConfirm:{_ in fatalError("synthetic route invoked")})
  let listener = CommandLine.arguments.count > 3 && CommandLine.arguments[3] == "--loopback" ? try CompanionLoopbackListener(handler:handler,ownerActivated:true) : nil
  func deliver(_ raw:Data)throws->CompanionHTTPReply {
   guard let listener else {return handler.handle(raw)}
   let fd=socket(AF_INET,SOCK_STREAM,0);guard fd>=0 else {throw ProofError.denied};defer{close(fd)}
   var address=sockaddr_in();address.sin_len=UInt8(MemoryLayout<sockaddr_in>.size);address.sin_family=sa_family_t(AF_INET);address.sin_addr=in_addr(s_addr:in_addr_t(INADDR_LOOPBACK).bigEndian);address.sin_port=listener.port.bigEndian
   guard withUnsafePointer(to:&address,{$0.withMemoryRebound(to:sockaddr.self,capacity:1){connect(fd,$0,socklen_t(MemoryLayout<sockaddr_in>.size))}})==0 else {throw ProofError.denied}
   let sent=raw.withUnsafeBytes {bytes -> Bool in var offset=0;while offset<bytes.count {let n=Darwin.write(fd,bytes.baseAddress!.advanced(by:offset),bytes.count-offset);if n<=0{return false};offset+=n};return true};guard sent else {throw ProofError.denied}
   var reply=Data(),buf=[UInt8](repeating:0,count:4096);while true {let n=Darwin.read(fd,&buf,buf.count);if n==0 {break};guard n>0,reply.count+n<32768 else {throw ProofError.denied};reply.append(contentsOf:buf[..<n])}
   guard let split=reply.range(of:Data("\r\n\r\n".utf8)),let line=String(data:reply[..<split.lowerBound],encoding:.utf8)?.components(separatedBy:"\r\n").first,let code=Int(line.split(separator:" ")[1]) else {throw ProofError.denied}
   return CompanionHTTPReply(code:code,headers:[:],body:Data(reply[split.upperBound...]))
  }
  func post<T:Encodable>(_ path:String,_ value:T)throws->CompanionHTTPReply {let data=try JSONEncoder().encode(value),head="POST \(path) HTTP/1.1\r\nHost: atlas.example\r\nOrigin: https://atlas-desktop.joelr2.chatgpt.site\r\nContent-Type: application/json\r\nContent-Length: \(data.count)\r\n\r\n",raw=Data(head.utf8)+data
   if !Thread.isMainThread {return try deliver(raw)}
   var reply:CompanionHTTPReply?;let done=DispatchSemaphore(value:0);DispatchQueue.global().async {reply=try? deliver(raw);done.signal()}
   let until=Date().addingTimeInterval(7);while done.wait(timeout:.now()) == .timedOut && Date()<until {RunLoop.current.run(until:Date().addingTimeInterval(0.01))};guard let reply else {throw ProofError.denied};return reply
  }
  let client=try EnrollmentPhone(challenge:handler.challenge,expectedOrigin:"https://atlas.example",expectedMacFingerprint:try signingFingerprint(macPub),phoneName:"Synthetic Phone")
  let joined=try post("/v1/enrollment/join",client.response),attempt=try JSONDecoder().decode(AttemptReply.self,from:joined.body)
  try handler.ownerApprove(attemptID:attempt.attemptID,code:client.code,fingerprint:try signingFingerprint(macPub),confirmed:true)
  let approved=try post("/v1/enrollment/status",["attemptID":attempt.attemptID.uuidString]);precondition(approved.code==200)
  let binding=enrollmentBinding(handler.challenge,client.response),phonePub=phone.publicKey.x963Representation,proof=try phone.signature(for:identityProof(role:"phone",binding:binding,hostID:host,phoneID:phoneID,generation:1,macPublic:macPub,phonePublic:phonePub))
  let claim=IdentityClaim(deviceID:phoneID,generation:1,publicKey:phonePub,signature:proof.rawRepresentation)
  let finish=try post("/v1/enrollment/finish",sealPairing(claim,role:"phone",binding:binding,key:client.channel));precondition(finish.code==200)
  let ack=try phone.signature(for:identityProof(role:"ack",binding:binding,hostID:host,phoneID:phoneID,generation:1,macPublic:macPub,phonePublic:phonePub))
  let ackReply=try post("/v1/enrollment/ack",sealPairing(IdentityAck(signature:ack.rawRepresentation),role:"ack",binding:binding,key:client.channel));precondition(ackReply.code==200)
  let device:[String:Any]=["id":phoneID.uuidString.lowercased(),"name":"Synthetic Phone","generation":1,"fingerprint":try signingFingerprint(phonePub),"macFingerprint":try signingFingerprint(macPub),"macName":"Mac"]
  precondition(owner.bindCompanionDevice(device))
  var sentDevice=device;if mismatched {sentDevice["fingerprint"]=String(repeating:"f",count:64)}
  var bound=false;let bindDone=DispatchSemaphore(value:0);DispatchQueue.global().async {bound=bridge.bindDevice(sentDevice,id:phoneID);bindDone.signal()}
  let bindUntil=Date().addingTimeInterval(5);while bindDone.wait(timeout:.now()) == .timedOut && Date()<bindUntil {RunLoop.current.run(until:Date().addingTimeInterval(0.01))};precondition(bound)
  try handler.ownerStartSession(scope:("project","r1"),deadline:expiry,confirmed:true)
  if CommandLine.arguments.contains("--clean-stop") {
   let done=DispatchSemaphore(value:0);DispatchQueue.global().async {handler.ownerEndSession();done.signal()}
   let until=Date().addingTimeInterval(7);while done.wait(timeout:.now()) == .timedOut && Date()<until {RunLoop.current.run(until:Date().addingTimeInterval(0.01))}
   let marker=try RevocationJournal(storage:journal,hostID:host).read(),peer=try MacPairingVault(storage:vault,clock:clock).authority(phoneID)
   precondition(marker.state=="clear" && peer?.revoked==false && approvals==0)
   listener?.stop();bridge.close();owner.stop();try? input.fileHandleForWriting.close();if p.isRunning {p.terminate()};output.fileHandleForReading.readabilityHandler=nil;print("clean session stop preserves pairing");return
  }
  let id=UUID(),payload=try JSONEncoder().encode(SyntheticTask(id:id,task:"synthetic task"))
  func operation(_ action:String,_ path:String,_ payload:Data)throws->CompanionHTTPReply {let intent=RequestIntent(hostID:host,deviceID:phoneID,generation:1,scopeID:"project",scopeRevision:"r1",action:action,method:"POST",path:path,expiresAt:Int64(Date().timeIntervalSince1970)+20,payloadDigest:Data(SHA256.hash(data:payload)));let reply=try post("/v1/session/challenge",["intent":intent]);let c=try JSONDecoder().decode(RequestChallenge.self,from:reply.body);return try post(path,SyntheticOperation(challenge:c,signature:phone.signature(for:requestProofMessage(c)).rawRepresentation,payload:payload))}
  let secondID=UUID(),secondPayload=try JSONEncoder().encode(SyntheticTask(id:secondID,task:"second task")),secondIntent=RequestIntent(hostID:host,deviceID:phoneID,generation:1,scopeID:"project",scopeRevision:"r1",action:"submit",method:"POST",path:"/v1/tasks",expiresAt:Int64(Date().timeIntervalSince1970)+20,payloadDigest:Data(SHA256.hash(data:secondPayload)))
  let secondChallengeReply=try post("/v1/session/challenge",["intent":secondIntent]),secondChallenge=try JSONDecoder().decode(RequestChallenge.self,from:secondChallengeReply.body)
  let second=SyntheticOperation(challenge:secondChallenge,signature:try phone.signature(for:requestProofMessage(secondChallenge)).rawRepresentation,payload:secondPayload)
  var result:CompanionHTTPReply?,failure:Error?;let done=DispatchSemaphore(value:0)
  DispatchQueue.global().async {do{result=try operation("submit","/v1/tasks",payload)}catch{failure=error};done.signal()}
  let until=Date().addingTimeInterval(10);while done.wait(timeout:.now()) == .timedOut && Date()<until {RunLoop.current.run(until:Date().addingTimeInterval(0.01))}
  if mismatched {
   precondition(approvals==0)
   if let result,result.code==200,let body=try? JSONSerialization.jsonObject(with:result.body) as? [String:Any],let encoded=body["payload"] as? String,let data=Data(base64Encoded:encoded),let row=try? JSONDecoder().decode(SyntheticResult.self,from:data) {precondition(row.status != "submitted")}
   listener?.stop();bridge.close();owner.stop();try? input.fileHandleForWriting.close();if p.isRunning {p.terminate()};output.fileHandleForReading.readabilityHandler=nil;print("mismatched phone approval rejected");return
  }
  precondition(failure==nil && result?.code==200 && approvals==1)
  let deniedSecond=try post("/v1/tasks",second);precondition(deniedSecond.code==403)
  let body=try JSONSerialization.jsonObject(with:result!.body) as! [String:Any];let data=Data(base64Encoded:body["payload"] as! String)!,row=try JSONDecoder().decode(SyntheticResult.self,from:data);precondition(row.status=="submitted")
  precondition(FileManager.default.fileExists(atPath:root+"/profile/remote/remote-pending.json"))
  var cleared=true;let checkedBarrier=DispatchSemaphore(value:0)
  DispatchQueue.global().async {cleared=bridge.recoveryClear();checkedBarrier.signal()}
  let checkUntil=Date().addingTimeInterval(6);while checkedBarrier.wait(timeout:.now()) == .timedOut && Date()<checkUntil {RunLoop.current.run(until:Date().addingTimeInterval(0.01))}
  precondition(!cleared)
  let stopPayload=try JSONEncoder().encode(SyntheticTask(id:id,task:nil))
  func checked(_ action:String,_ path:String)throws->String {
   var reply:CompanionHTTPReply?,failure:Error?;let done=DispatchSemaphore(value:0)
   DispatchQueue.global().async {do{reply=try operation(action,path,stopPayload)}catch{failure=error};done.signal()}
   let until=Date().addingTimeInterval(7);while done.wait(timeout:.now()) == .timedOut && Date()<until {RunLoop.current.run(until:Date().addingTimeInterval(0.01))}
   guard failure==nil,let reply,reply.code==200,let body=try JSONSerialization.jsonObject(with:reply.body) as? [String:Any],let encoded=body["payload"] as? String,let data=Data(base64Encoded:encoded) else {throw ProofError.denied}
   return try JSONDecoder().decode(SyntheticResult.self,from:data).status
  }
  let status=try checked("status","/v1/tasks/status");precondition(status=="running")
  let stopped=try checked("stop","/v1/tasks/stop");precondition(stopped=="cancelling")
  let end=DispatchSemaphore(value:0);DispatchQueue.global().async {handler.ownerEndSession();end.signal()}
  let endUntil=Date().addingTimeInterval(7);while end.wait(timeout:.now()) == .timedOut && Date()<endUntil {RunLoop.current.run(until:Date().addingTimeInterval(0.01))}
  let pendingMarker=try RevocationJournal(storage:journal,hostID:host).read();precondition(pendingMarker.state=="stopped")
  let restarted=try PairingHTTPHandler(hostID:host,macKey:mac,expectedHost:"atlas.example",expectedOrigin:"https://atlas-desktop.joelr2.chatgpt.site",privateOrigin:"https://atlas.example",macName:"Mac",storage:vault,journalStorage:journal,clock:clock,wallClock:{Int64(Date().timeIntervalSince1970)},ownerStarted:true,recoveryCheck:{true},ownerConfirm:{_ in false})
  try restarted.ownerReviewRestart(confirmed:true,taskOutcomeReviewed:true);try restarted.ownerSelectPhone(phoneID,confirmed:true)
  let resumedPeer=try MacPairingVault(storage:vault,clock:clock).authority(phoneID);precondition(resumedPeer?.revoked==false)
  listener?.stop();bridge.close();owner.stop();try? input.fileHandleForWriting.close();if p.isRunning {p.terminate()};output.fileHandleForReading.readabilityHandler=nil
  print("signed handler -> native supervisor -> Agents fake provider fixture ok")
 }
}
