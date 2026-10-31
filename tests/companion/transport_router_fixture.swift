import Foundation
@main struct Fixture {
 static func main() {
  let router=CompanionEventRouter(),done=DispatchSemaphore(value:0);var result:String?
  let bridge=NativeCompanionTransport(timeout:2,send:{message in
   guard let call=message["call"] as? String,let id=message["id"] as? String else{return false}
   DispatchQueue.global().async {router.deliver(["event":"remote-companion-result","call":call,"result":["id":id,"status":"clear"]])};return true
  },stop:{})
  router.set(bridge)
  DispatchQueue.global().async {result=try? bridge.call(action:"check",id:UUID(),task:nil,deadline:nil,wallExpiry:nil);done.signal()}
  precondition(done.wait(timeout:.now()+3) == .success && result=="clear")
  router.set(nil);bridge.close();print("private replies complete while UI thread is blocked")
 }
}
