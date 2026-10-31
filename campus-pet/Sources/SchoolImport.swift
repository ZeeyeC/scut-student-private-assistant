import AppKit

extension AppDelegate {
    func presentWebReference(_ url: URL, title: String = "资料链接") {
        guard ["http", "https"].contains(url.scheme ?? ""), url.host != nil, url.user == nil, url.password == nil else { return }
        showAssistant(page: "日程")
        let data = try! JSONSerialization.data(withJSONObject: ["url": url.absoluteString, "title": title])
        let literal = String(data: data, encoding: .utf8)!
        webView.evaluateJavaScript("window.dispatchEvent(new CustomEvent('campus-web-reference',{detail:\(literal)}));")
    }

    func importReply(_ requestId: String, result: [String: Any] = [:], error: Error? = nil) {
        let body: [String: Any] = ["requestId": requestId, "ok": error == nil, "result": result, "error": error?.localizedDescription ?? ""]
        guard let data = try? JSONSerialization.data(withJSONObject: body), let literal = String(data: data, encoding: .utf8) else { return }
        webView.evaluateJavaScript("window.dispatchEvent(new CustomEvent('campus-native-import-result',{detail:\(literal)}));")
    }

    func handleImportMessage(_ body: [String: Any]) {
        guard body["channel"] as? String == "school-import-v1",
              let requestId = body["requestId"] as? String, UUID(uuidString: requestId) != nil,
              let command = body["command"] as? String,
              let payload = body["payload"] as? [String: Any] else { return }
        func settings() -> [String: Any] { ["browser": browserLaunchPolicy.selectedBrowser.rawValue, "installed": browserLaunchPolicy.installed] }
        do {
            if command == "get-pet-attribution" {
                importReply(requestId, result: PetAttribution.read(resources: Bundle.main.resourceURL)); return
            }
            if command == "get-browser" { importReply(requestId, result: settings()); return }
            if command == "set-browser" {
                guard let raw = payload["browser"] as? String else { throw ServiceError.message("请选择Chrome或Edge。") }
                try browserLaunchPolicy.select(raw); importReply(requestId, result: settings()); return
            }
            if command == "open-extension-manager" {
                try browserLaunchPolicy.openExtensionManager { [weak self] error in Task{@MainActor in self?.importReply(requestId,error:error)} };return
            }
            if command == "copy-extension-path" {
                Task {
                    do {
                        guard let result=try await js("const r=await fetch('/api/local/extension-installation');if(!r.ok)throw new Error('扩展目录暂不可用');return r.json()") as? [String:Any],result["available"] as? Bool == true,let path=result["directory"] as? String else {throw ServiceError.message("扩展文件未准备好，请重新安装完整App。")}
                        NSPasteboard.general.clearContents();NSPasteboard.general.setString(path,forType:.string)
                        importReply(requestId,result:["copied":true])
                    } catch {importReply(requestId,error:error)}
                };return
            }
            if command == "show-import-review",let id=payload["importId"] as? String,UUID(uuidString:id) != nil {
                Task {do {
                    let literal=String(data:try JSONSerialization.data(withJSONObject:[id]),encoding:.utf8)!
                    guard let result=try await js("const r=await fetch('/api/browser-imports/'+encodeURIComponent(\(literal)[0]));if(!r.ok)throw new Error('导入不可用');return r.json()") as? [String:Any],let data=result["data"] as? [String:Any],data["status"] as? String == "preview_ready" else {throw ServiceError.message("课表尚未回传")}
                    showAssistant(page:"日程");_ = try await webView.evaluateJavaScript("window.dispatchEvent(new Event('campus-start-import'))")
                    importReply(requestId,result:["opened":true])
                } catch {importReply(requestId,error:error)}};return
            }
            guard command == "open-school-import", let id = payload["importId"] as? String, UUID(uuidString: id) != nil else {
                throw ServiceError.message("学校导入请求无效。")
            }
            guard !launchingImports.contains(id) else { throw ServiceError.message("正在打开本次导入，请稍候。") }
            launchingImports.insert(id)
            Task {
                do {
                    let secret = (UUID().uuidString + UUID().uuidString).replacingOccurrences(of: "-", with: "").lowercased()
                    let parameters: [String: String] = ["path": "/api/browser-imports/" + id + "/desktop-grant", "secret": secret, "key": UUID().uuidString]
                    let data = try JSONSerialization.data(withJSONObject: parameters)
                    let literal = String(data: data, encoding: .utf8)!
                    guard let grant = try await js("""
                      const p = \(literal);
                      const token = (await (await fetch('/api/csrf')).json()).csrf_token;
                      const response = await fetch(p.path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':token,'Idempotency-Key':p.key},body:JSON.stringify({client_token:p.secret})});
                      const value = await response.json(); if(!response.ok) throw new Error(typeof value.detail==='string'?value.detail:'导入不可用'); return value;
                    """) as? [String: Any],
                          let path = grant["bridge_path"] as? String,
                          let grantId = grant["grant_id"] as? String,
                          let expires = grant["expires_at"] as? String, let expiry = ScheduleReminder.parseDate(expires),
                          let status = grant["status"] as? String,
                          let base = URL(string: path, relativeTo: assistantOrigin)?.absoluteURL,
                          var components = URLComponents(url: base, resolvingAgainstBaseURL: false)
                    else { throw ServiceError.message("导入授权返回内容无效。") }
                    components.fragment = "grant=" + grantId + "." + secret
                    guard let url = components.url else { throw ServiceError.message("导入地址无效。") }
                    try browserLaunchPolicy.launch(SchoolImportContext(id: id, bridgeURL: url, expiresAt: expiry, status: status), origin: assistantOrigin) { error in
                        Task { @MainActor in
                            self.launchingImports.remove(id)
                            self.importReply(requestId, result: settings(), error: error)
                        }
                    }
                } catch {
                    launchingImports.remove(id); importReply(requestId, error: error)
                }
            }
        } catch { importReply(requestId, error: error) }
    }
}
