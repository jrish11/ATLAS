import Foundation
@main struct Test {
 static func main()throws {
  let parser=StrictHTTP(expectedHost:"mac.example",expectedOrigin:"https://atlas-desktop.joelr2.chatgpt.site")
  func request(_ body:String,extra:String="",host:String="mac.example",origin:String="https://atlas-desktop.joelr2.chatgpt.site",path:String="/v1/tasks")->Data {
   Data("POST \(path) HTTP/1.1\r\nHost: \(host)\r\nOrigin: \(origin)\r\nContent-Type: application/json\r\nContent-Length: \(body.utf8.count)\r\n\(extra)\r\n\(body)".utf8)
  }
  let ok=try parser.parse(request("{\"id\":1}"));precondition(ok.path=="/v1/tasks")
  for bad in [request("{}",host:"evil.example"),request("{}",origin:"https://evil.example"),request("{}",extra:"Host: mac.example\r\n"),request("{}",extra:"Transfer-Encoding: chunked\r\n"),request("{}",extra:"Cookie: session=x\r\n"),request("{}",extra:"Authorization: Bearer x\r\n"),request("{}",path:"/v1/tasks?x=1"),request("{\"a\":1,\"a\":2}"),request("{\"a\":1,\"\\u0061\":2}"),request("{\"a\":{\"b\":1,\"b\":2}}"),request("{}",extra:"Access-Control-Request-Private-Network: true\r\n")] {
   do {_=try parser.parse(bad);fatalError("invalid request accepted")} catch is StrictHTTPError {}
  }
  let options=Data("OPTIONS /v1/tasks HTTP/1.1\r\nHost: mac.example\r\nOrigin: https://atlas-desktop.joelr2.chatgpt.site\r\nAccess-Control-Request-Method: POST\r\nAccess-Control-Request-Headers: content-type\r\n\r\n".utf8)
  let parsed=try parser.parse(options);precondition(parsed.method=="OPTIONS")
  let headers=parser.preflightHeaders();precondition(headers["Access-Control-Allow-Origin"]=="https://atlas-desktop.joelr2.chatgpt.site" && headers["Access-Control-Allow-Credentials"]==nil)
  print("strict HTTP and CORS fixture ok")
 }
}
