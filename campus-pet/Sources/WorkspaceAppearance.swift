import AppKit

enum WorkspaceWindowLayout {
    static func initialFrame(visibleFrame: NSRect, chromeInsets: NSEdgeInsets) -> NSRect {
        let available = visibleFrame.insetBy(dx: 12, dy: 12)
        let size = NSSize(width: min(1280 + chromeInsets.left + chromeInsets.right, available.width),
                          height: min(782 + chromeInsets.top + chromeInsets.bottom, available.height))
        return NSRect(x: available.midX - size.width / 2, y: available.midY - size.height / 2, width: size.width, height: size.height)
    }
}

enum WorkspaceAppearance {
    private static func color(_ light: UInt32, _ dark: UInt32) -> NSColor {
        NSColor(name: nil) { appearance in
            let value = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark : light
            return NSColor(srgbRed: CGFloat((value >> 16) & 255) / 255, green: CGFloat((value >> 8) & 255) / 255, blue: CGFloat(value & 255) / 255, alpha: 1)
        }
    }
    static let ink = color(0x252a35, 0xe5e8ef)
    static let muted = color(0x71798b, 0xa3adbf)
    static let line = color(0xe8ebf1, 0x323a48)
    static let paper = color(0xfefefe, 0x202630)
    static let soft = color(0xf7f8fc, 0x282f3c)
    static let accent = color(0x596bc6, 0xa1afea)
    static let selected = color(0xeaeefa, 0x303b59)
    static let panelSize = NSSize(width: 328, height: 360)
}

// Typed targets are serialized as data, never interpolated as JavaScript source.
enum WorkspaceNavigation {
    static func taskTarget(id:String)->[String:String]? {
        let allowed=CharacterSet(charactersIn:"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-")
        let start=CharacterSet.alphanumerics
        guard !id.isEmpty,id.utf8.count<=200,let first=id.unicodeScalars.first,start.contains(first),id.unicodeScalars.allSatisfy({allowed.contains($0)}) else{return nil}
        return ["page":"tasks","taskId":id]
    }
}
