import AppKit

@MainActor final class HealthTestDriver: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        Task {
            let origin = URL(string: "http://127.0.0.1:\(CommandLine.arguments[1])")!
            let scenario = CommandLine.arguments[2]
            var diagnostics: [HealthDiagnostic] = []
            do {
                if scenario == "origins" {
                    for value in ["https://127.0.0.1:5189", "http://localhost:5189", "http://127.0.0.1.example.com:5189", "http://192.0.2.1:5189", "http://127.0.0.1:80", "http://user:pass@127.0.0.1:5189", "http://127.0.0.1:5189/other", "http://127.0.0.1:5189?q=1", "http://127.0.0.1:5189/#fragment"] {
                        let probe = await LocalHealthTransport(origin: URL(string: value)!).fetch(timeout: 3)
                        precondition(probe.error != nil && probe.diagnostic.transactions.isEmpty, "Invalid origins must be refused before networking")
                    }
                }
                let count = scenario == "origins" ? 0 : (["stale", "cache"].contains(scenario) ? 2 : 1)
                for index in 0..<count {
                    let probe = await LocalHealthTransport(origin: origin).fetch(timeout: 3)
                    diagnostics.append(probe.diagnostic)
                    var rejected: Error?
                    do {
                        let (data, response) = try probe.get()
                        guard let body = try JSONSerialization.jsonObject(with: data) as? [String:Any] else { throw ServiceError.message("Non-object health response") }
                        try ServiceController.validateHealth(status: response?.statusCode ?? 0, body: body)
                    } catch { rejected = error }
                    let expectedRejection = scenario == "reject" || scenario == "timeout" || (scenario == "cache" && index == 1)
                    guard (rejected != nil) == expectedRejection else { throw rejected ?? ServiceError.message("Expected the server fixture to be rejected") }
                    if expectedRejection && scenario != "timeout", let transportError = probe.error { throw transportError }
                    if scenario == "timeout" {
                        precondition((rejected as? URLError)?.code == .timedOut, "Preserve the original timeout error")
                        precondition((2800...4500).contains(probe.diagnostic.elapsedMilliseconds), "Keep the three-second timeout without retry")
                    }
                }
                let data = try JSONEncoder().encode(diagnostics)
                print(String(data: data, encoding: .utf8)!)
                print("PASS \(scenario)")
                NSApp.terminate(nil)
            } catch {
                let failure = error as NSError
                print("FAIL independent health requests: \(failure.domain):\(failure.code)")
                if let data = try? JSONEncoder().encode(diagnostics), let s = String(data: data, encoding: .utf8) { print(s) }
                exit(1)
            }
        }
    }
}

@main struct HealthTransportTests {
    static func main() {
        MainActor.assumeIsolated {
            let app = NSApplication.shared
            app.setActivationPolicy(.accessory)
            let driver = HealthTestDriver()
            app.delegate = driver
            app.run()
        }
    }
}
