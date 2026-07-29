// Sparkle 自动更新集成
// 需要在 Xcode 项目中链接 Sparkle.framework

import Cocoa
// import Sparkle  // 取消注释当 Sparkle.framework 集成后

class UpdaterController: NSObject {
    // SPUStandardUpdaterController 需要在 Xcode 中配置
    // 这里提供集成说明:
    //
    // 1. 在 Info.plist 中添加:
    //    SUFeedURL = https://github.com/devotionn/Stock-Helper/releases/latest/download/appcast.xml
    //    SUEnableAutomaticChecks = true
    //    SUScheduledCheckInterval = 86400 (每天检查一次)
    //
    // 2. 在 AppDelegate 中:
    //    let updaterController = SPUStandardUpdaterController(
    //        startingUpdater: true,
    //        updaterDelegate: nil,
    //        userDriverDelegate: nil
    //    )
    //
    // 3. 添加菜单项 "检查更新" -> updaterController.checkForUpdates(nil)
    //
    // 4. 生成 EdDSA 密钥对:
    //    ./bin/generate_keys -p
    //    将公钥写入 Info.plist 的 SUPublicEDKey
    //    私钥用于 sign_update 工具签名更新包
}
