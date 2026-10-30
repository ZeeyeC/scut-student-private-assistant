import AppKit

@MainActor
func runWorkspaceWindowTests() {
    for chrome: CGFloat in [28, 38] {
        let frame = WorkspaceWindowLayout.initialFrame(visibleFrame: NSRect(x: 0, y: 0, width: 1440, height: 900), chromeInsets: NSEdgeInsets(top: chrome, left: 0, bottom: 0, right: 0))
        precondition(frame.size == NSSize(width: 1280, height: 782 + chrome), "Full workspace must match the reference product area")
    }
    let screen = NSRect(x: -850, y: 100, width: 850, height: 640)
    let limited = WorkspaceWindowLayout.initialFrame(visibleFrame: screen, chromeInsets: NSEdgeInsets(top: 28, left: 0, bottom: 0, right: 0))
    precondition(screen.contains(limited), "Small and negative-origin screens must contain the complete window")
    let app = AppDelegate()
    precondition(!app.compact, "First launch opens the complete window")
}
