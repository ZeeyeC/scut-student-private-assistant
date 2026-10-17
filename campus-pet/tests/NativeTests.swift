import AppKit

@main
struct NativeTests {
    static func main() {
        MainActor.assumeIsolated {
            _ = NSApplication.shared
            let app = AppDelegate()
            app.pet.mood = .approval
            app.toggleSleep()
            precondition(app.pet.mood == .sleeping, "Pause must show sleeping")
            app.toggleSleep()
            precondition(app.pet.mood == .approval, "Resume must retain pending approval")
            for incoming in [PetMood.replying, .approval, .idle] {
                app.toggleSleep()
                app.receiveAssistantMood(incoming)
                precondition(app.pet.mood == .sleeping, "Incoming state must not resume paused animation")
                app.toggleSleep()
                precondition(app.pet.mood == incoming, "Resume must use the state received while paused")
            }
            let menu = app.petMenu()
            guard let exits = menu.item(withTitle: "关闭与退出")?.submenu else { preconditionFailure("Pet must expose an exit submenu") }
            precondition(exits.item(withTitle: "仅退出桌宠（后台继续运行）")?.action == #selector(AppDelegate.quit), "Pet-only exit must keep existing quit behavior")
            precondition(exits.item(withTitle: "停止后台并退出…") != nil, "Service shutdown must be separately selectable")
            let identity: [String: Any] = ["application": "campus-companion", "mode": "local", "desktop_protocol": 1]
            let capabilities = ["after-class-checkin", "calendar-course-entry", "pet-state"]
            func rejects(_ body: [String: Any], status: Int = 200) -> Bool {
                do { try ServiceController.validateHealth(status: status, body: body); return false }
                catch { return true }
            }
            precondition(rejects(identity), "demo1.1 health must be recognized as incompatible")
            for missing in capabilities {
                precondition(rejects(identity.merging(["capabilities": capabilities.filter { $0 != missing }]) { _, new in new }), "Missing capability must block loading old UI")
            }
            let compatible = identity.merging(["capabilities": capabilities]) { _, new in new }
            precondition(!rejects(compatible), "Compatible shared backend must be reusable")
            precondition(rejects(compatible, status: 503))
            precondition(rejects(compatible.merging(["application": "other"]) { _, new in new }))
            precondition(rejects(compatible.merging(["mode": "shared"]) { _, new in new }))
            print("Native regression checks passed")
        }
    }
}
