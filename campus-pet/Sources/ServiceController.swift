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
    init(options: LaunchOptions) { self.options = options }

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
        var request = URLRequest(url: assistantOrigin.appendingPathComponent("api/healthz"))
        request.timeoutInterval = 3
        let (data, response) = try await URLSession.shared.data(for: request)
        guard (response as? HTTPURLResponse)?.statusCode == 200,
              let body = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              body["application"] as? String == "campus-companion",
              body["mode"] as? String == "local" else {
            throw ServiceError.message("5173 端口不是本机个人助手。请先关闭冲突服务。")
        }
    }
}
