import AppKit

// Alternative ports are exclusively for the isolated native integration verifier.
let assistantOrigin: URL = {
    let args = CommandLine.arguments
    if args.contains("--external-service"), args.contains("--smoke-test"),
       let index = args.firstIndex(of: "--port"), index + 1 < args.count,
       let port = Int(args[index + 1]), (1024...65535).contains(port), port != 5173 {
        return URL(string: "http://127.0.0.1:\(port)")!
    }
    return URL(string: "http://127.0.0.1:5173")!
}()

struct LaunchOptions {
    var dataDirectory: URL
    var projectMode: Bool
    var externalService: Bool
    var smokeDirectory: URL?

    static func parse() -> LaunchOptions {
        let args = CommandLine.arguments
        func argument(_ name: String) -> String? {
            guard let index = args.firstIndex(of: name), index + 1 < args.count else { return nil }
            return args[index + 1]
        }
        let marker = Bundle.main.resourceURL?.appendingPathComponent("source-project.txt")
        let source = marker.flatMap { try? String(contentsOf: $0, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines) }
        let explicit = argument("--data-dir")
        let sourceExists = source.map { FileManager.default.fileExists(atPath: $0 + "/backend/app/main.py") } ?? false
        let base = explicit ?? (sourceExists ? source! : NSHomeDirectory() + "/Library/Application Support/CampusCompanion")
        return LaunchOptions(
            dataDirectory: URL(fileURLWithPath: base).standardizedFileURL,
            projectMode: explicit == nil && sourceExists,
            externalService: args.contains("--external-service"),
            smokeDirectory: argument("--smoke-test").map { URL(fileURLWithPath: $0) }
        )
    }
}

enum ServiceError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case .message(let value) = self { return value }; return nil }
}

@MainActor
final class ServiceController {
    let options: LaunchOptions
    private var launcher: Process?
    private let healthTransport = LocalHealthTransport(origin: assistantOrigin)
    private(set) var healthDiagnostics: [HealthDiagnostic] = []
    init(options: LaunchOptions) { self.options = options }

    private func probeHealth(timeout: TimeInterval) async -> HealthProbe {
        let result = await healthTransport.fetch(timeout: timeout)
        healthDiagnostics.append(result.diagnostic)
        if healthDiagnostics.count > 64 { healthDiagnostics.removeFirst(healthDiagnostics.count - 64) }
        return result
    }

    // Runs in the trusted WKWebView so the existing selected profile, cookies,
    // Origin and CSRF protections apply exactly as they do in the web settings.
    static let shutdownJavaScript = """
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 8000);
        try {
          const csrf = await fetch('/api/csrf', {credentials:'same-origin', signal:controller.signal});
          if (!csrf.ok) return {stopping:false, reason:'无法获取会话，请先重新连接助手。'};
          const token = (await csrf.json()).csrf_token;
          const response = await fetch('/api/local/shutdown', {
            method:'POST', credentials:'same-origin', signal:controller.signal,
            headers:{'Content-Type':'application/json', 'X-CSRF-Token':token}, body:'{}'
          });
          const result = await response.json();
          return {stopping:response.ok && result.stopping === true,
            reason:typeof result.detail === 'string' ? result.detail : '无法停止后台，请确认已进入本机资料。'};
        } finally { clearTimeout(timeout); }
        """

    func waitUntilStopped() async throws {
        let deadline = ProcessInfo.processInfo.systemUptime + 10
        var refused = 0
        while ProcessInfo.processInfo.systemUptime < deadline {
            do {
                _ = try await probeHealth(timeout: 1).get()
                refused = 0
            } catch let error as URLError where error.code == .cannotConnectToHost || error.code == .networkConnectionLost {
                refused += 1
                if refused >= 2 { return }
            } catch {
                throw ServiceError.message("无法确认后台是否已停止。请检查连接后重试，或选择仅退出桌宠。")
            }
            try await Task.sleep(nanoseconds: 250_000_000)
        }
        throw ServiceError.message("后台尚未停止，可能仍在结束任务。请稍后重试，或选择仅退出桌宠。")
    }

    func start() async throws {
        if options.externalService { try await verifyHealth(); return }
        guard let executable = Bundle.main.resourceURL?.appendingPathComponent("service/CampusCompanion"),
              FileManager.default.isExecutableFile(atPath: executable.path) else {
            throw ServiceError.message("缺少助手服务，请重新运行构建脚本。")
        }
        try FileManager.default.createDirectory(at: options.dataDirectory, withIntermediateDirectories: true)
        let process = Process()
        process.executableURL = executable
        process.arguments = ["--no-browser", "--data-dir", options.dataDirectory.path]
        if options.projectMode { process.arguments!.append("--project") }
        process.currentDirectoryURL = options.dataDirectory
        var env = ProcessInfo.processInfo.environment
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        process.environment = env
        // The backend launcher owns desktop.log / desktop-error.txt. Opening a
        // protected Desktop file synchronously here can block the UI before a
        // macOS file-access prompt can be handled. Native startup needs no log.
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        launcher = process
        try process.run()
        // The existing launcher verifies database identity, serializes startup,
        // and refuses to attach to a service using a different data directory.
        for _ in 0..<650 {
            if !process.isRunning {
                guard process.terminationStatus == 0 else {
                    throw ServiceError.message("服务启动失败。请查看 \(options.dataDirectory.path)/desktop-error.txt。若旧助手仍运行，请先在其设置中停止服务。")
                }
                try await verifyHealth()
                return
            }
            try await Task.sleep(nanoseconds: 200_000_000)
        }
        process.terminate()
        throw ServiceError.message("服务启动超时，请查看 desktop.log 后重试。")
    }

    func verifyHealth() async throws {
        let (data, response) = try await probeHealth(timeout: 3).get()
        guard let body = try JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            throw ServiceError.message("本机端口返回了无法识别的服务。")
        }
        try Self.validateHealth(status: response?.statusCode ?? 0, body: body)
    }

    nonisolated static func validateHealth(status: Int, body: [String: Any]) throws {
        guard status == 200,
              body["application"] as? String == "campus-companion",
              body["mode"] as? String == "local" else {
            throw ServiceError.message("5173 端口不是本机个人助手。请先关闭冲突服务。")
        }
        let required: Set<String> = ["after-class-checkin", "calendar-course-entry", "pet-state", "schedule-reminders", "planning-constraints-once", "timetable-recognition", "timetable-text", "planning-today", "course-changes", "execution-timers-v1", "profiles-v1", "goals-v1", "weekly-review-v1", "planning-core-v1", "b-interaction-v1", "project-completion-v1"]
        guard let available = body["capabilities"] as? [String], required.isSubset(of: Set(available)) else {
            throw ServiceError.message("检测到旧版后台，缺少新版桌宠功能。请在旧助手设置中停止服务，再点击「重新连接本机服务」。浏览器和桌宠仍可共用升级后的后台，个人资料无需删除。")
        }
    }
}
