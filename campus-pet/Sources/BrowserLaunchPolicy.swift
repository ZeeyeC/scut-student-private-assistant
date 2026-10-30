import AppKit

enum SchoolImportBrowser: String {
    case chrome, edge
    var bundleIdentifier: String { self == .chrome ? "com.google.Chrome" : "com.microsoft.edgemac" }
    var title: String { self == .chrome ? "Chrome" : "Edge" }
}

struct SchoolImportContext {
    let id: String
    let bridgeURL: URL
    let expiresAt: Date
    let status: String
}

@MainActor
final class BrowserLaunchPolicy {
    let defaults: UserDefaults
    let resolve: (String) -> URL?
    let open: (URL, URL, @escaping (Error?) -> Void) -> Void
    var selectedBrowser: SchoolImportBrowser { SchoolImportBrowser(rawValue: defaults.string(forKey: "schoolImportBrowser") ?? "") ?? .chrome }
    var installed: Bool { resolve(selectedBrowser.bundleIdentifier) != nil }

    init(defaults: UserDefaults = .standard,
         resolve: @escaping (String) -> URL? = { NSWorkspace.shared.urlForApplication(withBundleIdentifier: $0) },
         open: @escaping (URL, URL, @escaping (Error?) -> Void) -> Void = { url, app, completion in
             let configuration = NSWorkspace.OpenConfiguration()
             configuration.activates = true
             NSWorkspace.shared.open([url], withApplicationAt: app, configuration: configuration) { _, error in completion(error) }
         }) {
        self.defaults = defaults; self.resolve = resolve; self.open = open
    }

    func select(_ raw: String) throws {
        guard let browser = SchoolImportBrowser(rawValue: raw) else { throw ServiceError.message("请选择Chrome或Edge。") }
        defaults.set(browser.rawValue, forKey: "schoolImportBrowser")
    }

    func launch(_ context: SchoolImportContext, origin: URL, now: Date = Date(), completion: @escaping (Error?) -> Void = {_ in}) throws {
        let url = context.bridgeURL
        guard UUID(uuidString: context.id) != nil,
              ["queued", "waiting_login", "waiting_timetable", "extracting"].contains(context.status),
              context.expiresAt > now, context.expiresAt.timeIntervalSince(now) <= 15 * 60,
              origin.scheme == "http", origin.host == "127.0.0.1", (origin.port ?? 0) >= 1024,
              url.scheme == origin.scheme, url.host == origin.host, url.port == origin.port,
              url.user == nil, url.password == nil, url.query == nil,
              url.path == "/school-import/" + context.id,
              let fragment = url.fragment,
              fragment.range(of: "^grant=[a-f0-9-]{36}\\.[a-f0-9]{64}$", options: .regularExpression) != nil
        else { throw ServiceError.message("学校导入已过期、取消或地址无效，请回到App重新发起。") }
        guard let application = resolve(selectedBrowser.bundleIdentifier) else {
            throw ServiceError.message("未安装所选的\(selectedBrowser.title)，请安装它或在课程与学期中切换浏览器。")
        }
        open(url, application, completion)
    }
}
