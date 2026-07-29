import Cocoa
import Foundation

#if canImport(Sparkle)
import Sparkle
#endif

func appendLog(_ message: String, toFile path: String) {
    let timestamp = DateFormatter.localizedString(from: Date(), dateStyle: .short, timeStyle: .medium)
    let line = "[\(timestamp)] \(message)\n"
    if let handle = FileHandle(forWritingAtPath: path) {
        handle.seekToEndOfFile()
        if let data = line.data(using: .utf8) {
            handle.write(data)
        }
        handle.closeFile()
    } else {
        // 文件不存在，创建
        try? line.write(toFile: path, atomically: true, encoding: .utf8)
    }
}

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
            let success = self.waitForBackend()
            DispatchQueue.main.async {
                if success {
                    self.openBrowser()
                } else {
                    self.showLaunchError()
                }
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
        let logDir = dataDir + "/logs"

        // 确保目录存在
        let fm = FileManager.default
        try? fm.createDirectory(atPath: dataDir, withIntermediateDirectories: true)
        try? fm.createDirectory(atPath: logDir, withIntermediateDirectories: true)

        // 日志文件
        let logPath = logDir + "/backend.log"
        let launcherLogPath = logDir + "/launcher.log"

        // 记录启动器日志
        appendLog("启动股票分析助手...", toFile: launcherLogPath)

        backendProcess = Process()
        backendProcess?.executableURL = URL(fileURLWithPath: backendPath)
        backendProcess?.arguments = []
        var env = ProcessInfo.processInfo.environment
        env["STOCK_DATA_DIR"] = dataDir
        backendProcess?.environment = env

        // 保留旧日志：将旧的 backend.log 重命名为带时间戳的备份，仅保留最近5份
        if fm.fileExists(atPath: logPath) {
            let oldTimestamp = DateFormatter()
            oldTimestamp.dateFormat = "yyyyMMdd-HHmmss"
            let backupPath = logDir + "/backend-\(oldTimestamp.string(from: Date())).log"
            try? fm.moveItem(atPath: logPath, toPath: backupPath)

            // 清理超过5份的旧日志
            if let logs = try? fm.contentsOfDirectory(atPath: logDir) {
                let oldLogs = logs.filter { $0.hasPrefix("backend-") && $0.hasSuffix(".log") }
                    .sorted().reversed()
                for oldLog in oldLogs.dropFirst(4) {
                    try? fm.removeItem(atPath: logDir + "/" + oldLog)
                }
            }
        }

        // 确保日志文件存在，以便 FileHandle 可打开
        if !fm.fileExists(atPath: logPath) {
            fm.createFile(atPath: logPath, contents: nil)
        }

        // 重定向 stdout/stderr 到日志文件
        let logFile = FileHandle(forWritingAtPath: logPath)
        if let logFile = logFile {
            backendProcess?.standardOutput = logFile
            backendProcess?.standardError = logFile
        }

        do {
            try backendProcess?.run()
            appendLog("后端进程已启动", toFile: launcherLogPath)
        } catch {
            appendLog("后端启动失败: \(error.localizedDescription)", toFile: launcherLogPath)
            let alert = NSAlert()
            alert.messageText = "启动失败"
            alert.informativeText = "无法启动后端服务: \(error.localizedDescription)\n\n请重新打开应用；如仍失败，请联系维护人员。"
            alert.runModal()
            NSApp.terminate(nil)
        }
    }

    func waitForBackend() -> Bool {
        let baseURL = "http://127.0.0.1:8765"
        guard let sessionURL = URL(string: "\(baseURL)/api/session") else { return false }

        for _ in 0..<30 {
            let semaphore = DispatchSemaphore(value: 0)
            var token: String?

            var sessionRequest = URLRequest(url: sessionURL)
            sessionRequest.timeoutInterval = 3.0
            let task = URLSession.shared.dataTask(with: sessionRequest) { data, response, _ in
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
                // /api/health 现在免令牌，但仍然带上令牌以防万一
                guard let healthURL = URL(string: "\(baseURL)/api/health") else { return false }
                var healthRequest = URLRequest(url: healthURL)
                healthRequest.setValue(token, forHTTPHeaderField: "X-Session-Token")
                healthRequest.setValue("127.0.0.1:8765", forHTTPHeaderField: "Host")
                healthRequest.timeoutInterval = 3.0

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

                if success { return true }
            }
            Thread.sleep(forTimeInterval: 1.0)
        }
        return false
    }

    func showLaunchError() {
        let alert = NSAlert()
        alert.messageText = "股票分析助手启动失败"
        alert.informativeText = "后端服务未能正常启动。\n\n请重新打开应用；如仍失败，请点击菜单栏图标选择「导出诊断信息」并发送给维护人员。"
        alert.addButton(withTitle: "确定")
        alert.runModal()
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
        menu.addItem(NSMenuItem(title: "导出诊断信息", action: #selector(exportDiagnostics), keyEquivalent: ""))
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

    @objc func exportDiagnostics() {
        let dataDir = NSHomeDirectory() + "/Library/Application Support/Stock Helper"
        let logDir = dataDir + "/logs"

        // 创建诊断信息文件
        let diagPath = dataDir + "/diagnostic_report.txt"
        let timestamp = DateFormatter.localizedString(from: Date(), dateStyle: .full, timeStyle: .full)

        var report = "=== 股票分析助手诊断报告 ===\n"
        report += "时间: \(timestamp)\n"
        report += "应用路径: \(Bundle.main.bundlePath)\n"
        report += "数据目录: \(dataDir)\n\n"

        // 后端进程状态
        if let p = backendProcess {
            report += "后端进程PID: \(p.processIdentifier)\n"
            report += "后端运行中: \(p.isRunning)\n"
        } else {
            report += "后端进程: 未创建\n"
        }

        // 日志文件
        report += "\n=== launcher.log ===\n"
        if let content = try? String(contentsOfFile: logDir + "/launcher.log", encoding: .utf8) {
            report += content
        } else {
            report += "(无日志)\n"
        }

        report += "\n=== backend.log (最后100行) ===\n"
        if let content = try? String(contentsOfFile: logDir + "/backend.log", encoding: .utf8) {
            let lines = content.components(separatedBy: "\n")
            let start = max(0, lines.count - 100)
            report += lines[start...].joined(separator: "\n")
        } else {
            report += "(无日志)\n"
        }

        try? report.write(toFile: diagPath, atomically: true, encoding: .utf8)

        // 在 Finder 中显示
        NSWorkspace.shared.selectFile(diagPath, inFileViewerRootedAtPath: dataDir)
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
