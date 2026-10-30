import AppKit
import CryptoKit

struct PetDecodedFrame {
    let image: NSImage
    let bitmap: NSBitmapImageRep
    let byteCost: Int
}

@MainActor
final class PetFrameCache {
    let byteLimit: Int
    private(set) var residentBytes = 0
    private(set) var decodeCount = 0
    private var entries: [String: (frame: PetDecodedFrame, tick: UInt64)] = [:]
    private var tick: UInt64 = 0
    var entryCount: Int { entries.count }
    init(byteLimit: Int = 64 * 1024 * 1024) { self.byteLimit = max(0, byteLimit) }
    func removeAll() { entries.removeAll(); residentBytes = 0 }
    func frame(clip: PetClipSpec, index: Int) -> NSImage? { decodedFrame(clip: clip, index: index)?.image }

    func decodedFrame(clip: PetClipSpec, index: Int) -> PetDecodedFrame? {
        guard clip.frames.indices.contains(index) else { return nil }
        tick &+= 1
        let spec = clip.frames[index]
        if let entry = entries[spec.sha256] { entries[spec.sha256] = (entry.frame, tick); return entry.frame }
        guard let handle = try? FileHandle(forReadingFrom: spec.url) else { return nil }
        defer { try? handle.close() }
        let limit = 16 * 1024 * 1024
        guard let data = try? handle.read(upToCount: limit + 1), data.count >= 33, data.count <= limit,
              Array(data.prefix(8)) == [137, 80, 78, 71, 13, 10, 26, 10],
              String(data: data[12..<16], encoding: .ascii) == "IHDR",
              SHA256.hash(data: data).map({ String(format: "%02x", $0) }).joined() == spec.sha256 else { return nil }
        func integer(_ offset: Int) -> UInt32 { data[offset..<offset+4].reduce(UInt32(0)) { ($0 << 8) | UInt32($1) } }
        guard integer(16) == UInt32(clip.sourceSize.width), integer(20) == UInt32(clip.sourceSize.height),
              let bitmap = NSBitmapImageRep(data: data), bitmap.hasAlpha,
              bitmap.pixelsWide == Int(clip.sourceSize.width), bitmap.pixelsHigh == Int(clip.sourceSize.height) else { return nil }
        decodeCount += 1
        let cost = bitmap.bytesPerRow * bitmap.pixelsHigh
        guard cost <= byteLimit else { return nil }
        while residentBytes + cost > byteLimit, let oldest = entries.min(by: { $0.value.tick < $1.value.tick }) {
            residentBytes -= oldest.value.frame.byteCost; entries.removeValue(forKey: oldest.key)
        }
        let image = NSImage(size: clip.sourceSize)
        image.addRepresentation(bitmap)
        let frame = PetDecodedFrame(image: image, bitmap: bitmap, byteCost: cost)
        entries[spec.sha256] = (frame, tick); residentBytes += cost
        return frame
    }
}
