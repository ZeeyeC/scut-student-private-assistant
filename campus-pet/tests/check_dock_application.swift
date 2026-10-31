import AppKit
import Foundation

// Read the running application's policy from macOS, without launching or
// interacting with the user's windows, database or Dock preferences.
let url = URL(fileURLWithPath: CommandLine.arguments[1]).standardizedFileURL
let app = NSWorkspace.shared.runningApplications.first {
    $0.bundleURL?.standardizedFileURL == url
}
let regular = app?.activationPolicy == .regular
let normalBundle = (Bundle(url: url)?.object(forInfoDictionaryKey: "LSUIElement") as? Bool) != true
let iconPresent = app?.icon != nil
let passed = app != nil && regular && normalBundle && iconPresent
let result: [String: Any] = ["passed": passed, "running": app != nil,
    "regular_activation_policy": regular, "normal_app_bundle": normalBundle,
    "application_icon_available": iconPresent,
    "scope": "macOS running application Dock eligibility; user Dock indicator preferences unchanged"]
let data = try JSONSerialization.data(withJSONObject: result, options: [.sortedKeys])
print(String(data: data, encoding: .utf8)!)
exit(passed ? 0 : 1)
