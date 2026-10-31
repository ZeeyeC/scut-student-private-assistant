import AppKit

@MainActor
func runBrowserLaunchPolicyTests() {
    let suite = "campus-import-tests-" + UUID().uuidString
    let defaults = UserDefaults(suiteName: suite)!
    defer { defaults.removePersistentDomain(forName: suite) }
    var resolved: [String] = [], opened: [URL] = []
    let application = URL(fileURLWithPath: "/Applications/SelectedBrowser.app")
    let policy = BrowserLaunchPolicy(defaults: defaults, resolve: { id in resolved.append(id); return application }, open: { url, app, completion in
        precondition(app == application); opened.append(url); completion(nil)
    })
    let origin = URL(string: "http://127.0.0.1:5189")!
    let id = UUID().uuidString.lowercased(), grant = UUID().uuidString.lowercased()
    let url = URL(string: origin.absoluteString + "/school-import/" + id + "#grant=" + grant + "." + String(repeating: "a", count: 64))!
    let context = SchoolImportContext(id: id, bridgeURL: url, expiresAt: Date().addingTimeInterval(60), status: "queued")
    func rejects(_ operation: () throws -> Void) -> Bool { do { try operation(); return false } catch { return true } }
    precondition(policy.selectedBrowser == .chrome)
    try! policy.launch(context, origin: origin)
    precondition(resolved == ["com.google.Chrome"] && opened == [url], "Use Chrome explicitly even if the system default is Safari")
    try! policy.select("edge")
    precondition(BrowserLaunchPolicy(defaults: defaults).selectedBrowser == .edge, "Remember browser across launches")
    try! policy.launch(context, origin: origin)
    precondition(resolved.last == "com.microsoft.edgemac")
    precondition(rejects { try policy.select("safari") })
    let missing = BrowserLaunchPolicy(defaults: defaults, resolve: { _ in nil }, open: { _, _, _ in preconditionFailure("Missing selected browser must not open anything") })
    precondition(rejects { try missing.launch(context, origin: origin) })
    for address in ["https://example.com/", "http://127.0.0.1:5190/school-import/" + id, origin.absoluteString + "/api/tasks", origin.absoluteString + "/school-import/" + UUID().uuidString] {
        precondition(rejects { try policy.launch(SchoolImportContext(id: id, bridgeURL: URL(string: address)!, expiresAt: context.expiresAt, status: "queued"), origin: origin) })
    }
    for state in ["cancelled", "expired", "failed", "completed", "preview_ready"] {
        precondition(rejects { try policy.launch(SchoolImportContext(id: id, bridgeURL: url, expiresAt: context.expiresAt, status: state), origin: origin) })
    }
    precondition(rejects { try policy.launch(SchoolImportContext(id: id, bridgeURL: url, expiresAt: .distantPast, status: "queued"), origin: origin) })
    precondition(opened.count == 2, "Invalid contexts must have no external side effects")
    try! policy.openExtensionManager()
    precondition(opened.last?.absoluteString == "edge://extensions/", "Management uses selected Edge")
    precondition(resolved.last == "com.microsoft.edgemac")
    precondition(rejects {try missing.openExtensionManager()})

}
