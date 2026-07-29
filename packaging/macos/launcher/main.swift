// StockHelperLauncher - macOS 应用启动器
// 负责启动后端服务、打开浏览器、管理应用生命周期

import Cocoa
import Foundation

class AppDelegate: NSObject, NSApplicationDelegate {
    var backendProcess: Process?
    var statusBar: NSStatusItem?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // 1. 启动后端
        launchBackend()

        // 2. 等待后端就绪
        DispatchQueue.global().async {
            self.waitForBackend()

            // 3. 打开浏览器
            DispatchQueue.main.async {
                self.openBrowser()
            }
        }

        // 4. 创建状态栏图标
        createStatusItem()
    }

    func launchBackend() {
        let bundlePath = Bundle.main.bundlePath
        let backendPath = bundlePath + "/Contents/Resources/backend/stock-helper-server"

        backendProcess = Process()
        backendProcess?.executableURL = URL(fileURLWithPath: backendPath)
        backendProcess?.arguments = []

        // 设置数据目录
        let dataDir = NSHomeDirectory() + "/Library/Application Support/Stock Helper"
        let env = ProcessInfo.processInfo.environment
        backendProcess?.environment = env

        do {
            try backendProcess?.run()
        } catch {
            // 显示错误对话框
            let alert = NSAlert()
            alert.messageText = "启动失败"
            alert.informativeText = "无法启动后端服务: \(error.localizedDescription)"
            alert.runModal()
            NSApp.terminate(nil)
        }
    }

    func waitForBackend() {
        let url = URL(string: "http://127.0.0.1:8765/api/health")!
        for _ in 0..<30 {
            let semaphore = DispatchSemaphore(value: 0)
            var success = false

            let task = URLSession.shared.dataTask(with: url) { _, response, _ in
                if let r = response as? HTTPURLResponse, r.statusCode == 200 {
                    success = true
                }
                semaphore.signal()
            }
            task.resume()
            semaphore.wait()

            if success { return }
            Thread.sleep(forTimeInterval: 1.0)
        }
    }

    func openBrowser() {
        if let url = URL(string: "http://127.0.0.1:8765") {
            NSWorkspace.shared.open(url)
        }
    }

    func createStatusItem() {
        statusBar = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        if let button = statusBar?.button {
            button.title = "📈"
        }

        let menu = NSMenu()
        menu.addItem(NSMenuItem(title: "打开股票分析助手", action: #selector(openApp), keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator)
        menu.addItem(NSMenuItem(title: "退出", action: #selector(quitApp), keyEquivalent: "q"))
        statusBar?.menu = menu
    }

    @objc func openApp() {
        openBrowser()
    }

    @objc func quitApp() {
        backendProcess?.terminate()
        NSApp.terminate(nil)
    }

    func applicationWillTerminate(_ notification: Notification) {
        backendProcess?.terminate()
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
