import AppKit
import WebKit

struct PetTodoPanelState {
    var payload: [String:Any]
    static var loading: Self { Self(payload:["status":"loading","tasks":[]]) }
}

@MainActor
private final class TodoMessageProxy: NSObject, WKScriptMessageHandler {
    weak var owner: PetTodoPanel?
    func userContentController(_ controller: WKUserContentController,didReceive message: WKScriptMessage) { owner?.receive(message) }
}

@MainActor
final class PetTodoPanel: NSPanel, WKNavigationDelegate {
    let renderer: WKWebView
    private let proxy=TodoMessageProxy()
    private var state=PetTodoPanelState.loading
    private(set) var rendererReady=false
    var onAction: ((String,String?)->Void)?
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
    init() {
        let config=WKWebViewConfiguration();config.websiteDataStore = .nonPersistent()
        renderer=WKWebView(frame:.zero,configuration:config)
        super.init(contentRect:NSRect(x:0,y:0,width:328,height:360),styleMask:[.borderless,.nonactivatingPanel],backing:.buffered,defer:false)
        title="桌宠待办";isOpaque=false;backgroundColor = .clear;hasShadow=true
        hidesOnDeactivate=false;isReleasedWhenClosed=false;level=NSWindow.Level(rawValue:NSWindow.Level.floating.rawValue+1)
        collectionBehavior=[.canJoinAllSpaces,.fullScreenAuxiliary]
        renderer.navigationDelegate=self;renderer.setValue(false,forKey:"drawsBackground")
        renderer.wantsLayer=true;renderer.layer?.cornerRadius=12;renderer.layer?.masksToBounds=true
        contentView=renderer;proxy.owner=self
        config.userContentController.add(proxy,name:"todo")
        if let url=Bundle.main.url(forResource:"PetTodo",withExtension:"html") { renderer.loadFileURL(url,allowingReadAccessTo:url) }
    }
    func render(_ state:PetTodoPanelState) {
        self.state=state
        guard rendererReady else { return }
        renderer.callAsyncJavaScript("window.renderTodo(state)",arguments:["state":state.payload],in:nil,in:.page,completionHandler:{_ in})
    }
    func receive(_ message:WKScriptMessage) {
        guard message.webView === renderer,message.frameInfo.isMainFrame,
              message.frameInfo.request.url == Bundle.main.url(forResource:"PetTodo",withExtension:"html"),
              let body=message.body as? [String:Any],let action=body["action"] as? String else { return }
        if action == "ready" { rendererReady=true;render(state);return }
        guard isVisible,["close","select","complete","back","all","retry","review"].contains(action) else { return }
        let id=body["id"] as? String
        if ["select","complete"].contains(action) {
            guard let id,let tasks=state.payload["tasks"] as? [[String:Any]],
                  tasks.contains(where:{$0["id"] as? String == id && $0["pending"] as? Bool != true && (action != "complete" || $0["done"] as? Bool != true)}) else { return }
        }
        onAction?(action,id)
    }
    func webView(_ webView:WKWebView,decidePolicyFor navigationAction:WKNavigationAction,decisionHandler:@escaping(WKNavigationActionPolicy)->Void) {
        decisionHandler(navigationAction.targetFrame?.isMainFrame == true && navigationAction.request.url == Bundle.main.url(forResource:"PetTodo",withExtension:"html") ? .allow : .cancel)
    }
}

// WebKit's localized error omits the useful API failure text.
enum TodoError {
    static func message(_ error:Error)->String {
        let native=error as NSError
        if let text=native.userInfo["WKJavaScriptExceptionMessage"] as? String,!text.isEmpty {return String(text.prefix(500))}
        return error.localizedDescription
    }
}
