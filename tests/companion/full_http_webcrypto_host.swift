import Foundation
import CryptoKit
final class MemoryStorage:SecureDeviceStorage {let storageIdentifier=UUID().uuidString;var data:Data?;func read()throws->Data?{data};func write(_ d:Data)throws{data=d};func delete()throws{data=nil}}
struct Command:Decodable {let kind:String;let path:String?;let host:String?;let origin:String?;let method:String?;let body:Data?;let attemptID:UUID?;let code:String?;let fingerprint:String?;let phoneID:UUID?}
struct WireReply:Encodable {let code:Int;let headers:[String:String];let body:Data}
struct RecoveryInput:Decodable {let signature:Data}
func output<T:Encodable>(_ v:T)throws {print(String(decoding:try JSONEncoder().encode(v),as:UTF8.self));fflush(stdout)}
@main struct Test {
 static func main()throws {
  let args=CommandLine.arguments
  if args.count==4 && args[1]=="--recover" {
   let storage=SyntheticFileStorage(directory:args[2]),vault=MacPairingVault(storage:storage,clock:{1}),id=UUID(uuidString:args[3])!
   guard let descriptor=try vault.inspectRecovery(id) else {throw DeviceError.missing}
   let journal=RevocationJournal(storage:SyntheticFileStorage(directory:args[2],name:"synthetic-journal.json"),hostID:descriptor.hostID)
   let recovery=PairingRecovery(vault:vault,clock:{1},recoveryCheck:{(try? journal.read().state)=="clear"}),challenge=try recovery.begin(displayed:descriptor,ownerReviewed:true);try output(challenge)
   guard let line=readLine(),let data=line.data(using:.utf8) else {throw ProofError.invalid};let input=try JSONDecoder().decode(RecoveryInput.self,from:data)
   try output(recovery.finish(challenge,signature:input.signature));return
  }
  let storage:SecureDeviceStorage=args.count>1 ? SyntheticFileStorage(directory:args[1]) : MemoryStorage()
  let journalStorage:SecureDeviceStorage=args.count>1 ? SyntheticFileStorage(directory:args[1],name:"synthetic-journal.json") : MemoryStorage()
  let loseAck=args.contains("--lose-ack")
  let mac=P256.Signing.PrivateKey(),hostID=UUID(),clock={1.0},wall={Int64(1000)}
  let h=try PairingHTTPHandler(hostID:hostID,macKey:mac,expectedHost:"atlas.example",expectedOrigin:"https://atlas-desktop.joelr2.chatgpt.site",privateOrigin:"https://atlas.example",macName:"Synthetic Mac",storage:storage,journalStorage:journalStorage,clock:clock,wallClock:wall,ownerStarted:true,recoveryCheck:{true},ownerConfirm:{_ in true})
  try output(h.challenge)
  while let line=readLine(),let bytes=line.data(using:.utf8) {
   do {
    let c=try JSONDecoder().decode(Command.self,from:bytes)
    switch c.kind {
    case "owner-approve":guard let id=c.attemptID,let code=c.code,let fp=c.fingerprint else {throw ProofError.invalid};try h.ownerApprove(attemptID:id,code:code,fingerprint:fp,confirmed:true);try output(["status":"approved-locally"])
    case "owner-review":try h.ownerReviewRestart(confirmed:true,taskOutcomeReviewed:true);try output(["status":"reviewed-locally"])
    case "owner-recovery":guard let id=c.phoneID,let descriptor=try h.ownerRecoveryDescriptor(id) else {throw ProofError.invalid};try h.ownerPrepareRecovery(descriptor,confirmed:true);try output(["status":"recovery-approved-locally"])
    case "owner-session":try h.ownerStartSession(scope:("project","one"),deadline:100,confirmed:true);try output(["status":"session-approved-locally"])
    case "owner-revoke":try h.ownerRevoke(expectedGeneration:1,confirmed:true);try output(["status":"revoked-locally"])
    case "http":
     guard let path=c.path,let method=c.method,let host=c.host,let origin=c.origin,let body=c.body else {throw ProofError.invalid}
     let head="\(method) \(path) HTTP/1.1\r\nHost: \(host)\r\nOrigin: \(origin)\r\nContent-Type: application/json\r\nContent-Length: \(body.count)\r\n\r\n"
     let result=h.handle(Data(head.utf8)+body);if loseAck && path=="/v1/enrollment/ack" && result.code==200 {exit(0)};try output(WireReply(code:result.code,headers:result.headers,body:result.body))
    default:throw ProofError.invalid
    }
   } catch {try output(["error":"rejected"])}
  }
 }
}
