import AppKit

enum PetMood: String {
    case starting, idle, thinking, replying, approval, error, sleeping
    var message: String {
        switch self {
        case .starting: return "奶蛙正在打开助手…"
        case .idle: return "奶蛙"
        case .thinking: return "让我想一想…"
        case .replying: return "正在回复你"
        case .approval: return "有内容等你确认"
        case .error: return "打开面板看看"
        case .sleeping: return "休息一下 · 点我唤醒"
        }
    }
}

class PetPanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

final class PetView: NSView {
    var mood: PetMood = .starting { didSet { needsDisplay = true } }
    var onClick: (() -> Void)?
    var reminderText: String?
    var taskRingText: String? { didSet { needsDisplay = true } }
    var onReminderClick: (() -> Void)?
    var onMenu: ((NSEvent) -> Void)?
    var onMove: (() -> Void)?
    var onDragStart: (() -> Void)?
    var tick = 0.0
    var reducedMotion = false
    private(set) var animation: PetAnimationClip?
    private(set) var actionElapsed = 0.0
    var activeAction: PetAction? { animation?.action }
    var actionFrameIndex: Int {
        guard let animation else { return 0 }
        return Int(actionElapsed * animation.fps) % animation.images.count
    }
    private var down: NSPoint?
    private var origin: NSPoint?
    private var dragged = false
    private let sprite: NSImage? = {
        let resources = Bundle.main.resourceURL
        if let url = resources?.appendingPathComponent("Animations/idle.png"),
           let image = NSImage(contentsOf: url) { return image }
        return Bundle.main.url(forResource: "naiwa", withExtension: "png").flatMap(NSImage.init(contentsOf:))
    }()
    private lazy var pixels: NSBitmapImageRep? = sprite?.tiffRepresentation.flatMap(NSBitmapImageRep.init(data:))
    static func reminderColor(_ color: NSColor) -> NSColor {
        guard let rgb = color.usingColorSpace(.deviceRGB) else { return color }
        var h: CGFloat = 0, s: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
        rgb.getHue(&h, saturation: &s, brightness: &b, alpha: &a)
        guard h >= 0.04, h <= 0.22, s > 0.20 else { return color }
        return NSColor(deviceHue: 0.77, saturation: s, brightness: b, alpha: a)
    }
    private lazy var purpleSprite: NSImage? = {
        guard let data = sprite?.tiffRepresentation, let bitmap = NSBitmapImageRep(data: data) else { return sprite }
        for y in 0..<bitmap.pixelsHigh {
            for x in 0..<bitmap.pixelsWide {
                if let color = bitmap.colorAt(x: x, y: y) { bitmap.setColor(Self.reminderColor(color), atX: x, y: y) }
            }
        }
        let image = NSImage(size: sprite?.size ?? .zero); image.addRepresentation(bitmap)
        return image
    }()
    func isReminderBelly(_ point: NSPoint) -> Bool {
        let r = displayRect
        let belly = NSRect(x: r.minX + r.width * 0.28, y: r.minY + r.height * 0.20, width: r.width * 0.44, height: r.height * 0.36)
        return reminderText != nil && belly.contains(point) && isInteractive(point)
    }
    private let bubble = NSRect(x: 13, y: 175, width: 164, height: 30)
    private var spriteRect: NSRect {
        guard let sprite else { return .zero }
        let ratio = min(170 / sprite.size.width, 172 / sprite.size.height)
        let size = NSSize(width: sprite.size.width * ratio, height: sprite.size.height * ratio)
        return NSRect(x: (bounds.width - size.width) / 2, y: 0, width: size.width, height: size.height)
    }
    override var isOpaque: Bool { false }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    @discardableResult
    func play(_ action: PetAction) -> Bool {
        guard reminderText == nil, !reducedMotion, let clip = PetAnimationClip(action: action) else { return false }
        animation = clip; actionElapsed = 0; needsDisplay = true
        return true
    }
    func stopAction() { animation = nil; actionElapsed = 0; needsDisplay = true }
    func advanceAnimation(by delta: Double) {
        guard !reducedMotion, mood != .sleeping else { return }
        tick += delta
        if let animation {
            actionElapsed += delta
            if actionElapsed >= animation.duration { stopAction() }
        }
        needsDisplay = true
    }
    private var displayRect: NSRect {
        var rect = spriteRect
        if animation == nil, !reducedMotion, mood != .sleeping {
            rect.size.height += sin(tick * 2) * 1.8
            if mood == .replying { rect.origin.y += abs(sin(tick * 4)) * 3 }
        }
        return rect
    }
    func isInteractive(_ point: NSPoint) -> Bool {
        if bubble.contains(point) { return true }
        let rect = displayRect
        let pixels = animation.map { $0.pixels[actionFrameIndex] } ?? self.pixels
        guard rect.contains(point), let pixels else { return false }
        let x = min(pixels.pixelsWide - 1, max(0, Int((point.x - rect.minX) / rect.width * CGFloat(pixels.pixelsWide))))
        let y = min(pixels.pixelsHigh - 1, max(0, Int((rect.maxY - point.y) / rect.height * CGFloat(pixels.pixelsHigh))))
        return (pixels.colorAt(x: x, y: y)?.alphaComponent ?? 0) > 0.1
    }
    override func mouseDown(with event: NSEvent) {
        down = NSEvent.mouseLocation; origin = window?.frame.origin; dragged = false
    }
    override func mouseDragged(with event: NSEvent) {
        guard let down, let origin, let window else { return }
        let mouse = NSEvent.mouseLocation
        let dx = mouse.x - down.x, dy = mouse.y - down.y
        if !dragged, hypot(dx, dy) > 4 { dragged = true; onDragStart?() }
        if dragged { window.setFrameOrigin(NSPoint(x: origin.x + dx, y: origin.y + dy)) }
    }
    override func mouseUp(with event: NSEvent) {
        if dragged { onMove?() }
        else if isReminderBelly(convert(event.locationInWindow, from: nil)) { onReminderClick?() }
        else { onClick?() }
        down = nil; origin = nil
    }
    override func rightMouseDown(with event: NSEvent) { onMenu?(event) }
    override func accessibilityPerformPress() -> Bool {
        if reminderText != nil { onReminderClick?() } else { onClick?() }; return true
    }

    override func draw(_ dirtyRect: NSRect) {
        NSColor.clear.setFill(); bounds.fill(using: .copy)
        let moving = !reducedMotion && mood != .sleeping && animation == nil
        let rect = displayRect
        NSGraphicsContext.saveGraphicsState()
        if mood == .thinking && moving {
            let transform = NSAffineTransform()
            transform.translateX(by: bounds.midX, yBy: 80)
            transform.rotate(byDegrees: sin(tick * 2) * 2)
            transform.translateX(by: -bounds.midX, yBy: -80)
            transform.concat()
        }
        let image = reminderText != nil ? purpleSprite : (animation.map { $0.images[actionFrameIndex] } ?? sprite)
        image?.draw(in: rect, from: .zero, operation: .sourceOver, fraction: mood == .sleeping ? 0.72 : 1, respectFlipped: true, hints: [.interpolation: NSImageInterpolation.high])
        NSGraphicsContext.restoreGraphicsState()
        let accent: NSColor = mood == .error ? .systemOrange : NSColor(srgbRed: 0.36, green: 0.48, blue: 0.20, alpha: 1)
        if mood == .thinking {
            for i in 0..<3 {
                accent.withAlphaComponent(0.35 + 0.65 * abs(sin(tick * 4 + Double(i)))).setFill()
                NSBezierPath(ovalIn: NSRect(x: 139 + CGFloat(i) * 10, y: 143, width: 5, height: 5)).fill()
            }
        }
        if mood == .sleeping {
            ("z Z" as NSString).draw(at: NSPoint(x: 140, y: 136), withAttributes: [.font: NSFont.systemFont(ofSize: 15, weight: .semibold), .foregroundColor: accent])
        }
        NSColor(srgbRed: 1, green: 0.99, blue: 0.94, alpha: 0.98).setFill()
        NSBezierPath(roundedRect: bubble, xRadius: 15, yRadius: 15).fill()
        let style = NSMutableParagraphStyle(); style.alignment = .center
        let message = reminderText ?? taskRingText ?? (mood == .idle ? (activeAction?.title ?? mood.message) : mood.message)
        (message as NSString).draw(in: NSRect(x: 15, y: 182, width: 160, height: 18), withAttributes: [
            .font: NSFont.systemFont(ofSize: 11, weight: .medium),
            .foregroundColor: NSColor(srgbRed: 0.29, green: 0.32, blue: 0.18, alpha: 1),
            .paragraphStyle: style,
        ])
    }
}
