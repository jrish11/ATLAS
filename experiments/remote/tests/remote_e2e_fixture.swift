import Cocoa
import Darwin
@main struct Fixture {
 static func main() throws {
  let repo=CommandLine.arguments[1], root=CommandLine.arguments[2], result=root+"/result.json", mode=CommandLine.arguments.count > 3 ? CommandLine.arguments[3] : "allow"
  try? FileManager.default.removeItem(atPath:root)
  for folder in [root,root+"/project",root+"/profile",root+"/barrier"] { try FileManager.default.createDirectory(atPath:folder,withIntermediateDirectories:true,attributes:[.posixPermissions:0o700]) }
  let attributes=try FileManager.default.attributesOfItem(atPath:root+"/project")
  let device=(attributes[.systemNumber] as! NSNumber).intValue, inode=(attributes[.systemFileNumber] as! NSNumber).intValue
  var scale=mach_timebase_info_data_t();mach_timebase_info(&scale)
  let clock: () -> Double = { Double(mach_continuous_time()) * Double(scale.numer) / Double(scale.denom) / 1_000_000_000 }
  let expiry=clock()+60
  let scope=RemoteNativeOwner.Scope(folder:root+"/project",id:"fixture",revision:"r1",device:device,inode:inode,expires:expiry)
  var count=0
  let activation=RemoteNativeOwner.Activation(origin:"https://atlas.test",token:String(repeating:"t",count:32),csrf:String(repeating:"c",count:32),invitation:String(repeating:"i",count:32))
  let owner=RemoteNativeOwner(scope:scope,clock:clock,activation:activation,decide:{target,reply in count += 1; if count == 1 { precondition(target["device"] as? String == "synthetic phone") } else { precondition(target["task"] as? String == "synthetic task") }; reply(true)})
  var fds:[Int32] = [-1,-1]; precondition(socketpair(AF_UNIX, SOCK_STREAM, 0, &fds) == 0)
  _ = fcntl(fds[0],F_SETFD,FD_CLOEXEC); _ = fcntl(fds[1],F_SETFD,FD_CLOEXEC)
  let child=FileHandle(fileDescriptor:fds[1],closeOnDealloc:true)
  let process=Process();process.executableURL=URL(fileURLWithPath:"/usr/bin/python3");process.arguments=[repo+"/tests/remote_end_to_end_worker.py",root,String(expiry),result,mode]
  process.standardInput=FileHandle.nullDevice;process.standardOutput=FileHandle.nullDevice;process.standardError=child
  try process.run();try child.close()
  let bootstrap=try JSONSerialization.data(withJSONObject:["kind":"native-authority","key":String(repeating:"a",count:64)])
  let n=bootstrap.count;var frame=Data([UInt8((n>>24)&255),UInt8((n>>16)&255),UInt8((n>>8)&255),UInt8(n&255)]);frame.append(bootstrap)
  try FileHandle(fileDescriptor:fds[0],closeOnDealloc:false).write(contentsOf:frame)
  try owner.attach(fd:fds[0])
  let deadline=Date().addingTimeInterval(15)
  while !FileManager.default.fileExists(atPath:result) && Date()<deadline {RunLoop.current.run(until:Date().addingTimeInterval(0.05))}
  let data=try Data(contentsOf:URL(fileURLWithPath:result)); let out=try JSONSerialization.jsonObject(with:data) as! [String:Any]
  if mode == "forged" { precondition(count==0 && (out["rejected"] as? Bool)==true && (out["rows"] as? Int)==0 && (out["providers"] as? Int)==0);owner.stop();print("native forged activation rejected");return }
  precondition(count==2 && (out["rows"] as? Int)==1 && (out["interrupted"] as? Bool)==true)
  precondition((out["submitted"] as? [String:String])?["status"]=="submitted")
  precondition((out["status"] as? [String:String])?["status"]=="running")
  precondition((out["stop"] as? [String:String])?["status"]=="cancelling")
  precondition(out["barrier"] is [String:Any]);owner.stop();print("native remote end-to-end fixture ok")
 }
}
