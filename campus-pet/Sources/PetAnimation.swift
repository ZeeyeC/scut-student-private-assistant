import AppKit

enum PetAction: String, CaseIterable {
    case flashStep = "flash-step", armSwing = "arm-swing", bearShake = "bear-shake"

    var repeatCount: Int { self == .bearShake ? 2 : 1 }

    var title: String {
        switch self {
        case .flashStep: return "闪身步"
        case .armSwing: return "大抡臂"
        case .bearShake: return "狗熊哆嗦毛"
        }
    }
}

/// Only the playing clip is retained. The app never decodes or plays audio.
final class PetAnimationClip {
    let action: PetAction
    let fps: Double
    let images: [NSImage]
    let pixels: [NSBitmapImageRep]
    var duration: Double { Double(images.count * action.repeatCount) / fps }

    init?(action: PetAction) {
        guard let resources = Bundle.main.resourceURL else { return nil }
        let base = resources.appendingPathComponent("Animations", isDirectory: true)
        guard let data = try? Data(contentsOf: base.appendingPathComponent("manifest.json")),
              let manifest = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let rate = manifest["fps"] as? Double, rate > 0, rate <= 60,
              let clips = manifest["clips"] as? [[String: Any]],
              let spec = clips.first(where: { $0["id"] as? String == action.rawValue }),
              let count = spec["frameCount"] as? Int, count > 0, count <= 240 else { return nil }
        var frames: [NSImage] = []
        var bitmaps: [NSBitmapImageRep] = []
        for index in 0..<count {
            let url = base.appendingPathComponent(action.rawValue).appendingPathComponent(String(format: "%04d.png", index))
            guard let data = try? Data(contentsOf: url), let bitmap = NSBitmapImageRep(data: data), bitmap.hasAlpha,
                  bitmap.pixelsWide == 320, bitmap.pixelsHigh == 320 else { return nil }
            let image = NSImage(size: NSSize(width: 320, height: 320))
            image.addRepresentation(bitmap)
            frames.append(image); bitmaps.append(bitmap)
        }
        self.action = action; fps = rate; images = frames; pixels = bitmaps
    }
}
