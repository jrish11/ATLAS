import Foundation

enum StrictHTTPError:Error { case invalid, forbidden, tooLarge }
struct StrictHTTPRequest { let method:String;let path:String;let body:Data }

/// Parses a single, complete HTTP/1.1 request from a loopback TLS proxy.
/// Disabled until wired to a separately approved listener and native owner UI.
struct StrictHTTP {
    let expectedHost:String,expectedOrigin:String
    static let paths:Set<String>=["/v1/enrollment/join","/v1/enrollment/status","/v1/enrollment/finish","/v1/enrollment/ack","/v1/enrollment/recovery/challenge","/v1/enrollment/recovery/finish","/v1/session/challenge","/v1/tasks","/v1/tasks/status","/v1/tasks/stop"]
    func parse(_ raw:Data)throws->StrictHTTPRequest {
        guard raw.count<=24576 else {throw StrictHTTPError.tooLarge}
        guard let boundary=raw.range(of:Data([13,10,13,10])),boundary.lowerBound<=8192 else {throw StrictHTTPError.invalid}
        let head=raw.subdata(in:0..<boundary.lowerBound),body=raw.subdata(in:boundary.upperBound..<raw.count)
        guard let text=String(data:head,encoding:.ascii),!text.contains("\0") else {throw StrictHTTPError.invalid}
        let lines=text.components(separatedBy:"\r\n");guard let first=lines.first else {throw StrictHTTPError.invalid}
        let parts=first.components(separatedBy:" ");guard parts.count==3,parts[2]=="HTTP/1.1",["POST","OPTIONS"].contains(parts[0]),Self.paths.contains(parts[1]) else {throw StrictHTTPError.invalid}
        var headers:[String:String]=[:]
        for line in lines.dropFirst() {
            guard !line.isEmpty,!line.hasPrefix(" "),!line.hasPrefix("\t"),let colon=line.firstIndex(of:":") else {throw StrictHTTPError.invalid}
            let key=String(line[..<colon]).lowercased(),value=String(line[line.index(after:colon)...]).trimmingCharacters(in:.whitespaces)
            guard key.range(of:#"^[a-z0-9!#$%&'*+.^_`|~-]+$"#,options:.regularExpression) != nil,headers[key]==nil,
                  !value.unicodeScalars.contains(where:{$0.value<32 || $0.value==127}) else {throw StrictHTTPError.invalid}
            headers[key]=value
        }
        guard headers["host"]==expectedHost,headers["origin"]==expectedOrigin,headers["transfer-encoding"]==nil,
              headers["cookie"]==nil,headers["authorization"]==nil,headers["proxy-authorization"]==nil else {throw StrictHTTPError.forbidden}
        guard headers["access-control-request-private-network"]==nil else {throw StrictHTTPError.forbidden}
        if parts[0]=="OPTIONS" {
            guard body.isEmpty,headers["content-length"].map({$0=="0"}) ?? true,headers["access-control-request-method"]=="POST" else {throw StrictHTTPError.invalid}
            let requested=(headers["access-control-request-headers"] ?? "").split(separator:",").map{$0.trimmingCharacters(in:.whitespaces).lowercased()}
            guard requested.isEmpty || requested==["content-type"] else {throw StrictHTTPError.forbidden}
        } else {
            guard headers["content-type"]=="application/json",let rawLength=headers["content-length"],!rawLength.isEmpty,rawLength.allSatisfy({$0.isASCII && $0.isNumber}),
                  let length=Int(rawLength),length>0,length<=16384,length==body.count else {throw StrictHTTPError.invalid}
            var scanner=JSONStructure(body);try scanner.check()
            guard let object=try? JSONSerialization.jsonObject(with:body),object is [String:Any] else {throw StrictHTTPError.invalid}
        }
        return StrictHTTPRequest(method:parts[0],path:parts[1],body:body)
    }
    /// Only call after parse succeeds. No wildcard, cookies, or PNA grant.
    func preflightHeaders()->[String:String] { ["Access-Control-Allow-Origin":expectedOrigin,"Access-Control-Allow-Methods":"POST, OPTIONS","Access-Control-Allow-Headers":"content-type","Vary":"Origin","Cache-Control":"no-store"] }
}
