import AppKit

struct PetGeometry {
    let sourceSize: NSSize
    let groundY: CGFloat
    let imageRect: NSRect
    let scale: CGFloat
    init(sourceSize: NSSize, groundY: CGFloat, targetRect: NSRect) {
        self.sourceSize = sourceSize; self.groundY = groundY
        let ratio = min(targetRect.width / max(1, sourceSize.width), targetRect.height / max(1, sourceSize.height))
        scale = ratio.isFinite ? max(0, ratio) : 0
        imageRect = NSRect(x: targetRect.midX - sourceSize.width * scale / 2,
                           y: targetRect.minY - (sourceSize.height - groundY) * scale,
                           width: sourceSize.width * scale, height: sourceSize.height * scale)
    }
    func sourcePoint(fromView point: NSPoint) -> NSPoint? {
        guard scale > 0, imageRect.contains(point) else { return nil }
        let result = NSPoint(x: (point.x - imageRect.minX) / scale, y: sourceSize.height - (point.y - imageRect.minY) / scale)
        return result.x >= 0 && result.x < sourceSize.width && result.y >= 0 && result.y < sourceSize.height ? result : nil
    }
    func viewRect(fromSource rect: NSRect) -> NSRect {
        NSRect(x: imageRect.minX + rect.minX * scale, y: imageRect.minY + (sourceSize.height - rect.maxY) * scale, width: rect.width * scale, height: rect.height * scale)
    }
}
