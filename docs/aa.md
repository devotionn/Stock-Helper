我继续审查了最新提交 **`69e59dd1`——“完成审查报告第六轮全部修复”**。这轮把证书导入、Secrets预检、正式签名/公证强制检查、日志轮转和版本配置等继续补上了。

# 总体结论

现在可以判断为：

| 部分               |                 完成度 |
| ------------------ | ---------------------: |
| 核心业务功能       |                    95% |
| Windows端开发      |                    95% |
| macOS构建代码      |                85%—90% |
| 签名、公证流程代码 |                    80% |
| 自动更新流程代码   |                    80% |
| 真正可交付状态     | 仍需首次构建和真机验收 |

**已经非常接近第一次正式构建，但仍有3个P0级问题需要修正。**

---

# 这轮确认修好的内容

Release工作流现在已经增加：

- 8项Secrets预检；
- 临时Keychain创建；
- Developer ID P12证书导入；
- `codesign`权限配置；
- 构建后清理Keychain；
- 缺少签名或公证配置时终止发布。

构建脚本现在也会在正式模式下强制要求Developer ID和Apple公证凭据，并在公证后执行`stapler`和`spctl`验证。

日志方面已经实现：

- `launcher.log`追加写入；

- `backend.log`历史轮转；

- 保留最近数份日志；

- 网络请求3秒超时；

- 导出诊断文件后在Finder中选中。

---

# P0-1：缺少本地HTTP的ATS配置

这是目前最容易造成“后端明明启动了，但应用仍提示启动失败”的问题。

Swift启动器使用`URLSession`访问：

```text
http://127.0.0.1:8765/api/session
http://127.0.0.1:8765/api/health
```

但是生成的`Info.plist`中没有：

```text
NSAppTransportSecurity
NSAllowsLocalNetworking
```

Apple当前文档说明，从macOS 14开始，ATS不再默认允许直接访问IP地址；要允许应用通过HTTP连接本机IP，应明确配置本地网络例外。([Apple Developer][1])

## 必须加入

```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsLocalNetworking</key>
    <true/>

    <key>NSExceptionDomains</key>
    <dict>
        <key>127.0.0.1</key>
        <dict>
            <key>NSExceptionAllowsInsecureHTTPLoads</key>
            <true/>
        </dict>
        <key>localhost</key>
        <dict>
            <key>NSExceptionAllowsInsecureHTTPLoads</key>
            <true/>
        </dict>
    </dict>
</dict>
```

否则在李叔的Mac mini M4上，Swift健康检查可能被ATS拦截，最终显示：

> 股票分析助手启动失败

但实际FastAPI后端可能已经正常运行。

---

# P0-2：Sparkle.framework的签名方式仍不符合官方最佳实践

当前脚本使用：

```bash
codesign --force --deep --strict \
  --sign "$DEVELOPER_ID" \
  --options runtime \
  "$APP_DIR/Contents/Frameworks/Sparkle.framework"
```

之后对整个应用再次使用`--deep`。

Sparkle官方明确说明，手动签名Sparkle时不建议使用`--deep`，因为Sparkle内部包含：

- `Installer.xpc`
- `Downloader.xpc`
- `Autoupdate`
- `Updater.app`

其中`Downloader.xpc`还需要保留特定entitlements。官方建议由内向外分别签名，并为Downloader使用`--preserve-metadata=entitlements`。([sparkle-project.org][2])

## 建议改成

```bash
SPARKLE="$APP_DIR/Contents/Frameworks/Sparkle.framework/Versions/B"

codesign -f -s "$DEVELOPER_ID" \
  -o runtime \
  "$SPARKLE/XPCServices/Installer.xpc"

codesign -f -s "$DEVELOPER_ID" \
  -o runtime \
  --preserve-metadata=entitlements \
  "$SPARKLE/XPCServices/Downloader.xpc"

codesign -f -s "$DEVELOPER_ID" \
  -o runtime \
  "$SPARKLE/Autoupdate"

codesign -f -s "$DEVELOPER_ID" \
  -o runtime \
  "$SPARKLE/Updater.app"

codesign -f -s "$DEVELOPER_ID" \
  -o runtime \
  "$APP_DIR/Contents/Frameworks/Sparkle.framework"
```

然后再签：

```text
PyInstaller内部动态库和扩展
→ 后端主程序
→ Swift启动器
→ 整个.app
```

Sparkle官方也推荐使用Xcode Archive/Export，因为它会正确处理内部Helper；当前项目不采用Xcode工程，因此手工签名必须严格按嵌套结构执行。([sparkle-project.org][3])

---

# P0-3：应用版本仍没有真正传给运行中的后端

后端新增了：

```python
app_version = os.environ.get("STOCK_APP_VERSION", "1.0.0")
```

备份manifest也读取：

```python
APP_VERSION = os.environ.get("STOCK_APP_VERSION", "1.0.0")
```

但Swift启动器启动后端时只传递了：

```swift
env["STOCK_DATA_DIR"] = dataDir
```

没有传递：

```text
STOCK_APP_VERSION
```

因此，即使发布的是`v1.2.0`，后端运行时仍然会默认认为自己是：

```text
1.0.0
```

备份manifest也仍然会写成：

```json
{
  "app_version": "1.0.0"
}
```

## Swift启动器应增加

```swift
let appVersion =
    Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String
    ?? "1.0.0"

env["STOCK_APP_VERSION"] = appVersion
```

然后FastAPI版本、诊断信息、备份manifest都统一使用这个版本。

---

# P1-1：没有单实例保护

当前每次打开应用都会直接执行：

```swift
launchBackend()
```

并尝试在固定端口`8765`启动服务。

假设李叔连续点击两次应用：

```text
第一个应用启动后端，占用8765
→ 第二个应用再次启动
→ 第二个后端因端口占用退出
→ 第二个启动器却可能连接到第一个后端
→ 两个菜单栏图标同时存在
```

退出第二个图标时，第一个后端仍可能继续运行。

应至少采用一种单实例机制：

- 启动前检查同Bundle ID应用是否已运行；
- 数据目录创建进程锁文件；
- 使用`flock`；
- 启动前检查8765端口，发现已有健康服务时只打开浏览器并退出第二实例；
- 在`Info.plist`中增加单实例限制作为补充。

---

# P1-2：退出时没有等待后端真正结束

当前退出逻辑只是：

```swift
backendProcess?.terminate()
NSApp.terminate(nil)
```

Sparkle更新时，旧应用退出后会替换`.app`。如果FastAPI子进程没有及时停止，可能出现：

```text
旧后端仍占用8765
→ 新版本应用启动
→ 新后端无法绑定端口
→ 新启动器连接到旧后端
```

建议实现：

```text
发送SIGTERM
→ 等待最多5秒
→ 若仍运行，执行interrupt或强制结束
→ 确认端口释放
→ 再退出主应用
```

这对自动更新非常关键。

---

# P1-3：证书导入命令还有兼容性细节

当前使用：

```bash
base64 --decode
```

解码P12证书。

Apple提供的macOS命令示例使用的是：

```bash
base64 -D
```

([Apple Developer][4])

建议改为：

```bash
printf '%s' "$MACOS_CERTIFICATE_P12_BASE64" \
  | base64 -D \
  > "$CERT_PATH"
```

同时在导入后增加：

```bash
security find-identity -v -p codesigning "$KEYCHAIN_PATH"
```

并检查`MACOS_CERTIFICATE_NAME`确实存在，避免等到`codesign`阶段才发现证书名称错误。

---

# P1-4：Secrets预检不应直接插入Shell脚本

当前预检把Secrets直接写入`run`脚本：

```yaml
"SPARKLE_PRIVATE_KEY=${{ secrets.SPARKLE_PRIVATE_KEY }}"
```

当Secret中存在换行、引号或Shell特殊字符时，脚本可能解析异常。

更稳妥的方式是：

```yaml
env:
  SPARKLE_PUBLIC_KEY: ${{ secrets.SPARKLE_PUBLIC_KEY }}
  SPARKLE_PRIVATE_KEY: ${{ secrets.SPARKLE_PRIVATE_KEY }}
  MACOS_CERTIFICATE_P12_BASE64: ${{ secrets.MACOS_CERTIFICATE_P12_BASE64 }}
```

然后Shell里只检查：

```bash
[ -n "${SPARKLE_PRIVATE_KEY:-}" ] || exit 1
```

---

# P1-5：缺少打包产物冒烟测试

当前Release流程执行了源码层面的pytest，然后直接：

```text
打包
→ 签名
→ 公证
→ 发布
```

但没有测试最终PyInstaller产物是否真的能够：

- 启动；
- 找到前端；
- 初始化SQLite；
- 加载Keyring；
- 返回`/api/health`；
- 正常退出。

建议在发布前执行：

```bash
dist/股票分析助手.app/Contents/Resources/backend/stock-helper-server &
PID=$!

for i in {1..30}; do
  curl -f http://127.0.0.1:8765/api/health && break
  sleep 1
done

kill "$PID"
wait "$PID" || true
```

正式版还应检查：

```bash
codesign --verify --deep --strict
spctl --assess --type execute
xcrun stapler validate
```

---

# 其他建议

构建脚本每次从网络下载Sparkle 2.6.4，但没有校验SHA-256。

建议固定版本的同时固定校验值：

```text
下载
→ SHA-256校验
→ 解压
→ 构建
```

Sparkle官方要求复制和压缩Framework时保留符号链接及可执行权限；当前使用`cp -R`和`ditto --keepParent`总体方向正确。([sparkle-project.org][3])

另外，`macos-15`目前确实对应GitHub托管的Apple Silicon ARM64运行器，与李叔的M4目标架构一致。([GitHub][5])

---

# 最终判断

这轮之后，已经可以明确说：

> **Windows端能够完成的主体开发工作已经基本完成，macOS发布流水线也接近成型。**

但在推送第一个正式Tag之前，至少要先修复：

```text
1. ATS本地HTTP配置
2. Sparkle嵌套组件正确签名
3. STOCK_APP_VERSION运行时传递
4. 单实例和后端进程退出
5. 最终.app冒烟测试
```

完成后再走：

```text
v0.1.0构建
→ GitHub Actions全绿
→ M芯片Mac首次安装
→ Keychain、图片、AI、备份测试
→ 发布v0.1.1
→ Sparkle自动更新
→ 确认所有数据保留
```

现在最大的价值不再是继续让代码生成器“再修一轮”，而是先解决上述几个确定问题，然后真正跑一次GitHub Actions和M系列Mac测试。

[1]: https://developer.apple.com/documentation/bundleresources/information-property-list/nsapptransportsecurity/nsallowslocalnetworking?changes=lat__5_8__8&utm_source=chatgpt.com "NSAllowsLocalNetworking | Apple Developer Documentation"
[2]: https://sparkle-project.org/documentation/sandboxing/?utm_source=chatgpt.com "Sandboxing with Sparkle - Sparkle: open source software update framework for macOS"
[3]: https://sparkle-project.org/documentation/?utm_source=chatgpt.com "Documentation - Sparkle: open source software update framework for macOS"
[4]: https://developer.apple.com/forums/thread/89764?utm_source=chatgpt.com "Swift SecPKCS12Import returns diff… | Apple Developer Forums"
[5]: https://github.com/actions/runner-images?utm_source=chatgpt.com "GitHub - actions/runner-images: GitHub Actions runner images · GitHub"
