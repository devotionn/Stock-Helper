import Cocoa
import Foundation

#if canImport(Sparkle)
import Sparkle
#endif

class AppDelegate: NSObject, NSApplicationDelegate {
    var backendProcess: Process?
    var statusBar: NSStatusItem?
    #if canImport(Sparkle)
    var updaterController: SPUStandardUpdaterController?
    #endif

    func applicationDidFinishLaunching(_ notification: Notification) {
        // 1. 启动后端
        launchBackend()

        // 2. 等待后端就绪
        DispatchQueue.global().async {
            self.waitForBackend()
            DispatchQueue.main.async {
                self.openBrowser()
            }
        }

        // 3. 创建状态栏图标
        createStatusItem()

        // 4. 初始化 Sparkle 自动更新
        #if canImport(Sparkle)
        updaterController = SPUStandardUpdaterController(
            startingUpdater: true,
            updaterDelegate: nil,
            userDriverDelegate: nil
        )
        #endif
    }

    func launchBackend() {
        let bundlePath = Bundle.main.bundlePath
        let backendPath = bundlePath + "/Contents/Resources/backend/stock-helper-server"
        let dataDir = NSHomeDirectory() + "/Library/Application Support/Stock Helper"

        // 确保数据目录存在
        let fm = FileManager.default
        try? fm.createDirectory(atPath: dataDir, withIntermediateDirectories: true)

        backendProcess = Process()
        backendProcess?.executableURL = URL(fileURLWithPath: backendPath)
        backendProcess?.arguments = []
        var env = ProcessInfo.processInfo.environment
        env["STOCK_DATA_DIR"] = dataDir
        backendProcess?.environment = env

        do {
            try backendProcess?.run()
        } catch {
            let alert = NSAlert()
            alert.messageText = "启动失败"
            alert.informativeText = "无法启动后端服务: \(error.localizedDescription)"
            alert.runModal()
            NSApp.terminate(nil)
        }
    }

    func waitForBackend() {
        let baseURL = "http://127.0.0.1:8765"
        // 先获取会话令牌
        guard let sessionURL = URL(string: "\(baseURL)/api/session") else { return }
        for _ in 0..<30 {
            let semaphore = DispatchSemaphore(value: 0)
            var token: String?

            let task = URLSession.shared.dataTask(with: sessionURL) { data, response, _ in
                if let r = response as? HTTPURLResponse, r.statusCode == 200,
                   let data = data,
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let t = json["token"] as? String {
                    token = t
                }
                semaphore.signal()
            }
            task.resume()
            semaphore.wait()

            if let token = token {
                // 用令牌检查健康
                guard let healthURL = URL(string: "\(baseURL)/api/health") else { return }
                var healthRequest = URLRequest(url: healthURL)
                healthRequest.setValue(token, forHTTPHeaderField: "X-Session-Token")
                healthRequest.setValue("127.0.0.1:8765", forHTTPHeaderField: "Host")

                let healthSem = DispatchSemaphore(value: 0)
                var success = false
                let healthTask = URLSession.shared.dataTask(with: healthRequest) { _, response, _ in
                    if let r = response as? HTTPURLResponse, r.statusCode == 200 {
                        success = true
                    }
                    healthSem.signal()
                }
                healthTask.resume()
                healthSem.wait()

                if success { return }
            }
            Thread.sleep(forTimeInterval: 1.0)
        }
        // 30秒后仍未就绪，也尝试打开浏览器
        print("后端健康检查超时，仍尝试打开浏览器")
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
        menu.addItem(NSMenuItem(title: "检查更新", action: #selector(checkForUpdates), keyEquivalent: ""))
        menu.addItem(NSMenuItem.separator())
        menu.addItem(NSMenuItem(title: "退出股票分析助手", action: #selector(quitApp), keyEquivalent: "q"))
        statusBar?.menu = menu
    }

    @objc func openApp() {
        openBrowser()
    }

    @objc func checkForUpdates() {
        #if canImport(Sparkle)
        updaterController?.checkForUpdates(nil)
        #else
        let alert = NSAlert()
        alert.messageText = "自动更新不可用"
        alert.informativeText = "此版本未集成自动更新功能，请手动下载最新版本。"
        alert.runModal()
        #endif
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
