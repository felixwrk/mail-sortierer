// Mail-Sortierer – native Mac-App
// Öffnet ein eigenes Fenster, startet im Hintergrund den lokalen Mail-Dienst (mailsortierer.py)
// und beendet ihn wieder, wenn die App geschlossen wird.

import Cocoa
import WebKit

let PORT = 8765
let APP_URL = URL(string: "http://127.0.0.1:\(PORT)/")!

final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate,
                         WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var webView: WKWebView!
    var server: Process?

    // MARK: Start

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()

        let config = WKWebViewConfiguration()
        config.userContentController.add(self, name: "app")
        webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.setValue(false, forKey: "drawsBackground")

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1100, height: 760),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        window.title = "Mail-Sortierer"
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.backgroundColor = NSColor(name: nil) { appearance in
            let dark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            return dark ? NSColor(srgbRed: 0.059, green: 0.067, blue: 0.082, alpha: 1)
                        : NSColor(srgbRed: 0.953, green: 0.957, blue: 0.969, alpha: 1)
        }
        window.minSize = NSSize(width: 440, height: 600)
        window.contentView = webView
        window.delegate = self
        window.center()
        window.setFrameAutosaveName("MailSortiererHauptfenster")
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        showMessage("Mail-Sortierer wird gestartet …", spinner: true)
        startServer()
        waitForServer(attempt: 0)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ notification: Notification) {
        if let s = server, s.isRunning { s.terminate() }
    }

    // MARK: Hintergrund-Dienst

    func findPython() -> String? {
        let candidates = ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
        return candidates.first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    func logFileURL() -> URL {
        let dir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/MailSortierer", isDirectory: true)
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let file = dir.appendingPathComponent("log.txt")
        FileManager.default.createFile(atPath: file.path, contents: nil)
        return file
    }

    func startServer() {
        guard let python = findPython(),
              let script = Bundle.main.path(forResource: "mailsortierer", ofType: "py") else {
            showMessage("Python 3 wurde nicht gefunden. Öffne das Terminal und gib ein: xcode-select --install", spinner: false)
            return
        }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: python)
        p.arguments = [script, "--app"]
        if let log = try? FileHandle(forWritingTo: logFileURL()) {
            p.standardOutput = log
            p.standardError = log
        }
        do {
            try p.run()
            server = p
        } catch {
            showMessage("Der Mail-Dienst konnte nicht gestartet werden: \(error.localizedDescription)", spinner: false)
        }
    }

    func waitForServer(attempt: Int) {
        var request = URLRequest(url: APP_URL.appendingPathComponent("api/status"))
        request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { _, response, _ in
            DispatchQueue.main.async {
                if (response as? HTTPURLResponse)?.statusCode == 200 {
                    self.webView.load(URLRequest(url: APP_URL))
                } else if attempt < 80 {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { self.waitForServer(attempt: attempt + 1) }
                } else {
                    self.showMessage("Der Mail-Dienst antwortet nicht. Details stehen in ~/Library/Application Support/MailSortierer/log.txt", spinner: false)
                }
            }
        }.resume()
    }

    func showMessage(_ text: String, spinner: Bool) {
        let spin = spinner ? "<div class=s></div>" : ""
        let html = """
        <html><head><meta charset=utf-8><style>
        :root{color-scheme:light dark}
        body{margin:0;height:100vh;display:grid;place-items:center;font:15px -apple-system,sans-serif;
             color:#6b7080;background:#f3f4f7;text-align:center;padding:24px;box-sizing:border-box}
        @media (prefers-color-scheme:dark){body{background:#0f1115;color:#9aa0ad}}
        .s{width:28px;height:28px;border:3px solid rgba(128,128,128,.25);border-top-color:#3a5bd9;
           border-radius:50%;animation:r .8s linear infinite;margin:0 auto 14px}
        @keyframes r{to{transform:rotate(360deg)}}
        </style></head><body><div>\(spin)\(text)</div></body></html>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }

    // MARK: Web-Inhalt

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage) {
        if let body = message.body as? String, body == "quit" { NSApp.terminate(nil) }
    }

    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = action.request.url else { decisionHandler(.allow); return }
        if url.host == "127.0.0.1" || url.host == "localhost" || url.scheme == "about" || url.scheme == "data" {
            decisionHandler(.allow)
        } else {
            NSWorkspace.shared.open(url)   // externe Links (z. B. Gmail) im Standardbrowser öffnen
            decisionHandler(.cancel)
        }
    }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url { NSWorkspace.shared.open(url) }
        return nil
    }

    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Abbrechen")
        alert.beginSheetModal(for: window) { response in completionHandler(response == .alertFirstButtonReturn) }
    }

    // MARK: Menüleiste

    @objc func reloadPage(_ sender: Any?) { webView.load(URLRequest(url: APP_URL)) }

    func buildMenu() {
        let main = NSMenu()

        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Über Mail-Sortierer",
                        action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Mail-Sortierer ausblenden", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Mail-Sortierer beenden", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        main.addItem(appItem)

        let editItem = NSMenuItem()
        let edit = NSMenu(title: "Bearbeiten")
        edit.addItem(withTitle: "Ausschneiden", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Kopieren", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Einsetzen", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Alles auswählen", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = edit
        main.addItem(editItem)

        let viewItem = NSMenuItem()
        let view = NSMenu(title: "Darstellung")
        let reload = NSMenuItem(title: "Neu laden", action: #selector(reloadPage(_:)), keyEquivalent: "r")
        reload.target = self
        view.addItem(reload)
        view.addItem(.separator())
        view.addItem(withTitle: "Vollbild", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
            .keyEquivalentModifierMask = [.command, .control]
        viewItem.submenu = view
        main.addItem(viewItem)

        let winItem = NSMenuItem()
        let win = NSMenu(title: "Fenster")
        win.addItem(withTitle: "Im Dock ablegen", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        win.addItem(withTitle: "Schließen", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        winItem.submenu = win
        main.addItem(winItem)
        NSApp.windowsMenu = win

        NSApp.mainMenu = main
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
