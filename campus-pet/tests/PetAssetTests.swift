import AppKit
import CryptoKit

@MainActor
func runPetAssetTests() {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent("pet-assets-" + UUID().uuidString)
    try! FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    func png(_ name: String, color: NSColor) -> String {
        let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 420, pixelsHigh: 560, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
        memset(bitmap.bitmapData!, 0, bitmap.bytesPerRow * bitmap.pixelsHigh)
        let rgb = color.usingColorSpace(.deviceRGB)!
        let offset = 300 * bitmap.bytesPerRow + 200 * 4
        bitmap.bitmapData![offset] = UInt8(rgb.redComponent * 255)
        bitmap.bitmapData![offset + 1] = UInt8(rgb.greenComponent * 255)
        bitmap.bitmapData![offset + 2] = UInt8(rgb.blueComponent * 255)
        bitmap.bitmapData![offset + 3] = 255
        let data = bitmap.representation(using: .png, properties: [:])!
        try! data.write(to: root.appendingPathComponent(name))
        return SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    }
    let first = png("first.png", color: .blue), second = png("second.png", color: .red)
    precondition(first != second, "Fixture colors must produce distinct PNG data")
    func frame(_ file: String, _ hash: String, _ duration: Int64) -> [String: Any] { ["file": file, "sha256": hash, "duration_ns": duration, "source_path": "synthetic/" + file] }
    let states = Dictionary(uniqueKeysWithValues: ["starting", "idle", "thinking", "replying", "approval", "error", "sleeping"].map { ($0, "idle") })
    var document: [String: Any] = ["schema_version": 1, "repository": "https://github.com/SbongeBobybl/NaiWaChatPet", "upstream_ref": "008eb12636f517aedecee6f1a1fc773c2f0df6c4", "rights": ["status": "verified", "basis": "Synthetic PNG test fixture"], "canvas": ["width": 420, "height": 560], "ground_y": 540, "default_frame": "first.png", "states": states, "clips": [
        "idle": ["loop": true, "ground_y": 540, "frames": [frame("first.png", first, 85000000), frame("second.png", second, 85000000)]],
        "once": ["loop": false, "ground_y": 540, "frames": [frame("first.png", first, 41666667), frame("second.png", second, 41666667)]],
        "pose": ["loop": true, "ground_y": 540, "pose_hold_ms": 800, "frames": [frame("first.png", first, 83333333)]],
    ], "actions": [["id": "smile", "title": "微笑", "clips": ["pose"], "hold_ms": 800]]]
    func write() { try! JSONSerialization.data(withJSONObject: document).write(to: root.appendingPathComponent("asset-pack.json")) }
    write()
    let pack = try! PetAssetPack.load(from: root)
    let idle = pack.clip(for: .idle)
    precondition(idle.frameIndex(at: 0) == 0 && idle.frameIndex(at: 0.084) == 0)
    precondition(idle.frameIndex(at: 0.085) == 1 && idle.frameIndex(at: 0.170) == 0, "Original 85ms timing and looping")
    let once = pack.clips["once"]!
    precondition(once.frameIndex(at: 0.041666667) == 1 && once.frameIndex(at: 30) == 1)
    precondition(pack.clips["pose"]!.frameIndex(at: 1000) == 0, "A static pose never invents animation")
    precondition(pack.actions.first?.holdMilliseconds == 800)
    precondition(pack.clip(for: .approval).name == "idle", "Use the declared state mapping")
    let geometry = PetGeometry(sourceSize: NSSize(width: 420, height: 560), groundY: 540, targetRect: NSRect(x: 10, y: 20, width: 200, height: 200))
    precondition(abs(geometry.imageRect.width / geometry.imageRect.height - 0.75) < 0.0001)
    let rect = geometry.viewRect(fromSource: NSRect(x: 190, y: 290, width: 20, height: 20))
    let source = geometry.sourcePoint(fromView: NSPoint(x: rect.midX, y: rect.midY))!
    precondition(abs(source.x - 200) < 0.001 && abs(source.y - 300) < 0.001)
    precondition(geometry.sourcePoint(fromView: NSPoint(x: -100, y: -100)) == nil)
    let otherBaseline = PetGeometry(sourceSize: NSSize(width: 420, height: 560), groundY: 520, targetRect: NSRect(x: 10, y: 20, width: 200, height: 200))
    precondition(abs(geometry.viewRect(fromSource: NSRect(x: 0, y: 540, width: 1, height: 0)).minY - otherBaseline.viewRect(fromSource: NSRect(x: 0, y: 520, width: 1, height: 0)).minY) < 0.001, "Different source ground lines share the same visible baseline")
    let cache = PetFrameCache(byteLimit: 420 * 560 * 4)
    precondition(cache.frame(clip: idle, index: 0) != nil)
    precondition(cache.frame(clip: idle, index: 0) != nil && cache.decodeCount == 1)
    precondition(cache.frame(clip: idle, index: 1) != nil && cache.decodeCount == 2)
    precondition(cache.residentBytes <= cache.byteLimit && cache.entryCount == 1, "Evict decoded frames instead of loading the full sequence")
    var mapped = states
    for mood in ["starting", "thinking", "replying", "approval", "error", "sleeping"] { mapped[mood] = "pose" }
    document["states"] = mapped
    document["actions"] = [["id": "smile", "title": "微笑", "clips": ["pose"], "hold_ms": 800], ["id": "surprised", "title": "惊讶", "clips": ["once", "idle"]]]
    write()
    let playback = PetPlayback(pack: try! PetAssetPack.load(from: root))
    playback.update(mood: .idle, reminder: false)
    precondition(playback.play("smile"))
    playback.advance(by: 0.79)
    precondition(playback.activeActionID == "smile" && playback.frameIndex == 0)
    playback.advance(by: 0.02)
    precondition(playback.activeActionID == nil, "A manual static pose holds for exactly the declared 800ms")
    precondition(playback.play("surprised"))
    playback.advance(by: 0.05)
    precondition(playback.currentClip.name == "once" && playback.frameIndex == 1)
    playback.advance(by: 0.04)
    precondition(playback.currentClip.name == "idle" && playback.frameIndex == 0, "Each transition starts with its own zero-based clock")
    playback.update(mood: .approval, reminder: false)
    precondition(playback.activeActionID == nil && playback.currentClip.name == "pose")
    precondition(!playback.play("smile"), "Real approval state outranks a manual performance")
    playback.update(mood: .idle, reminder: true)
    precondition(!playback.play("smile"), "Reminder owns interaction priority")
    playback.update(mood: .idle, reminder: false)
    playback.visible = false
    precondition(!playback.play("smile"))
    let hiddenIndex = playback.frameIndex
    playback.advance(by: 100)
    precondition(playback.frameIndex == hiddenIndex)
    playback.visible = true; playback.reducedMotion = true
    precondition(!playback.play("smile"))
    playback.reducedMotion = false; playback.update(mood: .sleeping, reminder: false)
    playback.advance(by: 100)
    precondition(playback.currentClip.name == "pose" && playback.frameIndex == 0)
    let view = PetView(frame: NSRect(x: 0, y: 0, width: 190, height: 210))
    view.configureAssetPack(try! PetAssetPack.load(from: root))
    view.mood = .idle
    let viewGeometry = view.assetGeometry!
    let pixel = viewGeometry.viewRect(fromSource: NSRect(x: 200, y: 300, width: 1, height: 1))
    let opaquePoint = NSPoint(x: pixel.midX, y: pixel.midY)
    precondition(view.isInteractive(opaquePoint))
    precondition(!view.isInteractive(NSPoint(x: viewGeometry.imageRect.minX + 1, y: viewGeometry.imageRect.minY + 1)), "Transparent sprite corners pass through")
    view.reminderText = "合成提醒"
    precondition(view.isReminderBelly(opaquePoint), "Reminder click uses original source coordinates and alpha")
    view.reminderText = nil
    for mood in [PetMood.starting, .idle, .thinking, .replying, .approval, .error, .sleeping] {
        view.mood = mood
        precondition(view.assetClipName == (mood == .idle ? "idle" : "pose"))
    }
    view.mood = .idle
    precondition(view.playAction("smile"))
    view.mood = .approval
    precondition(!view.hasActiveAction)
    view.mood = .idle; view.animationsVisible = false
    let decoded = view.decodedFrameCount
    view.advanceAnimation(by: 20)
    precondition(view.decodedFrameCount == decoded, "Hidden animation must not decode more frames")
    try! Data("bad PNG".utf8).write(to: root.appendingPathComponent("second.png"))
    let fallbackView = PetView(frame: NSRect(x:0,y:0,width:190,height:210))
    fallbackView.configureAssetPack(pack); fallbackView.mood = .idle
    fallbackView.advanceAnimation(by:0.085)
    precondition(fallbackView.isInteractive(opaquePoint), "Corrupt active frame falls back to the same pack's default frame")
    let freshCache = PetFrameCache()
    precondition(freshCache.frame(clip: idle, index: 1) == nil, "Bad frame bytes must never be displayed")
    precondition(freshCache.frame(clip: idle, index: 0) != nil, "A valid new default frame remains available")
    var clips = document["clips"] as! [String: Any]
    var bad = clips["idle"] as! [String: Any]
    bad["transition_in"] = "missing"
    clips["idle"] = bad; document["clips"] = clips; write()
    precondition((try? PetAssetPack.load(from: root)) == nil, "Missing transition references must fail metadata validation")
    bad.removeValue(forKey: "transition_in"); clips["idle"] = bad; document["clips"] = clips
    document["rights"] = ["status": "pending", "basis": "not cleared"]; write()
    precondition((try? PetAssetPack.load(from: root)) == nil, "Uncleared art must not become an active pack")
}
