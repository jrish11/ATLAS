import Foundation

protocol UpdateDownloading {
    func fetch(_ url: URL, maximum: Int, expectedSize: Int?) async throws -> Data
}

enum UpdateDownloadOrigins {
    static func permits(_ url: URL, redirected: Bool) -> Bool {
        guard url.scheme == "https", url.user == nil, url.password == nil, url.fragment == nil,
              url.port == nil || url.port == 443, let host=url.host?.lowercased() else {return false}
        if host == "github.com" {
            return url.path.hasPrefix("/jrish11/ATLAS/releases/download/") && url.query == nil
        }
        return redirected && ["release-assets.githubusercontent.com", "objects.githubusercontent.com"].contains(host)
            && url.path.hasPrefix("/github-production-release-asset/")
    }
}

// Ephemeral, no shared credentials/cookies/cache; only known release transport
// may receive a redirect. A redirect never receives an Authorization header.
final class BoundedUpdateDownloader: UpdateDownloading {
    private var fixtureProtocols:[AnyClass]? = nil
    #if UPDATER_TESTING
    init(protocolClasses:[AnyClass]) {fixtureProtocols=protocolClasses}
    #endif
    init() {}
    func fetch(_ url: URL, maximum: Int, expectedSize: Int? = nil) async throws -> Data {
        guard UpdateDownloadOrigins.permits(url, redirected:false), maximum > 0,
              expectedSize == nil || (expectedSize! > 0 && expectedSize! <= maximum) else {
            throw SignedUpdateError.rejected("Unapproved update request.")
        }
        let transfer=UpdateTransfer(url:url, maximum:maximum, expected:expectedSize,protocolClasses:fixtureProtocols)
        return try await withTaskCancellationHandler(operation: {
            try Task.checkCancellation()
            return try await withCheckedThrowingContinuation { transfer.start($0) }
        }, onCancel: {transfer.cancel()})
    }
}

private final class UpdateTransfer: NSObject, URLSessionDataDelegate, @unchecked Sendable {
    private let lock=NSLock(), url:URL, maximum:Int, expected:Int?
    private let protocolClasses:[AnyClass]?
    private var session:URLSession?, task:URLSessionDataTask?, continuation:CheckedContinuation<Data,Error>?
    private var body=Data(), finished=false, cancelled=false, redirects=0
    init(url:URL, maximum:Int, expected:Int?,protocolClasses:[AnyClass]?) {self.url=url;self.maximum=maximum;self.expected=expected;self.protocolClasses=protocolClasses}
    func start(_ continuation:CheckedContinuation<Data,Error>) {
        lock.lock()
        if cancelled {lock.unlock();continuation.resume(throwing:CancellationError());return}
        self.continuation=continuation
        let config=URLSessionConfiguration.ephemeral
        config.protocolClasses=protocolClasses
        config.httpCookieStorage=nil;config.httpShouldSetCookies=false;config.urlCredentialStorage=nil
        config.urlCache=nil;config.requestCachePolicy = .reloadIgnoringLocalCacheData
        config.timeoutIntervalForRequest=30;config.timeoutIntervalForResource=120
        let queue=OperationQueue();queue.maxConcurrentOperationCount=1
        let session=URLSession(configuration:config,delegate:self,delegateQueue:queue)
        var request=URLRequest(url:url);request.setValue("ATLAS-Signed-Updater",forHTTPHeaderField:"User-Agent")
        request.setValue("application/octet-stream",forHTTPHeaderField:"Accept")
        self.session=session;let task=session.dataTask(with:request);self.task=task
        lock.unlock();task.resume()
    }
    func cancel() {
        lock.lock();cancelled=true;let task=self.task;lock.unlock()
        task?.cancel();finish(.failure(CancellationError()))
    }
    private func finish(_ result:Result<Data,Error>) {
        lock.lock();guard !finished else {lock.unlock();return};finished=true
        let callback=continuation, session=self.session;continuation=nil;self.session=nil;task=nil;lock.unlock()
        session?.invalidateAndCancel();callback?.resume(with:result)
    }
    func urlSession(_ session:URLSession, task:URLSessionTask, willPerformHTTPRedirection response:HTTPURLResponse,
                    newRequest request:URLRequest, completionHandler:@escaping(URLRequest?)->Void) {
        lock.lock();redirects += 1;let allowed=redirects <= 4 && !cancelled;lock.unlock()
        guard allowed, let url=request.url, UpdateDownloadOrigins.permits(url,redirected:true) else {
            completionHandler(nil);finish(.failure(SignedUpdateError.rejected("Unapproved update redirect.")));return
        }
        var clean=URLRequest(url:url);clean.httpMethod="GET";clean.setValue("application/octet-stream",forHTTPHeaderField:"Accept")
        clean.setValue("ATLAS-Signed-Updater",forHTTPHeaderField:"User-Agent");completionHandler(clean)
    }
    func urlSession(_ session:URLSession, dataTask:URLSessionDataTask, didReceive response:URLResponse,
                    completionHandler:@escaping(URLSession.ResponseDisposition)->Void) {
        guard let http=response as? HTTPURLResponse, http.statusCode==200,
              let final=response.url, UpdateDownloadOrigins.permits(final,redirected:redirects>0),
              response.expectedContentLength <= Int64(maximum),
              expected == nil || response.expectedContentLength < 0 || response.expectedContentLength == Int64(expected!) else {
            completionHandler(.cancel);finish(.failure(SignedUpdateError.rejected("Update download response was rejected.")));return
        }
        completionHandler(.allow)
    }
    func urlSession(_ session:URLSession, dataTask:URLSessionDataTask, didReceive data:Data) {
        lock.lock()
        if !finished && !cancelled && body.count <= maximum-data.count {body.append(data);lock.unlock()}
        else {lock.unlock();finish(.failure(SignedUpdateError.rejected("Update download exceeded its bound.")))}
    }
    func urlSession(_ session:URLSession, task:URLSessionTask, didCompleteWithError error:Error?) {
        lock.lock();let bytes=body, cancelled=self.cancelled;lock.unlock()
        if cancelled {finish(.failure(CancellationError()))}
        else if let error {finish(.failure(error))}
        else if let expected, bytes.count != expected {finish(.failure(SignedUpdateError.rejected("Incomplete update download.")))}
        else if bytes.isEmpty {finish(.failure(SignedUpdateError.rejected("Empty update response.")))}
        else {finish(.success(bytes))}
    }
}
