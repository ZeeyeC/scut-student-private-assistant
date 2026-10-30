import AppKit

enum PetAssetError: LocalizedError {
    case invalid(String)
    var errorDescription: String? { if case .invalid(let reason) = self { return "桌宠资源无效：" + reason }; return nil }
}

struct PetFrameSpec {
    let file: String
    let url: URL
    let sha256: String
    let durationNanoseconds: Int64
}

struct PetClipSpec {
    let name: String
    let frames: [PetFrameSpec]
    let loop: Bool
    let sourceSize: NSSize
    let groundY: CGFloat
    let transitionIn: String
    let transitionOut: String
    let poseHoldMilliseconds: Int?
    var duration: TimeInterval { Double(frames.reduce(Int64(0)) { $0 + $1.durationNanoseconds }) / 1_000_000_000 }

    func frameIndex(at elapsed: TimeInterval) -> Int {
        guard frames.count > 1, elapsed.isFinite, elapsed > 0 else { return 0 }
        let total = duration * 1_000_000_000
        var time = elapsed * 1_000_000_000
        if loop { time = time.truncatingRemainder(dividingBy: total) }
        else if time >= total { return frames.count - 1 }
        var boundary: Double = 0
        for (index, frame) in frames.enumerated() {
            boundary += Double(frame.durationNanoseconds)
            if time < boundary { return index }
        }
        return frames.count - 1
    }
}

struct PetManualAction {
    let id: String
    let title: String
    let clips: [String]
    let holdMilliseconds: Int?
}

struct PetAssetPack {
    let directory: URL
    let sourceSize: NSSize
    let groundY: CGFloat
    let clips: [String: PetClipSpec]
    let states: [String: String]
    let actions: [PetManualAction]
    var defaultClip: PetClipSpec { clips[states["idle"]!]! }
    func clip(for mood: PetMood) -> PetClipSpec { clips[states[mood.rawValue] ?? states["idle"]!] ?? defaultClip }

    private struct RawFrame: Decodable { let file: String; let sha256: String; let duration_ns: Int64 }
    private struct RawClip: Decodable { let frames: [RawFrame]; let loop: Bool; let ground_y: CGFloat?; let transition_in: String?; let transition_out: String?; let pose_hold_ms: Int? }
    private struct RawAction: Decodable { let id: String; let title: String; let clips: [String]; let hold_ms: Int? }
    private struct RawRights: Decodable { let status: String; let basis: String }
    private struct RawCanvas: Decodable { let width: Int; let height: Int }
    private struct RawPack: Decodable {
        let schema_version: Int; let upstream_ref: String; let rights: RawRights; let canvas: RawCanvas
        let ground_y: CGFloat; let default_frame: String; let clips: [String: RawClip]; let states: [String: String]; let actions: [RawAction]
    }

    static func load(from directory: URL) throws -> PetAssetPack {
        let root = directory.resolvingSymlinksInPath().standardizedFileURL
        let manifest = root.appendingPathComponent("asset-pack.json")
        guard (try manifest.resourceValues(forKeys: [.fileSizeKey]).fileSize ?? Int.max) <= 1_048_576 else { throw PetAssetError.invalid("清单过大") }
        let raw = try JSONDecoder().decode(RawPack.self, from: Data(contentsOf: manifest))
        guard raw.schema_version == 1, raw.upstream_ref == "008eb12636f517aedecee6f1a1fc773c2f0df6c4",
              raw.rights.status == "verified", !raw.rights.basis.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              raw.canvas.width == 420, raw.canvas.height == 560,
              raw.ground_y.isFinite, (0...560).contains(raw.ground_y), raw.clips.count <= 64
        else { throw PetAssetError.invalid("来源、许可或画布不匹配") }
        func fileURL(_ relative: String) throws -> URL {
            guard !relative.isEmpty, !relative.hasPrefix("/"), !relative.contains("\\"), !relative.contains("\0"), !relative.split(separator: "/").contains("..") else { throw PetAssetError.invalid("资源路径越界") }
            let url = root.appendingPathComponent(relative).standardizedFileURL
            guard url.path.hasPrefix(root.path + "/"), url.resolvingSymlinksInPath().path == url.path else { throw PetAssetError.invalid("资源路径不是独立文件") }
            return url
        }
        var clips: [String: PetClipSpec] = [:]
        let size = NSSize(width: raw.canvas.width, height: raw.canvas.height)
        for (name, clip) in raw.clips {
            guard name.range(of: "^[a-z][a-z0-9_]{0,39}$", options: .regularExpression) != nil,
                  (1...240).contains(clip.frames.count),
                  (clip.ground_y ?? raw.ground_y).isFinite, (0...560).contains(clip.ground_y ?? raw.ground_y),
                  clip.pose_hold_ms == nil || (clip.pose_hold_ms == 800 && clip.frames.count == 1)
            else { throw PetAssetError.invalid("片段格式错误") }
            let frames = try clip.frames.map { frame -> PetFrameSpec in
                guard frame.sha256.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil,
                      frame.duration_ns > 0, frame.duration_ns <= 10_000_000_000 else { throw PetAssetError.invalid("帧校验值或时长错误") }
                return PetFrameSpec(file: frame.file, url: try fileURL(frame.file), sha256: frame.sha256, durationNanoseconds: frame.duration_ns)
            }
            clips[name] = PetClipSpec(name: name, frames: frames, loop: clip.loop, sourceSize: size, groundY: clip.ground_y ?? raw.ground_y, transitionIn: clip.transition_in ?? "", transitionOut: clip.transition_out ?? "", poseHoldMilliseconds: clip.pose_hold_ms)
        }
        let moods = Set(["starting", "idle", "thinking", "replying", "approval", "error", "sleeping"])
        guard Set(raw.states.keys) == moods, raw.states.values.allSatisfy({ clips[$0] != nil }),
              let idleName = raw.states["idle"], let idle = clips[idleName], idle.frames.first?.file == raw.default_frame,
              FileManager.default.fileExists(atPath: try fileURL(raw.default_frame).path), raw.actions.count <= 16
        else { throw PetAssetError.invalid("状态或默认帧不完整") }
        for clip in clips.values {
            guard [clip.transitionIn, clip.transitionOut].allSatisfy({ $0.isEmpty || clips[$0] != nil }) else { throw PetAssetError.invalid("缺少转场") }
        }
        var seen = Set<String>()
        let actions = try raw.actions.map { action -> PetManualAction in
            guard seen.insert(action.id).inserted, !action.id.isEmpty, !action.title.isEmpty,
                  !action.clips.isEmpty, action.clips.count <= 8, action.clips.allSatisfy({ clips[$0] != nil }),
                  action.hold_ms == nil || (action.hold_ms == 800 && action.clips.count == 1 && clips[action.clips[0]]!.frames.count == 1)
            else { throw PetAssetError.invalid("动作映射错误") }
            return PetManualAction(id: action.id, title: action.title, clips: action.clips, holdMilliseconds: action.hold_ms)
        }
        return PetAssetPack(directory: root, sourceSize: size, groundY: raw.ground_y, clips: clips, states: raw.states, actions: actions)
    }
}
