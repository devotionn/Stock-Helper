// Updater.swift - Sparkle 自动更新配置说明
//
// 此文件提供 Sparkle 集成的关键配置信息。
// 实际的 SPUStandardUpdaterController 初始化在 main.swift 中完成。
//
// Info.plist 中的 Sparkle 配置（由 build_app.sh 注入）:
//   SUFeedURL        - appcast.xml 的 URL
//   SUPublicEDKey    - EdDSA 公钥（验证更新包签名）
//   SUEnableAutomaticChecks - 自动检查开关
//   SUScheduledCheckInterval - 检查间隔（秒）
//
// EdDSA 密钥对生成:
//   1. 下载 Sparkle.framework
//   2. 运行 ./bin/generate_keys -p 生成密钥对
//   3. 公钥写入 Info.plist 的 SUPublicEDKey
//   4. 私钥保存到 GitHub Actions Secrets: SPARKLE_PRIVATE_KEY
//   5. 发布时用 sign_update 对 ZIP 签名:
//      ./bin/sign_update StockHelper-1.0.1.zip -p <private_key>
//   6. 输出格式: "edSignature:..." 长度:..."
//   7. 将签名值写入 appcast.xml 的 sparkle:edSignature
//
// 本文件目前不需要包含可执行代码。
// Sparkle 的更新流程由 main.swift 中的 SPUStandardUpdaterController 管理。
