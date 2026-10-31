import Foundation
import Darwin
// Test-only durable store for synthetic keys. Never points at a user's profile.
final class SyntheticFileStorage:SecureDeviceStorage {
 let directory:String,name:String;var path:String {directory+"/"+name}
 var storageIdentifier:String { "synthetic-file:"+path }
 init(directory:String,name:String="synthetic-pairing.json"){self.directory=directory;self.name=name}
 func read()throws->Data? {if !FileManager.default.fileExists(atPath:path){return nil};return try Data(contentsOf:URL(fileURLWithPath:path))}
 func write(_ data:Data)throws {
  let temporary=directory+"/.synthetic-"+UUID().uuidString
  let fd=open(temporary,O_WRONLY|O_CREAT|O_EXCL,0o600);guard fd>=0 else {throw DeviceError.invalid}
  var okay=false;defer {close(fd);if !okay{unlink(temporary)}}
  let wrote=data.withUnsafeBytes { raw->Bool in var offset=0;while offset<raw.count {let n=Darwin.write(fd,raw.baseAddress!.advanced(by:offset),raw.count-offset);if n<=0{return false};offset+=n};return true }
  guard wrote,fsync(fd)==0,rename(temporary,path)==0 else {throw DeviceError.invalid};okay=true
  let dirfd=open(directory,O_RDONLY);guard dirfd>=0 else {throw DeviceError.invalid};defer{close(dirfd)}
  guard fsync(dirfd)==0 else {throw DeviceError.invalid}
 }
 func delete()throws {if unlink(path) != 0 && errno != ENOENT {throw DeviceError.invalid}}
}
