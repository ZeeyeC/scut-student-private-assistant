import Foundation

// This transport is deliberately limited to the fixed local health endpoint.
// It never carries a selected profile, credentials or a shutdown request.
struct HealthTransactionDiagnostic: Codable {
    let fetchStarted: Bool
    let dnsStarted: Bool
    let connectStarted: Bool
    let connected: Bool
    let requestStarted: Bool
    let responseStarted: Bool
    let connectionReused: Bool
    let proxyConnection: Bool
    let resourceFetchType: Int
}

struct HealthDiagnostic: Codable {
    let probeID: String
    let port: Int?
    let elapsedMilliseconds: Int
    let statusCode: Int?
    let errorDomain: String?
    let errorCode: Int?
    let transactions: [HealthTransactionDiagnostic]

    var phase: String {
        guard let last = transactions.last else { return "metrics-unavailable" }
        if last.responseStarted { return "response-started" }
        if last.requestStarted { return "request-started" }
        if last.connected { return "connected" }
        if last.connectStarted { return "connect-started" }
        if last.dnsStarted { return "dns-started" }
        return "before-connect"
    }
}

struct HealthProbe {
    let data: Data
    let response: HTTPURLResponse?
    let error: Error?
    let diagnostic: HealthDiagnostic

    func get() throws -> (Data, HTTPURLResponse?) {
        if let error { throw error }
        return (data, response)
    }
}

private final class HealthTaskObserver: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    private let lock = NSLock()
    private var transactions: [HealthTransactionDiagnostic] = []

    func urlSession(_ session: URLSession, task: URLSessionTask, didFinishCollecting metrics: URLSessionTaskMetrics) {
        let values = metrics.transactionMetrics.map {
            HealthTransactionDiagnostic(
                fetchStarted: $0.fetchStartDate != nil, dnsStarted: $0.domainLookupStartDate != nil,
                connectStarted: $0.connectStartDate != nil, connected: $0.connectEndDate != nil,
                requestStarted: $0.requestStartDate != nil, responseStarted: $0.responseStartDate != nil,
                connectionReused: $0.isReusedConnection, proxyConnection: $0.isProxyConnection,
                resourceFetchType: Int($0.resourceFetchType.rawValue)
            )
        }
        lock.lock()
        transactions = values
        lock.unlock()
    }

    func snapshot() -> [HealthTransactionDiagnostic] {
        lock.lock()
        defer { lock.unlock() }
        return transactions
    }

    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse,
                    newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        // Even a loopback redirect could escape the health endpoint or origin.
        completionHandler(nil)
    }
}

struct LocalHealthTransport {
    let origin: URL

    static func healthURL(for origin: URL) throws -> URL {
        guard let parts = URLComponents(url: origin, resolvingAgainstBaseURL: false),
              parts.scheme == "http", parts.host == "127.0.0.1",
              let port = parts.port, (1024...65535).contains(port),
              parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
              parts.path.isEmpty || parts.path == "/" else {
            throw ServiceError.message("健康检查仅允许本机固定端口和路径。")
        }
        return origin.appendingPathComponent("api/healthz")
    }

    @MainActor func fetch(timeout: TimeInterval) async -> HealthProbe {
        let started = ProcessInfo.processInfo.systemUptime
        let identifier = UUID().uuidString
        let observer = HealthTaskObserver()
        var payload = Data()
        var response: HTTPURLResponse?
        var failure: Error?
        do {
            let url = try Self.healthURL(for: origin)
            let configuration = URLSessionConfiguration.ephemeral
            configuration.connectionProxyDictionary = [:]
            configuration.urlCache = nil
            configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
            configuration.httpCookieStorage = nil
            configuration.httpShouldSetCookies = false
            configuration.urlCredentialStorage = nil
            configuration.waitsForConnectivity = false
            configuration.timeoutIntervalForRequest = timeout
            configuration.timeoutIntervalForResource = timeout
            // A fresh session for each probe avoids a stale pooled connection.
            // No retry: identity, status and transport errors remain observable.
            let session = URLSession(configuration: configuration)
            defer { session.invalidateAndCancel() }
            var request = URLRequest(url: url, cachePolicy: .reloadIgnoringLocalCacheData)
            request.timeoutInterval = timeout
            request.setValue("close", forHTTPHeaderField: "Connection")
            request.setValue(identifier, forHTTPHeaderField: "X-Campus-Health-Probe")
            let (data, reply) = try await session.data(for: request, delegate: observer)
            payload = data
            response = reply as? HTTPURLResponse
        } catch { failure = error }
        let error = failure.map { $0 as NSError }
        let diagnostic = HealthDiagnostic(
            probeID: identifier, port: origin.port,
            elapsedMilliseconds: Int((ProcessInfo.processInfo.systemUptime - started) * 1000),
            statusCode: response?.statusCode, errorDomain: error?.domain, errorCode: error?.code,
            transactions: observer.snapshot()
        )
        return HealthProbe(data: payload, response: response, error: failure, diagnostic: diagnostic)
    }
}
