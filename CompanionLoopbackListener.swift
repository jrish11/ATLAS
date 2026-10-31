import Foundation
import Darwin

// Explicitly started only by the native owner. This never configures a TLS
// proxy or network route. Each bounded connection contains one HTTP request.
final class CompanionLoopbackListener {
    private let lock=NSLock(),handler:PairingHTTPHandler
    private var listener:Int32 = -1,clients=Set<Int32>(),stopped=false
    let port:UInt16
    init(handler:PairingHTTPHandler,ownerActivated:Bool)throws {
        guard ownerActivated else {throw ProofError.denied};self.handler=handler
        let fd=socket(AF_INET,SOCK_STREAM,0);guard fd>=0 else {throw ProofError.denied}
        _ = fcntl(fd,F_SETFD,FD_CLOEXEC);_ = fcntl(fd,F_SETNOSIGPIPE,1)
        var address=sockaddr_in();address.sin_len=UInt8(MemoryLayout<sockaddr_in>.size);address.sin_family=sa_family_t(AF_INET);address.sin_addr=in_addr(s_addr:in_addr_t(INADDR_LOOPBACK).bigEndian);address.sin_port=0
        let bound=withUnsafePointer(to:&address) {$0.withMemoryRebound(to:sockaddr.self,capacity:1){Darwin.bind(fd,$0,socklen_t(MemoryLayout<sockaddr_in>.size))}}
        guard bound==0,Darwin.listen(fd,16)==0 else {close(fd);throw ProofError.denied}
        var actual=sockaddr_in(),length=socklen_t(MemoryLayout<sockaddr_in>.size)
        guard withUnsafeMutablePointer(to:&actual,{$0.withMemoryRebound(to:sockaddr.self,capacity:1){getsockname(fd,$0,&length)}})==0 else {close(fd);throw ProofError.denied}
        port=UInt16(bigEndian:actual.sin_port);listener=fd
        DispatchQueue.global(qos:.userInitiated).async {[weak self] in self?.acceptLoop(fd)}
    }
    private func acceptLoop(_ fd:Int32) {
        while true {
            let client=Darwin.accept(fd,nil,nil);if client<0 {return}
            _ = fcntl(client,F_SETFD,FD_CLOEXEC);_ = fcntl(client,F_SETNOSIGPIPE,1)
            var timeout=timeval(tv_sec:10,tv_usec:0);_ = setsockopt(client,SOL_SOCKET,SO_RCVTIMEO,&timeout,socklen_t(MemoryLayout<timeval>.size));_ = setsockopt(client,SOL_SOCKET,SO_SNDTIMEO,&timeout,socklen_t(MemoryLayout<timeval>.size))
            lock.lock();if stopped {lock.unlock();close(client);return};if clients.count>=16 {lock.unlock();close(client);continue};clients.insert(client);lock.unlock()
            DispatchQueue.global(qos:.userInitiated).async {[weak self] in self?.serve(client)}
        }
    }
    private func serve(_ client:Int32) {
        defer {lock.lock();clients.remove(client);lock.unlock();close(client)}
        var data=Data(),target:Int?,scratch=[UInt8](repeating:0,count:4096)
        while data.count<=16384 {
            let n=Darwin.read(client,&scratch,scratch.count);guard n>0 else{return};data.append(contentsOf:scratch[..<n])
            if target==nil,let boundary=data.range(of:Data("\r\n\r\n".utf8)) {
                guard boundary.upperBound<=8192,let head=String(data:data[..<boundary.lowerBound],encoding:.utf8) else{return}
                let lines=head.components(separatedBy:"\r\n").dropFirst(),lengths=lines.compactMap { line -> String? in let parts=line.split(separator:":",maxSplits:1,omittingEmptySubsequences:false);guard parts.count==2,parts[0].lowercased()=="content-length" else{return nil};return parts[1].trimmingCharacters(in:.whitespaces)}
                guard lengths.count<=1,let count=lengths.first.map({Int($0)}) ?? 0,count>=0,count<=8192 else {return};target=boundary.upperBound+count
            }
            if let target {guard data.count<=target else{return};if data.count==target {break}}
        }
        guard let target,data.count==target else{return}
        let reply=handler.handle(data),reason=reply.code==200 ? "OK" : reply.code==204 ? "No Content" : "Rejected"
        var headers=reply.headers;headers["Content-Length"]=String(reply.body.count);headers["Connection"]="close"
        guard headers.allSatisfy({!$0.key.contains("\r") && !$0.key.contains("\n") && !$0.value.contains("\r") && !$0.value.contains("\n")}) else{return}
        var out=Data("HTTP/1.1 \(reply.code) \(reason)\r\n".utf8);for (key,value) in headers {out.append(Data("\(key): \(value)\r\n".utf8))};out.append(Data("\r\n".utf8));out.append(reply.body)
        out.withUnsafeBytes {bytes in var offset=0;while offset<bytes.count {let n=Darwin.write(client,bytes.baseAddress!.advanced(by:offset),bytes.count-offset);if n<=0{return};offset+=n}}
    }
    func stop() {
        lock.lock();guard !stopped else {lock.unlock();return};stopped=true;let fd=listener;listener = -1;let active=Array(clients);lock.unlock()
        if fd>=0 {_ = shutdown(fd,SHUT_RDWR);close(fd)};for client in active {_ = shutdown(client,SHUT_RDWR)}
    }
    deinit {stop()}
}
