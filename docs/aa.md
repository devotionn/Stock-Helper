我继续检查了最新提交 **`5d3398b3`——“完成审查报告第五轮全部修复”**。这轮进步很大，`package-lock.json`、Sparkle公钥、签名流程、正式Release、macOS 15 Runner、日志和诊断功能都进行了实质修改。

# 最新结论

**核心业务代码可以视为基本开发完成，但macOS正式发布链路仍有一个P0阻断问题，以及几个必须在首次构建前修复的问题。**

| 部分                     |                当前判断 |
| ------------------------ | ----------------------: |
| 12格录入、图片、组合分析 |                 90%—95% |
| Windows端开发            |                     95% |
| 数据库、备份、安全       |                 85%—90% |
| macOS ARM64打包代码      |                 80%—85% |
| Sparkle自动更新代码      |                 70%—75% |
| Developer ID签名、公证   | 代码约60%，实际尚未验证 |
| 可交付李叔长期使用       |                尚未达到 |

现在已经不适合继续反复“补业务功能”，而应该进入：

> **构建—失败—修复—真机验收阶段。**

---

# 这轮已经修好的内容

## 1. `package-lock.json`已经同步

之前`package.json`与锁文件不一致，会导致`npm ci`直接失败。现在锁文件已经包含：

```text
eslint
eslint-plugin-vue
vue-eslint-parser
```

这个构建阻断问题已解决。

## 2. Sparkle公钥支持动态写入

`Info.plist`不再固定写“待生成”，而是读取：

```text
SPARKLE_PUBLIC_KEY
```

并写入：

```xml
<key>SUPublicEDKey</key>
<string>${SPARKLE_PUBLIC_KEY}</string>
```

方向正确。

## 3. EdDSA私钥传递方式正确了

现在使用：

```bash
--ed-key-file -
```

通过标准输入传递私钥，不再把私钥直接放在命令行参数中。Sparkle官方也建议CI环境通过标准输入使用密钥。 ([sparkle-project.org][1])

## 4. 正式版本压缩顺序基本正确

现在是：

```text
构建应用
→ Developer ID签名
→ Apple公证
→ stapler写入票据
→ 生成最终ZIP
→ Sparkle签名
→ 生成appcast
→ 发布Release
```

这个顺序比之前先压缩再签名正确得多。

## 5. macOS Runner选择正确

当前使用：

```yaml
runs-on: macos-15
```

GitHub当前的标准`macos-15`运行器是Apple Silicon ARM64环境，适合构建李叔的Mac mini M4版本。([GitHub Docs][2])

## 6. Swift启动器更接近真实可用

现在已经具备：

- 启动FastAPI后端；

- 写入macOS标准数据目录；

- 检查服务是否正常；

- 失败时显示中文错误；

- 后端日志落盘；

- 菜单栏图标；

- 打开系统；

- 检查更新；

- 导出诊断信息；

- 退出时停止后端。

---

# 当前最严重的P0问题

## GitHub Runner里没有导入Developer ID证书

这是目前最大的实际阻断点。

Release工作流只向构建脚本传入了：

```text
MACOS_CERTIFICATE_NAME
```

构建脚本随后直接执行：

```bash
codesign --sign "$DEVELOPER_ID"
```

但是，GitHub托管的macOS Runner是每次新建的临时机器，它不会自动拥有你的Developer ID证书和私钥。GitHub官方流程要求：

1. 把`.p12`证书转为Base64；
2. 保存到GitHub Secret；
3. 创建临时Keychain；
4. 将证书导入Keychain；
5. 配置Keychain访问权限；
6. 构建完成后删除临时Keychain。([GitHub Docs][3])

### 当前可能出现两种结果

**没有设置`MACOS_CERTIFICATE_NAME`：**

```text
跳过签名
→ 可能也跳过公证
→ 仍然创建正式Release
```

**设置了证书名称，但没有导入证书：**

```text
codesign
→ 找不到签名身份
→ 工作流失败
```

因此，现在的Release工作流还不能真正完成Developer ID签名。

## 需要增加的Secrets

建议至少配置：

```text
MACOS_CERTIFICATE_P12_BASE64
MACOS_CERTIFICATE_PASSWORD
KEYCHAIN_PASSWORD
MACOS_CERTIFICATE_NAME

APPLE_ID
APPLE_TEAM_ID
APPLE_APP_PASSWORD

SPARKLE_PUBLIC_KEY
SPARKLE_PRIVATE_KEY
```

然后在构建前增加“导入证书”步骤。

---

# 第二个问题：正式发布缺少Secrets预检查

虽然Release标记为正式发布，但构建脚本仍然允许这些变量为空：

```text
SPARKLE_PUBLIC_KEY
MACOS_CERTIFICATE_NAME
APPLE_ID
APPLE_TEAM_ID
APPLE_APP_PASSWORD
```

例如公钥为空时，应用仍会写出：

```xml
<key>SUPublicEDKey</key>
<string></string>
```

证书为空时跳过签名，公证凭据不完整时跳过公证。

但工作流最后仍会创建一个：

```yaml
draft: false
prerelease: false
```

的正式Release。

## 应增加Release预检

正式发布时，任何一项缺失都必须失败：

```bash
required_vars=(
  SPARKLE_PUBLIC_KEY
  SPARKLE_PRIVATE_KEY
  MACOS_CERTIFICATE_NAME
  MACOS_CERTIFICATE_P12_BASE64
  MACOS_CERTIFICATE_PASSWORD
  APPLE_ID
  APPLE_TEAM_ID
  APPLE_APP_PASSWORD
)

for var in "${required_vars[@]}"; do
  if [ -z "${!var}" ]; then
    echo "缺少必要配置：$var"
    exit 1
  fi
done
```

不能默默发布一个未签名或无法自动更新的正式版本。

---

# 第三个问题：签名注入的`sed`命令不安全

当前代码：

```bash
sed -i '' \
  "s/sparkle:edSignature=\"\"/sparkle:edSignature=\"$SIGNATURE\"/" \
  dist/appcast.xml
```

这里使用`/`作为`sed`分隔符。

但Sparkle EdDSA签名是Base64字符串，可能包含：

```text
/
+
=
```

Sparkle官方给出的签名示例中就包含`/`。([sparkle-project.org][4])

一旦本次生成的签名中包含`/`，这个`sed`表达式就可能解析失败。

## 最低限度修正

改用Base64不会包含的分隔符：

```bash
sed -i '' \
  "s|sparkle:edSignature=\"\"|sparkle:edSignature=\"$SIGNATURE\"|" \
  dist/appcast.xml
```

## 更佳做法

不要先生成空签名再用`sed`修改，而是让：

```text
generate_appcast.py
```

直接接收签名参数。

最好进一步使用Sparkle官方的`generate_appcast`工具。Sparkle官方明确推荐使用它自动生成签名和appcast，而不是手工拼接XML。([sparkle-project.org][5])

---

# 第四个问题：当前签名、公证是“可选步骤”

虽然注释写着正式发布，但代码逻辑是：

```bash
if [ -n "$DEVELOPER_ID" ]; then
    执行签名
fi
```

以及：

```bash
if Apple凭据完整; then
    执行公证
fi
```

正式Release不应该采用“有就签、没有就算了”的设计。

建议区分：

```text
开发构建：
允许不签名、不公证

正式Release：
必须签名、必须公证、必须Sparkle签名
任何一步失败立即终止
```

例如增加：

```text
RELEASE_MODE=1
```

在正式模式下强制检查全部配置和结果。

---

# 第五个问题：签名嵌套组件还需要真实公证验证

当前签名逻辑包括：

```text
Sparkle.framework
后端主二进制
Swift启动器
整个.app
```

但PyInstaller的`onedir`目录中还可能包含：

- Python动态库；
- 第三方`.dylib`；
- 扩展模块；
- Keyring相关组件；
- Pillow相关二进制；
- Sparkle内部Helper/XPC组件。

目前主要依赖：

```bash
codesign --deep
```

递归处理。

这不一定必然失败，但**必须通过真实的`notarytool`返回结果才能确认**。Sparkle官方也建议应用本体使用Developer ID签名并完成Apple公证。([sparkle-project.org][5])

首次公证失败后，需要根据Apple返回的JSON日志，定位具体哪个嵌套Mach-O文件未正确签名，再改成由内向外逐个签名。

---

# Swift启动器还有几个P1问题

## 1. `launcher.log`每次写入都在覆盖

当前启动时写：

```swift
"启动股票分析助手..."
```

后端启动后又写：

```swift
"后端进程已启动"
```

但两次都使用：

```swift
write(toFile:atomically:true)
```

第二次会覆盖第一次，并不是追加。

应写一个追加日志函数，否则诊断文件里往往只能看到最后一条。

## 2. 后端日志每次启动都会被清空

```swift
logFile.truncateFile(atOffset: 0)
```

如果李叔第一次启动失败，第二次重新打开时旧错误日志就会被清除。

建议采用：

```text
backend-current.log
backend-20260730-013100.log
```

或者保留最近5份日志。

## 3. 后端检查请求没有明确超时

当前使用信号量等待`URLSession`完成：

```swift
semaphore.wait()
```

但请求没有设置约1秒的`timeoutInterval`。

正常情况下localhost连接失败会很快返回，但如果连接建立后无响应，等待时间可能超过预期，所谓“最多30秒”并不能严格保证。

## 4. “导出诊断信息”只打开文件夹

诊断报告写到：

```text
diagnostic_report.txt
```

但最后调用：

```swift
selectFile(nil, inFileViewerRootedAtPath: dataDir)
```

Finder只会打开数据目录，不会自动选中诊断文件。

应改成选中：

```text
diagPath
```

让李叔一眼看到应该发送哪个文件。

---

# 工程流程还可以简化

Tag推送后，现在会同时执行：

- `ci.yml`中的后端测试、前端检查、macOS构建；
- `release.yml`中的前端构建、后端测试、macOS构建和发布。

并且`ci.yml`先执行一次PyInstaller，然后`build_app.sh`内部又执行一次PyInstaller。

不会直接造成错误，但会：

- 重复消耗macOS Runner时间；
- 延长发布；
- 产生两套构建结果；
- 增加排查难度。

建议Release只依赖一条经过测试的产物链，不要重复构建两次。

---

# 版本信息仍未完全统一

应用的`Info.plist`版本会根据Tag变化，这已经正确。

但备份文件中的：

```json
"app_version": "1.0.0"
```

仍然写死。

例如程序升级到`1.2.0`后，备份manifest仍然声称来自`1.0.0`。

建议建立一个统一版本来源：

```text
STOCK_APP_VERSION
```

并同时用于：

- Info.plist；
- FastAPI版本；
- 备份manifest；
- 诊断信息；
- 日志；
- 更新记录。

---

# 现在能不能说“开发好了”

可以说：

> **业务功能已经开发完成，macOS构建和更新代码也基本齐全。**

不能说：

> **已经完成正式交付。**

因为目前还缺少最关键的客观证据：

```text
GitHub Actions成功构建
Developer ID签名成功
Apple公证成功
Sparkle签名成功
M芯片Mac成功启动
v0.1.0成功升级到v0.1.1
用户数据全部保留
```

代码审查只能证明“写了这些逻辑”，不能证明GitHub Runner、Apple公证服务和真实Mac都已经接受这套逻辑。

# 现在应立即做的事情

先不要继续增加功能，按以下顺序验收：

```text
1. 导入Developer ID证书到GitHub Runner
2. 增加全部Release Secrets预检
3. 修复sed签名注入
4. 推送测试标签 v0.1.0
5. 检查GitHub Actions是否全部绿色
6. 下载最终ZIP
7. 在M芯片Mac执行：
   codesign --verify
   spctl --assess
   stapler validate
8. 双击启动应用
9. 测试Keychain、图片上传、AI分析、备份恢复
10. 发布v0.1.1
11. 用v0.1.0执行Sparkle自动更新
12. 确认数据库、图片和历史记录完全保留
```

完成第12步以后，才可以认定：

> **股票分析助手已经具备正式交付给李叔的条件。**

[1]: https://sparkle-project.org/documentation/security-and-reliability/?utm_source=chatgpt.com "Update Improvements - Sparkle: open source software update framework for macOS"
[2]: https://docs.github.com/en/actions/reference/runners/github-hosted-runners?utm_source=chatgpt.com "GitHub-hosted runners reference - GitHub Docs"
[3]: https://docs.github.com/en/actions/how-tos/deploy/deploy-to-third-party-platforms/sign-xcode-applications?source=post_page-----51088aa5852c---------------------------------------&utm_source=chatgpt.com "Installing an Apple certificate on macOS runners for Xcode development - GitHub Docs"
[4]: https://sparkle-project.org/documentation/publishing/?utm_source=chatgpt.com "Publishing an update - Sparkle: open source software update framework for macOS"
[5]: https://sparkle-project.org/documentation/?utm_source=chatgpt.com "Documentation - Sparkle: open source software update framework for macOS"
