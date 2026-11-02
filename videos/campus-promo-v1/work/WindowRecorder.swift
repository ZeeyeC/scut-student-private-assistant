import AppKit
import ScreenCaptureKit
import AVFoundation

// Passive capture only. Input and navigation stay in the CUA tool.
@available(macOS 15.0, *)
final class RecordingObserver: NSObject, SCRecordingOutputDelegate {
    var finished = false
    var failure: Error?
    func recordingOutputDidStartRecording(_ output: SCRecordingOutput) {
        print("recording_started"); fflush(stdout)
    }
    func recordingOutputDidFinishRecording(_ output: SCRecordingOutput) {
        finished = true
    }
    func recordingOutput(_ output: SCRecordingOutput, didFailWithError error: Error) {
        failure = error; finished = true
    }
}

@main
struct WindowRecorder {
    @MainActor static func main() async throws {
        guard #available(macOS 15.0, *) else { fatalError("Requires macOS 15+") }
        _ = NSApplication.shared
        let args = CommandLine.arguments
        guard args.count >= 3 else { fatalError("Usage: WindowRecorder still|record output [seconds]") }
        let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: false)
        guard let window = content.windows.first(where: {
            $0.owningApplication?.bundleIdentifier == "cn.campuscompanion.pet"
            && $0.title == "课间 · 桌宠助手"
            && $0.frame.width > 600
        }) else { fatalError("Assistant window not found; no fallback to screen capture") }
        let target = URL(fileURLWithPath: args[2])
        guard !FileManager.default.fileExists(atPath: target.path) else { fatalError("Will not overwrite existing footage") }
        let applicationOnly = args[1].hasSuffix("-app")
        let filter: SCContentFilter
        if applicationOnly {
            guard let app = content.applications.first(where: {$0.bundleIdentifier == "cn.campuscompanion.pet"}),
                  let display = content.displays.first(where: {$0.displayID == CGMainDisplayID()}) else {
                fatalError("Target application/display unavailable; refusing full-screen fallback")
            }
            filter = SCContentFilter(display: display, including: [app], exceptingWindows: [])
            filter.includeMenuBar = false
        } else {
            filter = SCContentFilter(desktopIndependentWindow: window)
        }
        let config = SCStreamConfiguration()
        config.width = Int(window.frame.width * 2)
        config.height = Int(window.frame.height * 2)
        config.minimumFrameInterval = CMTime(value: 1, timescale: 30)
        config.showsCursor = false
        config.capturesAudio = false
        config.ignoreShadowsSingleWindow = true
        let background = CGColor(red: 0.953, green: 0.961, blue: 0.98, alpha: 1)
        defer { withExtendedLifetime(background) {} }
        config.backgroundColor = background
        if applicationOnly, let display = content.displays.first(where: {$0.displayID == CGMainDisplayID()}) {
            config.width = display.width
            config.height = display.height
        }
        if args[1] == "still" || args[1] == "still-app" {
            let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: config)
            let bitmap = NSBitmapImageRep(cgImage: image)
            try bitmap.representation(using: .png, properties: [:])!.write(to: target)
            print("single_window_still_saved")
            return
        }
        guard ["record", "record-app"].contains(args[1]), args.count == 4, let seconds = Double(args[3]), seconds > 0, seconds <= 900 else { fatalError("Recording limit 1–900 seconds") }
        let observer = RecordingObserver()
        let recordingConfig = SCRecordingOutputConfiguration()
        recordingConfig.outputURL = target
        recordingConfig.videoCodecType = .h264
        recordingConfig.outputFileType = .mp4
        let recording = SCRecordingOutput(configuration: recordingConfig, delegate: observer)
        let stream = SCStream(filter: filter, configuration: config, delegate: nil)
        try stream.addRecordingOutput(recording)
        try await stream.startCapture()
        let stopFile = target.appendingPathExtension("stop")
        let deadline = Date().addingTimeInterval(seconds)
        while Date() < deadline && !observer.finished && !FileManager.default.fileExists(atPath: stopFile.path) {
            try await Task.sleep(for: .milliseconds(100))
        }
        if !observer.finished { try await stream.stopCapture() }
        for _ in 0..<100 where !observer.finished { try await Task.sleep(for: .milliseconds(50)) }
        if let error = observer.failure { throw error }
        guard observer.finished else { fatalError("Recording did not finalize") }
        print("single_window_recording_finished")
    }
}
