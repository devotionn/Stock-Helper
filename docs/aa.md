我重新检查了最新提交 **`34b0d749`——“完成审查报告第三轮全部修复”**。这次确实又修掉了不少问题，但提交说明里“全部修复”仍然说得过满。

# 现在的总体判断

目前可以评价为：

| 部分                 | 完成度 |
| -------------------- | -----: |
| 12格业务功能         |    90% |
| Windows端开发与调试  |    90% |
| 数据安全、备份、迁移 |    80% |
| macOS打包基础        |    60% |
| macOS真实应用启动器  |    20% |
| Sparkle自动更新      |    10% |
| 签名、公证、正式交付 | 0%—10% |

**Windows上能够完成的核心业务代码，基本已经做到位了。**

现在可以正式进入：

```text
GitHub Actions构建第一个macOS arm64测试包
→ 修正构建问题
→ M芯片Mac真机测试
```

但还不能直接告诉李叔“程序已经可以自动更新并长期使用”。

---

# 这轮已经真正修好的内容

## 1. Keyring正式加入依赖

现在生产依赖中已经加入：

```text
keyring==25.5.0
```

正式打包环境如果完全没有Keyring，也不再静默退回SQLite，而是直接报错，避免把密钥偷偷写进普通数据库。

这个方向正确。

## 2. PyInstaller动态导入和前端路径已修正

`run.py`已经改成直接导入FastAPI应用，而不是通过字符串动态导入：

```python
from app.main import app
uvicorn.run(app, ...)
```

前端资源也开始使用PyInstaller的 `_MEIPASS` 路径查找。

Spec中也补充了主要后端模块的隐藏导入。

所以之前“后端启动失败”或者“浏览器里找不到前端”的风险，已经大幅下降。

## 3. 测试环境隔离已经修正

现在会在导入应用模块之前设置测试数据目录，并且每个测试重新初始化干净数据库，解决了测试污染正式数据目录的问题。

## 4. CI已经支持Tag触发

CI现在同时监听：

```yaml
branches: [main]
tags:
  - "v*"
```

原来macOS构建任务永远不会触发的问题，已经修复。

## 5. 备份恢复继续加强

已经增加：

- 恢复操作锁；
- 解压前文件数量和体积检查；
- 数据库及图片完整回滚；
- 从数据库读取真实 `schema_version`；
- 原子覆盖备份文件。

这部分已经达到可继续真机测试的水平。

---

# 现在最严重的问题：Swift启动器根本没有被用上

仓库里确实新增了：

```text
packaging/macos/launcher/main.swift
packaging/macos/launcher/Updater.swift
```

`main.swift`里也写了：

- 启动后端；

- 等待服务；

- 打开浏览器；

- 创建菜单栏图标；

- 点击退出时停止后端。

但是，**构建脚本完全没有编译这个Swift文件。**

构建脚本最终仍然把下面这个Shell脚本写入应用：

```bash
#!/bin/bash
DIR=".../Resources/backend"
exec "./stock-helper-server"
```

因此，当前生成出来的 `.app` 实际运行的是：

> Shell脚本启动器，而不是刚写的Swift启动器。

这意味着现在实际交付的应用没有：

- 菜单栏图标；
- “打开股票分析助手”菜单；
- “退出”菜单；
- 可靠的后端进程管理；
- 防止重复启动；
- Swift层面的Sparkle更新控制器。

换句话说：

> `main.swift`目前属于仓库里“写好了但没有参加构建”的死代码。

## 正确做法

构建脚本需要真正执行类似：

```bash
swiftc \
  packaging/macos/launcher/main.swift \
  packaging/macos/launcher/Updater.swift \
  -framework Cocoa \
  -F "$SPARKLE_FRAMEWORK_PATH" \
  -framework Sparkle \
  -Xlinker -rpath \
  -Xlinker "@executable_path/../Frameworks" \
  -o "$APP_DIR/Contents/MacOS/StockHelperLauncher"
```

然后删除当前生成Shell启动器的代码。

---

# 第二个严重问题：Sparkle仍然没有真正接入

`Updater.swift`目前全部是说明性注释：

```swift
// import Sparkle
// 取消注释当 Sparkle.framework 集成后
```

而且没有实际创建：

```swift
SPUStandardUpdaterController
```

构建脚本虽然会下载并复制 `Sparkle.framework`，但：

- Swift启动器没有链接Sparkle；
- `import Sparkle`没有启用；
- 没有“检查更新”菜单；
- 没有启动自动检查；
- 没有处理更新完成后的重启；
- 没有实际验证更新包签名。

所以目前的情况是：

```text
Sparkle.framework被放进.app
≠
应用已经有自动更新功能
```

**目前自动更新仍然不可用。**

---

# 第三个严重问题：更新包文件名仍然对不上

构建脚本会生成：

```text
StockHelper-1.0.1.zip
```

因为它会去掉Tag中的 `v`。

但Release工作流又重新生成：

```text
StockHelper-v1.0.1.zip
```

并且最终只上传这个带 `v` 的文件。

与此同时，appcast中的下载地址是：

```text
StockHelper-1.0.1.zip
```

不带 `v`。

最终结果：

```text
GitHub Release实际文件：
StockHelper-v1.0.1.zip

appcast要求下载：
StockHelper-1.0.1.zip
```

客户端会得到404。

## 应该统一为一种格式

建议统一为：

```text
Tag：v1.0.1
内部版本号：1.0.1
更新包：StockHelper-1.0.1.zip
```

Release工作流不要重新压缩，直接上传 `build_app.sh` 已经通过 `ditto` 生成的包。

---

# 第四个严重问题：Sparkle签名仍然为空

当前生成的appcast里：

```xml
sparkle:edSignature=""
```

同时应用内的公钥还是：

```xml
<SUPublicEDKey>待生成</SUPublicEDKey>
```

这意味着即使客户端真正接入Sparkle，也无法验证和安装更新包。

正确流程必须是：

```text
生成Sparkle EdDSA密钥对
→ 公钥写进Info.plist
→ 私钥保存在GitHub Actions Secrets
→ sign_update对ZIP签名
→ 签名值写进appcast.xml
→ 上传ZIP和appcast
```

不能发布一个空签名的appcast。

---

# 第五个问题：Swift健康检查和后端令牌发生冲突

Swift启动器会调用：

```text
http://127.0.0.1:8765/api/health
```

并要求返回200。

但是后端安全中间件规定：

- 除了 `/api/session`；
- 其他所有 `/api/` 请求都必须带会话令牌。

Swift启动器没有带令牌，因此：

```text
GET /api/health
→ 401
```

启动器会一直等待30次，每次1秒，然后才打开浏览器。

也就是说，Swift启动器真正启用后，每次打开应用可能白等约30秒。

## 修复方案

最简单的是把健康检查设为免令牌：

```python
if path in {"/api/session", "/api/health"}:
    return await call_next(request)
```

健康接口只返回：

```json
{ "status": "ok" }
```

不包含客户数据，允许本机免令牌访问是合理的。

---

# ESLint仍然没有真正配置完整

现在已经增加：

```json
"lint": "eslint src --ext .vue,.js",
"eslint": "^8.57.0"
```

但还缺少：

```text
eslint-plugin-vue
vue-eslint-parser
```

普通ESLint无法正确解析 `.vue` 单文件组件。

而CI目前也只执行：

```text
npm run build
```

没有执行：

```text
npm run lint
```

所以“ESLint完成”仍然只是部分完成。

---

# Keychain还有一个迁移问题

新代码会从Keychain读取AI密钥，但早期版本可能已经把密钥存进SQLite的：

```text
settings.ai_api_key
```

当前没有看到“一次性迁移”逻辑：

```text
发现数据库有旧密钥
→ 写入Keychain
→ 验证读取成功
→ 删除数据库旧密钥
```

虽然李叔还没有正式投入使用，影响暂时不大，但在首次正式发布前最好清理掉，避免开发测试期间的旧密钥继续留在数据库和备份文件中。

---

# 测试比以前多，但不能证明Mac版本可交付

现在新增了模块、组合、备份、安全和分析相关测试，这比之前明显好。

但所谓“16个测试全部通过”，主要还是API基础测试，还没有覆盖：

- PyInstaller产物真实启动；
- `.app`双击启动；
- Swift启动器编译；
- Sparkle检查更新；
- Keychain真实读写；
- 自动更新后数据是否保留；
- 恢复成功后的完整数据比对；
- 恢复中途失败自动回滚；
- Mac重启和重复启动；
- Gatekeeper；
- 签名和公证。

另外，我目前没有看到该提交对应的已通过状态检查记录，因此“测试全部通过”现在主要还是提交说明里的声明，尚不能当作GitHub CI成功证据。

---

# 最终判断

这次修改后，可以确认：

> **Windows上的核心业务开发、跨平台数据目录、基础安全、备份恢复、数据库迁移和测试框架已经基本做到位。**

现在真正剩下的核心工作已经集中到macOS交付链路：

```text
真正编译Swift启动器
→ 正式链接Sparkle
→ 修复health令牌冲突
→ 统一更新包文件名
→ 生成真实EdDSA签名
→ 动态写入SUPublicEDKey
→ GitHub Actions生成arm64应用
→ 应用启动冒烟测试
→ M芯片Mac真机安装
→ 签名和公证
→ 1.0.0升级1.0.1完整测试
```

所以现在可以进入Mac构建阶段，但**不要发布Tag给李叔更新**。应先把Swift启动器和Sparkle链路真正接通，否则当前所谓的“自动更新”只是目录、框架和说明文件已经存在，功能本身还没有运行起来。
