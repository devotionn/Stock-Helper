import Cocoa
import Darwin
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
        try? handle.close()
    } else {
        try? line.write(toFile: path, atomically: true, encoding: .utf8)
    }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    var backendProcess: Process?
    var backendLogHandle: FileHandle?
    var statusBar: NSStatusItem?
    var sessionToken: String?
    var instanceLockFD: Int32 = -1

    #if canImport(Sparkle)
    var updaterController: SPUStandardUpdaterController?
    #endif

    var dataDir: String {
        NSHomeDirectory() + "/Library/Application Support/Stock Helper"
    }

    var logDir: String {
        dataDir + "/logs"
    }

    var launcherLogPath: String {
        logDir + "/launcher.log"
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        ensureRuntimeDirectories()

        guard acquireInstanceLock() else {
            appendLog("检测到另一个启动器实例", toFile: launcherLogPath)
            if waitForExistingBackend(deadline: Date().addingTimeInterval(10)) {
                openBrowser()
            } else {
                let alert = NSAlert()
                alert.messageText = "股票分析助手正在启动"
                alert.informativeText = "另一个股票分析助手正在启动，请稍等片刻后再点击应用图标。"
                alert.runModal()
            }
            NSApp.terminate(nil)
            return
        }

        launchBackend()
        createStatusItem()

        #if canImport(Sparkle)
        updaterController = SPUStandardUpdaterController(
            startingUpdater: true,
            updaterDelegate: self,
            userDriverDelegate: nil
        )
        #endif

        DispatchQueue.global(qos: .userInitiated).async {
            let success = self.waitForBackend(deadline: Date().addingTimeInterval(30))
            DispatchQueue.main.async {
                if success {
                    self.openBrowser()
                } else {
                    self.showLaunchError()
                }
            }
        }
    }

    func ensureRuntimeDirectories() {
        let fm = FileManager.default
        try? fm.createDirectory(atPath: dataDir, withIntermediateDirectories: true)
        try? fm.createDirectory(atPath: logDir, withIntermediateDirectories: true)
    }

    func acquireInstanceLock() -> Bool {
        let lockPath = dataDir + "/stock-helper.lock"
        let fd = lockPath.withCString {
            Darwin.open($0, O_CREAT | O_RDWR, mode_t(S_IRUSR | S_IWUSR))
        }
        guard fd >= 0 else {
            appendLog("无法创建单实例锁文件", toFile: launcherLogPath)
            return false
        }
        guard flock(fd, LOCK_EX | LOCK_NB) == 0 else {
            Darwin.close(fd)
            return false
        }
        instanceLockFD = fd
        return true
    }

    func releaseInstanceLock() {
        guard instanceLockFD >= 0 else { return }
        flock(instanceLockFD, LOCK_UN)
        Darwin.close(instanceLockFD)
        instanceLockFD = -1
    }

    func launchBackend() {
        let backendPath = Bundle.main.bundlePath + "/Contents/Resources/backend/stock-helper-server"
        let logPath = logDir + "/backend.log"
        let fm = FileManager.default

        appendLog("启动股票分析助手...", toFile: launcherLogPath)
        rotateBackendLogs(fileManager: fm, currentLogPath: logPath)
        if !fm.fileExists(atPath: logPath) {
            fm.createFile(atPath: logPath, contents: nil)
        }

        backendProcess = Process()
        backendProcess?.executableURL = URL(fileURLWithPath: backendPath)
        var env = ProcessInfo.processInfo.environment
        env["STOCK_DATA_DIR"] = dataDir
        env["STOCK_APP_VERSION"] = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0.0"
        backendProcess?.environment = env

        backendLogHandle = FileHandle(forWritingAtPath: logPath)
        backendProcess?.standardOutput = backendLogHandle
        backendProcess?.standardError = backendLogHandle

        do {
            try backendProcess?.run()
            appendLog("后端进程已启动，PID=\(backendProcess?.processIdentifier ?? -1)", toFile: launcherLogPath)
        } catch {
            appendLog("后端启动失败: \(error.localizedDescription)", toFile: launcherLogPath)
            let alert = NSAlert()
            alert.messageText = "启动失败"
            alert.informativeText = "无法启动后端服务: \(error.localizedDescription)\n\n请重新打开应用；如仍失败，请联系维护人员。"
            alert.runModal()
            NSApp.terminate(nil)
        }
    }

    func rotateBackendLogs(fileManager fm: FileManager, currentLogPath: String) {
        guard fm.fileExists(atPath: currentLogPath) else { return }
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd-HHmmss-SSS"
        let backupPath = logDir + "/backend-\(formatter.string(from: Date())).log"
        try? fm.moveItem(atPath: currentLogPath, toPath: backupPath)

        guard let logs = try? fm.contentsOfDirectory(atPath: logDir) else { return }
        let oldLogs = logs
            .filter { $0.hasPrefix("backend-") && $0.hasSuffix(".log") }
            .sorted(by: >)
        for oldLog in oldLogs.dropFirst(5) {
            try? fm.removeItem(atPath: logDir + "/" + oldLog)
        }
    }

    func waitForExistingBackend(deadline: Date) -> Bool {
        while Date() < deadline {
            if fetchHealthIdentity()?.app == "stock-helper" {
                return true
            }
            Thread.sleep(forTimeInterval: 0.25)
        }
        return false
    }

    func waitForBackend(deadline: Date) -> Bool {
        while Date() < deadline {
            if sessionToken == nil {
                sessionToken = fetchSessionToken()
            }
            if sessionToken != nil, let health = fetchHealthIdentity(), health.app == "stock-helper" {
                appendLog("后端健康检查通过，版本=\(health.version)", toFile: launcherLogPath)
                return true
            }
            if let process = backendProcess, !process.isRunning {
                appendLog("后端进程提前退出，状态=\(process.terminationStatus)", toFile: launcherLogPath)
                return false
            }
            Thread.sleep(forTimeInterval: 0.25)
        }
        appendLog("后端健康检查超时", toFile: launcherLogPath)
        return false
    }

    struct HealthResponse: Decodable {
        let status: String
        let app: String
        let version: String
        let instance_id: String
        let pid: Int32
    }

    func fetchSessionToken() -> String? {
        guard let url = URL(string: "http://127.0.0.1:8765/api/session") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 1.0
        guard let data = synchronousData(request: request).data,
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return nil }
        return json["token"] as? String
    }

    func fetchHealthIdentity() -> HealthResponse? {
        guard let url = URL(string: "http://127.0.0.1:8765/api/health") else { return nil }
        var request = URLRequest(url: url)
        request.timeoutInterval = 1.0
        request.setValue("127.0.0.1:8765", forHTTPHeaderField: "Host")
        if let token = sessionToken {
            request.setValue(token, forHTTPHeaderField: "X-Session-Token")
        }
        let result = synchronousData(request: request)
        guard result.statusCode == 200, let data = result.data else { return nil }
        return try? JSONDecoder().decode(HealthResponse.self, from: data)
    }

    func synchronousData(request: URLRequest) -> (data: Data?, statusCode: Int?) {
        let semaphore = DispatchSemaphore(value: 0)
        var responseData: Data?
        var statusCode: Int?
        let task = URLSession.shared.dataTask(with: request) { data, response, _ in
            responseData = data
            statusCode = (response as? HTTPURLResponse)?.statusCode
            semaphore.signal()
        }
        task.resume()
        let timeout = max(1.0, request.timeoutInterval + 0.5)
        if semaphore.wait(timeout: .now() + timeout) == .timedOut {
            task.cancel()
            return (nil, nil)
        }
        return (responseData, statusCode)
    }

    func createUpdateBackup() -> Bool {
        guard let token = sessionToken,
              let url = URL(string: "http://127.0.0.1:8765/api/backup")
        else { return false }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.timeoutInterval = 120.0
        request.setValue("127.0.0.1:8765", forHTTPHeaderField: "Host")
        request.setValue(token, forHTTPHeaderField: "X-Session-Token")
        let result = synchronousData(request: request)
        guard result.statusCode == 200, let data = result.data,
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return false }
        return json["success"] as? Bool == true
    }

    func showLaunchError() {
        let alert = NSAlert()
        alert.messageText = "股票分析助手启动失败"
        alert.informativeText = "后端服务未能正常启动。\n\n请重新打开应用；如仍失败，请点击菜单栏图标选择「导出诊断信息」并发送给维护人员。"
        alert.addButton(withTitle: "确定")
        alert.runModal()
    }

    func openBrowser() {
        guard fetchHealthIdentity()?.app == "stock-helper" else { return }
        if let url = URL(string: "http://127.0.0.1:8765") {
            NSWorkspace.shared.open(url)
        }
    }

    func createStatusItem() {
        statusBar = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        statusBar?.button?.title = "📈"
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
        alert.informativeText = "此版本未集成自动更新功能，请联系维护人员。"
        alert.runModal()
        #endif
    }

    @objc func exportDiagnostics() {
        let diagPath = dataDir + "/diagnostic_report.txt"
        let timestamp = DateFormatter.localizedString(from: Date(), dateStyle: .full, timeStyle: .full)
        let appVersion = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "未知"
        var report = "=== 股票分析助手诊断报告 ===\n"
        report += "时间: \(timestamp)\n版本: \(appVersion)\n"
        report += "应用路径: \(Bundle.main.bundlePath)\n数据目录: \(dataDir)\n\n"
        if let process = backendProcess {
            report += "后端进程PID: \(process.processIdentifier)\n后端运行中: \(process.isRunning)\n"
        } else {
            report += "后端进程: 未创建\n"
        }
        report += "\n=== launcher.log ===\n"
        report += (try? String(contentsOfFile: launcherLogPath, encoding: .utf8)) ?? "(无日志)\n"
        report += "\n=== backend.log (最后100行) ===\n"
        if let content = try? String(contentsOfFile: logDir + "/backend.log", encoding: .utf8) {
            let lines = content.components(separatedBy: "\n")
            report += lines.suffix(100).joined(separator: "\n")
        } else {
            report += "(无日志)\n"
        }
        try? report.write(toFile: diagPath, atomically: true, encoding: .utf8)
        NSWorkspace.shared.selectFile(diagPath, inFileViewerRootedAtPath: dataDir)
    }

    @objc func quitApp() {
        shutdownBackend()
        NSApp.terminate(nil)
    }

    func shutdownBackend() {
        guard let process = backendProcess, process.isRunning else {
            try? backendLogHandle?.close()
            backendLogHandle = nil
            return
        }
        process.terminate()
        let deadline = Date().addingTimeInterval(5.0)
        while process.isRunning && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.1)
        }
        if process.isRunning {
            kill(process.processIdentifier, SIGKILL)
            process.waitUntilExit()
        }
        try? backendLogHandle?.close()
        backendLogHandle = nil
        appendLog("后端进程已停止，PID=\(process.processIdentifier)", toFile: launcherLogPath)
    }

    func applicationWillTerminate(_ notification: Notification) {
        shutdownBackend()
        releaseInstanceLock()
    }
}

#if canImport(Sparkle)
extension AppDelegate: SPUUpdaterDelegate {
    func updater(
        _ updater: SPUUpdater,
        shouldPostponeRelaunchForUpdate item: SUAppcastItem,
        untilInvokingBlock installHandler: @escaping () -> Void
    ) -> Bool {
        appendLog("准备安装更新 \(item.displayVersionString)，先创建数据备份", toFile: launcherLogPath)
        DispatchQueue.global(qos: .userInitiated).async {
            let backupSucceeded = self.createUpdateBackup()
            DispatchQueue.main.async {
                guard backupSucceeded else {
                    appendLog("更新前备份失败，已阻止本次更新", toFile: self.launcherLogPath)
                    let alert = NSAlert()
                    alert.messageText = "更新暂未安装"
                    alert.informativeText = "更新前备份失败。您的资料没有被修改，请检查备份位置或磁盘空间后再次更新。"
                    alert.runModal()
                    return
                }
                appendLog("更新前备份成功，开始安装更新", toFile: self.launcherLogPath)
                self.shutdownBackend()
                installHandler()
            }
        }
        return true
    }
}
#endif

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
