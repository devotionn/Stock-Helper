我重新检查了最新提交 **`b50155bb`——“完成审查报告第四轮全部修复”**。这轮确实把 Swift 启动器、Sparkle 调用、健康检查、ESLint 和密钥迁移补进去了。

# 结论

**业务程序基本开发完成，但 macOS 正式发布和自动更新链路仍没有真正跑通。**

当前状态更准确地说是：

| 部分                         | 状态     |
| ---------------------------- | -------- |
| 12格录入、图片、组合、AI分析 | 基本完成 |
| Windows本地开发              | 基本完成 |
| macOS arm64代码准备          | 基本完成 |
| 生成内部测试版 `.app`        | 接近可行 |
| Sparkle自动更新              | 尚未打通 |
| Developer ID签名、公证       | 未实现   |
| 可直接交付李叔长期使用       | 暂时不行 |

目前至少还有 **5个真实阻断问题**。

---

# 一、当前 GitHub Actions 很可能第一步就失败

`package.json`已经新增：

```text
eslint
eslint-plugin-vue
vue-eslint-parser
```

但 `package-lock.json` 根节点仍然只有：

```text
@vitejs/plugin-vue
vite
```

没有刚添加的三个ESLint依赖。

而所有工作流和构建脚本都使用：

```bash
npm ci
```

`npm ci`要求 `package.json` 和 `package-lock.json` 严格一致，否则会直接退出，不会帮你自动更新锁文件。([npm 文档][1])

## 必须先执行

在Windows开发机上：

```bash
cd frontend
npm install
npm run lint
npm run build
git add package.json package-lock.json
git commit -m "更新前端依赖锁文件"
git push
```

这是当前最直接的构建阻断项。

---

# 二、Sparkle公钥仍然是占位文字

生成的 `Info.plist` 中目前仍然写着：

```xml
<key>SUPublicEDKey</key>
<string>待生成</string>
```

这不是有效的EdDSA公钥。

Sparkle要求旧应用和新应用中都包含与私钥配对的有效 `SUPublicEDKey`；缺少或错误的公钥会导致更新签名验证失败。([GitHub][2])

所以目前即使：

- 检查到了更新；
- 下载了ZIP；
- appcast中有签名；

Sparkle也无法安全安装更新。

## 正确做法

生成一次Sparkle密钥对：

```text
私钥：存入 GitHub Actions Secret
名称：SPARKLE_PRIVATE_KEY

公钥：存入 GitHub Actions Secret 或 Repository Variable
名称：SPARKLE_PUBLIC_KEY
```

构建时动态写入：

```xml
<key>SUPublicEDKey</key>
<string>${SPARKLE_PUBLIC_KEY}</string>
```

不能保留“待生成”。

---

# 三、当前Sparkle签名脚本实际上注入不了签名

Release工作流执行：

```bash
SIGNATURE=$("$SIGN_TOOL" ... -p "$SPARKLE_PRIVATE_KEY")
```

随后判断：

```bash
grep -q "^edSignature:"
```

但Sparkle官方工具的输出格式类似：

```xml
sparkle:edSignature="一段签名" length="文件大小"
```

不是：

```text
edSignature:一段签名
```

([Sparkle][3])

因此这个判断基本不会通过，最终生成的appcast仍然会保持：

```xml
sparkle:edSignature=""
```

当前生成器也明确把签名留空。

而且Sparkle官方目前建议CI通过标准输入或密钥文件使用：

```bash
--ed-key-file -
```

而不是把私钥作为命令行参数传递；命令行直接传私钥已经被标记为不安全或弃用方式。([Sparkle][4])

## 最佳改法

不要继续自己拼装和解析签名，直接使用Sparkle官方的：

```text
generate_appcast
```

让它自动：

- 计算文件长度；
- 生成EdDSA签名；
- 生成正确appcast；
- 避免手工XML错误。

或者至少采用：

```bash
SIGN_OUTPUT=$(
  printf '%s' "$SPARKLE_PRIVATE_KEY" |
  "$SIGN_TOOL" \
    --ed-key-file - \
    "dist/StockHelper-${APP_VERSION_CLEAN}.zip"
)
```

再准确提取引号中的签名值。

并且必须改成：

```text
没有私钥 → 发布失败
签名失败 → 发布失败
签名为空 → 发布失败
找不到sign_update → 发布失败
```

当前代码在找不到签名工具时会“跳过签名继续发布”，这不符合正式更新的安全要求。

---

# 四、自动更新地址和Release类型冲突

应用的更新地址是：

```text
releases/latest/download/appcast.xml
```

但Release工作流创建的是：

```yaml
draft: true
prerelease: true
```

GitHub的“latest release”只认：

- 已发布；
- 非草稿；
- 非预发布；

的正式Release。草稿和预发布不能成为latest。([GitHub Docs][5])

所以李叔电脑访问：

```text
releases/latest/download/appcast.xml
```

可能拿不到刚发布的测试版本。

## 两套更新渠道应分开

测试版：

```text
单独的 beta-appcast.xml
指向明确版本或测试仓库
```

正式版：

```yaml
draft: false
prerelease: false
```

并继续使用：

```text
releases/latest/download/appcast.xml
```

不能让正式客户端依赖一个始终是草稿或预发布的Release。

---

# 五、Developer ID签名和Apple公证仍未执行

当前构建脚本最后只是打印提示：

```text
下一步：
codesign
notarytool
stapler
```

并没有真正执行。

Release工作流也只做了：

```text
构建
→ Sparkle签名尝试
→ 生成appcast
→ 上传Release
```

没有：

- 导入Developer ID证书；
- 对Sparkle内部XPC和Framework签名；
- 对后端二进制签名；
- 对Swift启动器签名；
- 对整个 `.app` 签名；
- Hardened Runtime；
- 时间戳；
- `codesign --verify`；
- Apple公证；
- `stapler staple`；
- `spctl`验证。

Apple说明，Mac App Store以外正式分发的软件应使用Developer ID签名，并提交Apple公证，以便Gatekeeper验证来源、完整性和公证票据。([Apple Developer][6])

## 当前发布出来的ZIP仍然是未签名版本

而且构建脚本在签名和公证之前就已经生成ZIP：

```bash
ditto -c -k --keepParent ...
```

正式顺序应该是：

```text
构建.app
→ 写入Sparkle公钥
→ 签名所有嵌套组件
→ 签名整个.app
→ codesign验证
→ 生成公证ZIP
→ notarytool提交
→ stapler写入公证票据
→ 再次生成最终ZIP
→ 对最终ZIP进行Sparkle EdDSA签名
→ 生成appcast
→ 发布Release
```

不能先压缩，再只打印“以后签名”。

---

# 六、Swift启动器这次已经真正参与构建

这一点这次确实修好了。

构建脚本现在会使用 `swiftc` 编译：

```text
main.swift
Updater.swift
```

并链接：

```text
Cocoa
Sparkle.framework
```

`main.swift`也已经实际创建：

- 后端子进程；

- 数据目录；

- 服务健康检查；

- 浏览器启动；

- 菜单栏图标；

- 检查更新；

- 退出应用；

- Sparkle更新控制器。

这是实质性进展。

但目前构建脚本有一个不适合正式版的逻辑：

```text
Sparkle编译失败
→ 自动退回不带Sparkle的版本
→ 继续认为构建成功
```

既然项目明确要求自动更新，正式Release时应当：

```text
Sparkle编译失败
→ 整个构建失败
```

不能悄悄生成一个没有更新功能的客户端。

开发测试版可以允许回退，正式发布版不允许。

---

# 七、macOS运行器需要开始迁移

工作流目前使用：

```yaml
runs-on: macos-14
```

目前GitHub的 `macos-14` 是arm64环境，架构与李叔的M4相符；但macOS 14运行器已从2026年7月开始进入弃用周期，计划在2026年11月停止支持。GitHub当前提供 `macos-15` 和更新的arm64运行器。([GitHub][7])

建议现在直接改成：

```yaml
runs-on: macos-15
```

目标设备是Mac mini M4，本身不需要兼容很老的macOS。

---

# 八、还有两个不阻断测试、但交付前要处理的问题

## 1. 后端启动失败仍会打开浏览器

Swift启动器等待30秒后，即使后端始终没有启动成功，也会继续打开浏览器。

应改成：

```text
后端成功 → 打开浏览器

后端失败 → 显示：
“股票分析助手启动失败，请重新打开；如仍失败，请联系维护人员。”
```

不能给李叔打开一个无法访问的空白页面。

## 2. 后端日志没有可靠落盘

Swift启动的后端进程没有把标准输出、错误输出重定向到：

```text
~/Library/Application Support/Stock Helper/logs/
```

一旦李叔电脑启动失败，你远程排查时可能没有足够日志。

至少需要：

```text
launcher.log
backend.log
update.log
```

并在菜单中提供：

```text
导出诊断信息
```

---

# 最终评价

这轮以后，准确状态是：

> **核心业务程序已经基本开发完成，Swift原生启动器也已经真正进入构建；但当前仓库仍不能生成一个具备可靠自动更新、Developer ID签名和Apple公证的正式交付版本。**

现在先不要继续反复让AI宣称“全部完成”，直接按验收结果推进：

```text
1. 更新并提交 package-lock.json
2. 生成Sparkle公私钥
3. 动态写入SUPublicEDKey
4. 修复sign_update调用与签名提取
5. 签名失败时终止发布
6. 修复latest与draft/prerelease冲突
7. 加入Developer ID签名和Apple公证
8. 将Runner改为macos-15
9. 推送测试Tag v0.1.0
10. 确认GitHub Actions全部绿色
11. 下载arm64 .app到M芯片Mac
12. 完成首次安装、Keychain、备份和退出测试
13. 再发布v0.1.1测试自动更新
```

完成 `v0.1.0 → v0.1.1` 的真机升级，并确认文字、图片、历史记录全部保留以后，才可以认定这套程序真正具备交付条件。

[1]: https://docs.npmjs.com/cli/v10/commands/npm-ci/?utm_source=chatgpt.com "npm-ci | npm Docs"
[2]: https://github.com/sparkle-project/Sparkle/discussions/2597?utm_source=chatgpt.com "Help signing a `.dmg` with EdDSA key. · sparkle-project Sparkle · Discussion #2597 · GitHub"
[3]: https://sparkle-project.org/documentation/publishing/?utm_source=chatgpt.com "Publishing an update - Sparkle: open source software update framework for macOS"
[4]: https://sparkle-project.org/documentation/upgrading/?utm_source=chatgpt.com "Upgrading from previous versions of Sparkle - Sparkle: open source software update framework for macOS"
[5]: https://docs.github.com/en/rest/releases/releases?utm_source=chatgpt.com "REST API endpoints for releases - GitHub Docs"
[6]: https://developer.apple.com/developer-id/?utm_source=chatgpt.com "Signing Mac Software with Developer ID - Apple Developer"
[7]: https://github.com/actions/runner-images/releases?utm_source=chatgpt.com "Releases · actions/runner-images · GitHub"
