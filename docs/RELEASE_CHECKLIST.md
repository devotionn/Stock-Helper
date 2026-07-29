# 股票分析助手：正式发布与真机验收清单

本文档用于将 `main` 分支构建成可交付给李叔 Mac mini M4 的正式版本。任何密钥、证书密码或 Apple 专用密码都不得提交到仓库，也不要通过聊天工具发送。

## 1. 发布前一次性准备

### 1.1 Apple 开发者材料

准备以下内容：

- Developer ID Application 证书及私钥，导出为 `.p12`；
- `.p12` 导出密码；
- Apple ID；
- Apple Developer Team ID；
- Apple ID 的 App 专用密码；
- 证书完整名称，例如 `Developer ID Application: Example Name (TEAMID)`。

将 `.p12` 转为单行 Base64：

```bash
base64 -i DeveloperID.p12 | tr -d '\n' > DeveloperID.p12.base64.txt
```

### 1.2 Sparkle EdDSA 密钥

在可信任的 M 系列 Mac 上下载项目固定使用的 Sparkle 版本，然后运行：

```bash
./bin/generate_keys -x sparkle_private_key.txt
```

工具会输出用于 `SUPublicEDKey` 的公钥，并把私钥导出到指定文件。私钥文件应离线备份，禁止提交到 GitHub。

### 1.3 GitHub Actions Secrets

在仓库的 `Settings → Secrets and variables → Actions` 中配置：

| Secret 名称 | 内容 |
|---|---|
| `SPARKLE_PUBLIC_KEY` | Sparkle 输出的 Base64 公钥 |
| `SPARKLE_PRIVATE_KEY` | `sparkle_private_key.txt` 的完整内容 |
| `MACOS_CERTIFICATE_P12_BASE64` | `.p12` 的单行 Base64 |
| `MACOS_CERTIFICATE_PASSWORD` | `.p12` 导出密码 |
| `MACOS_CERTIFICATE_NAME` | Developer ID Application 证书完整名称 |
| `APPLE_ID` | 用于公证的 Apple ID |
| `APPLE_TEAM_ID` | Apple Developer Team ID |
| `APPLE_APP_PASSWORD` | Apple ID App 专用密码 |

配置完成后，不要在日志、Issue、PR、README 或聊天中粘贴这些值。

## 2. 发布 v0.1.0

确认 `main` CI 全绿后创建标签：

```bash
git checkout main
git pull --ff-only
git tag v0.1.0
git push origin v0.1.0
```

Release 工作流必须全部通过以下阶段：

1. 前端安装、ESLint 和生产构建；
2. 后端 Ruff 与 pytest；
3. Secrets 完整性检查；
4. Developer ID 证书导入及身份验证；
5. PyInstaller arm64 打包；
6. Sparkle 官方资产 digest 校验；
7. Swift 启动器与 Sparkle 链接；
8. PyInstaller 内部 Mach-O、Sparkle Helper、启动器和应用签名；
9. Apple 公证、staple 和 Gatekeeper 验证；
10. 最终包冒烟测试，包括前端、SQLite、模块写入、Keychain 和端口释放；
11. Sparkle EdDSA 更新包签名及 appcast XML 验证；
12. 正式 GitHub Release 发布。

任意步骤失败都不得手工上传未验证产物冒充正式版本。

## 3. M 系列 Mac 首次安装验收

在测试 Mac 上执行：

```bash
codesign --verify --deep --strict --verbose=2 "/Applications/股票分析助手.app"
spctl --assess --type execute --verbose=2 "/Applications/股票分析助手.app"
xcrun stapler validate "/Applications/股票分析助手.app"
```

然后按顺序验证：

- 从 ZIP 解压并拖入“应用程序”；
- 双击后只打开一个浏览器标签页；
- 菜单栏出现股票图标；
- 连续双击应用不会产生第二个后端实例；
- 12个模块均能进入；
- 输入文字后自动保存，返回再进入内容仍存在；
- 上传、粘贴、预览、排序和删除图片正常；
- 配置 AI 密钥后，SQLite 中不存在明文密钥，macOS Keychain 中存在对应项目；
- 自定义组合顺序保持不变；
- 多模态分析、历史记录、AI复盘和操作建议正常；
- 一键备份生成 `.shbackup`；
- 恢复测试使用专门测试数据，不直接拿唯一生产数据冒险；
- “导出诊断信息”能够在 Finder 中选中报告；
- 从菜单退出后 8765 端口释放；
- 重启 Mac 后再次启动正常。

## 4. 自动更新验收：v0.1.0 → v0.1.1

在 v0.1.0 中预先录入可识别的测试资料：

- 至少3个模块的文字；
- 至少5张图片；
- 1个常用组合；
- 2条历史分析；
- 1条备注；
- 已配置的测试 AI 密钥。

发布仅改变版本号或增加一个明确可见的小改动的 `v0.1.1`。在 v0.1.0 菜单中点击“检查更新”，验证：

1. 能识别 v0.1.1；
2. 更新前自动生成完整备份；
3. 备份失败时更新会被阻止；
4. 更新包签名验证成功；
5. 应用安装并重新启动；
6. 应用版本显示为 v0.1.1；
7. 原有文字、图片、组合、历史、备注和 Keychain 密钥全部保留；
8. SQLite `PRAGMA integrity_check` 返回 `ok`；
9. 数据库迁移失败模拟测试不会覆盖旧数据库；
10. 旧后端不残留，8765 仅有一个监听进程。

只有该升级链路在真实 M 系列 Mac 上完整成功后，才可将版本交付给李叔。

## 5. 李叔电脑交付

正式安装时：

- 仅安装已签名、公证并通过上述验收的 Release ZIP；
- 应用放入 `/Applications`；
- 客户数据位于 `~/Library/Application Support/Stock Helper/`；
- 配置一个客户能识别的备份位置，优先使用外部磁盘或 iCloud Drive 中的专用目录；
- 完成一次现场或远程备份恢复演示；
- 告知李叔只使用菜单栏中的“打开”“检查更新”“导出诊断信息”“退出”四个入口；
- 不向李叔暴露终端、GitHub、Python、Node、证书和密钥概念。

## 6. 发布失败处理

- 构建失败：不创建 Release，修复后创建新标签，不覆盖已经公开的版本资产；
- 公证失败：读取 `notarytool` 日志，修复具体 Mach-O 签名问题；
- Sparkle签名失败：检查公私钥是否成对，不得关闭签名校验绕过；
- 更新后数据库启动失败：保留升级前备份和诊断日志，不反复启动覆盖现场；
- 客户端更新失败：旧版本继续可用，收集 `diagnostic_report.txt` 后再处理。
