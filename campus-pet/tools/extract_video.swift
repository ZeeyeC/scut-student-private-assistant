import AppKit
import AVFoundation

// Extract user-provided video frames with Apple's native decoder. No audio.
let args = CommandLine.arguments
if args.count < 4 {
    fputs("Usage: extract_video input.mp4 output-directory step [start] [end] [max-size]\n", stderr)
    exit(1)
}
let input = URL(fileURLWithPath: args[1])
let output = URL(fileURLWithPath: args[2], isDirectory: true)
let step = Double(args[3])!
let start = args.count > 4 ? Double(args[4])! : 0
let asset = AVURLAsset(url: input)
let end = args.count > 5 ? Double(args[5])! : CMTimeGetSeconds(asset.duration)
let size = args.count > 6 ? Double(args[6])! : 800
let generator = AVAssetImageGenerator(asset: asset)
generator.appliesPreferredTrackTransform = true
generator.maximumSize = CGSize(width: size, height: size)
generator.requestedTimeToleranceBefore = .zero
generator.requestedTimeToleranceAfter = .zero
try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
var count = 0
for time in stride(from: start, to: end, by: step) {
    let image = try generator.copyCGImage(at: CMTime(seconds: time, preferredTimescale: 600), actualTime: nil)
    let bitmap = NSBitmapImageRep(cgImage: image)
    let data = bitmap.representation(using: .png, properties: [:])!
    try data.write(to: output.appendingPathComponent(String(format: "%06d.png", count)))
    count += 1
}
print("Extracted \(count) frames, \(start)…\(end)s, step \(step)s")
