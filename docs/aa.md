我重新检查了最新提交 **`4bd310dc`——“完成审查报告全部Windows端可完成项”**。这次修改是实质性的，进步很明显。

## 现在的总体判断

**Windows阶段大约完成了80%—85%，已经可以开始准备第一次 macOS arm64 构建。**

但还不能说“Windows上所有工作都做到位了”。目前仍有 **3个P0级问题**，不修的话，GitHub Actions即使生成 `.app`，也可能出现：

- 应用打不开；
- 打开后只有后端、没有页面；
- AI密钥仍然落在SQLite；
- 自动更新完全不能用。

---

# 这次真正修好的部分

### 1. 跨平台数据目录已经基本正确

现在会根据系统自动选择：

```text
Windows：
%LOCALAPPDATA%\Stock Helper\

macOS：
~/Library/Application Support/Stock Helper/
```

并且覆盖 `data_dir` 后，数据库、图片、临时文件和备份目录会重新派生，不再继续写到源码目录。

这项可以认定为 **基本完成**。

### 2. 本地接口安全明显加强

目前已经加入：

- 随机会话令牌；

- `Host`白名单；

- 防DNS Rebinding；

- 非开发环境API请求必须带令牌；

- 前端首次启动自动获取令牌；

- 令牌只放在内存，不写入 `localStorage`。

这套安全逻辑对于本地单机系统已经比较合适。

### 3. AI图片限制逻辑修正

现在即使图片达到16张上限，后续模块的文字仍然会继续加入AI请求，不会再把后续模块整体跳过。

### 4. 历史图片顺序修正

历史详情现在按照 `image_order_index` 读取图片，之前“同一模块内图片顺序不稳定”的问题已经修复。

### 5. 备份恢复增加完整回滚

当前恢复流程已经包括：

- 解压前统计总大小；

- 文件数量和单文件大小限制；

- 路径安全检查；

- SQLite完整性检查；

- 恢复前自动备份；

- 数据库和图片回滚副本；

- 恢复失败后自动还原。

比上一版可靠很多。

---

# 仍然必须修复的P0问题

## P0-1：Keychain实际上还没有启用

代码虽然写了：

```text
MacKeychainStore
WindowsCredentialStore
```

但它依赖Python的 `keyring` 包；如果没有安装，就会自动退回 `DevelopmentSecretStore`，继续把密钥写入SQLite数据库。

而正式依赖文件中目前没有：

```text
keyring
```

只有FastAPI、Pillow、httpx等依赖。

所以现状是：

```text
代码结构上支持Keychain
≠
打包后的Mac程序真的使用Keychain
```

### 必须修改

在生产依赖中加入锁定版本的 `keyring`，并在PyInstaller中确认打包对应后端：

- macOS Keychain backend；
- Windows Credential Locker backend；
- 打包启动时执行一次密钥读写自检；
- 如果Keychain不可用，正式版本不能静默退回SQLite，应明确报错。

否则李叔输入的AI密钥仍可能明文保存在数据库里。

---

## P0-2：当前macOS打包产物很可能启动失败或没有前端页面

这里有两个风险。

### 风险一：PyInstaller可能漏掉 `app.main`

启动代码使用的是动态字符串：

```python
uvicorn.run("app.main:app")
```

但PyInstaller配置中的 `hiddenimports` 没有：

```text
app.main
app.routers.modules
app.routers.analysis
……
```

PyInstaller无法保证识别字符串形式的动态导入。构建出的程序可能报：

```text
Could not import module "app.main"
```

最稳妥的改法是直接导入：

```python
from app.main import app

uvicorn.run(
    app,
    host=settings.host,
    port=settings.port,
)
```

### 风险二：前端资源路径可能错一层

PyInstaller把前端文件打包到：

```text
frontend/dist
```

但是主程序查找前端时使用：

```python
FRONTEND_DIST = settings.base_dir.parent / "frontend" / "dist"
```

在源码环境能正常工作，但打包后资源通常应从PyInstaller运行目录读取。当前没有显式使用：

```python
sys._MEIPASS
```

因此很可能出现：

```text
后端启动成功
但浏览器打开后显示“前端文件未找到”
```

需要增加统一的资源路径函数：

```python
def resource_path(relative: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / relative
    return PROJECT_ROOT / relative
```

这两项仍然可以在Windows写完，再交给GitHub Actions的Mac环境验证。

---

## P0-3：Sparkle自动更新目前只是“占位代码”，还不能真正工作

现在的 `.app` 创建了一个空的：

```text
Contents/Frameworks/
```

但构建脚本没有复制Sparkle Framework，也没有Swift/AppKit启动器或 `SPUStandardUpdaterController`。

也就是说，目前客户端根本没有：

- 检查更新；
- 显示新版本；
- 下载更新；
- 替换旧应用；
- 重启；
- 失败回退。

### 当前appcast也有明确错误

Release工作流把版本参数传成：

```text
github.ref_name
```

例如：

```text
v1.0.1
```

生成器又在下载地址前增加一个 `v`：

```python
releases/download/v{version}/
```

最终地址会变成：

```text
releases/download/vv1.0.1/
```

下载地址是错的。

另外，当前代码把SHA-256哈希直接写进：

```xml
sparkle:edSignature
```

但Sparkle要求这里是真正使用EdDSA私钥生成的签名，不是普通SHA-256值。官方推荐使用Sparkle自带的 `generate_appcast` 或 `sign_update` 生成签名。([sparkle-project.org][1])

### 应用版本也被写死

无论发布标签是多少，`Info.plist`始终写：

```text
CFBundleVersion = 1.0.0
CFBundleShortVersionString = 1.0.0
```

Sparkle依赖递增的应用版本判断是否存在新版，因此这里必须由Git标签动态生成。([sparkle-project.org][2])

---

# 仍需补齐的P1问题

## 1. CI中的macOS构建任务实际上不会触发

`ci.yml`只在以下情况触发：

```yaml
push:
  branches: [main]
```

但 `macos-build` 又要求：

```yaml
if: startsWith(github.ref, 'refs/tags/v')
```

主分支提交不是Tag，Tag推送又不会触发这个CI工作流，因此这个任务实际上是“死任务”。

应改成以下任意一种：

```yaml
push:
  branches: [main]
  tags:
    - "v*"
```

或者让主分支每次都构建一个未签名的Mac测试产物。

## 2. Release没有先运行测试

`release.yml`接到标签后直接构建和发布，没有先执行：

- 后端测试；
- Ruff；
- 前端构建校验之外的检查；
- 打包后启动测试。

正式流程应为：

```text
测试通过
→ 打包
→ 启动健康检查
→ 签名
→ 公证
→ 生成Sparkle签名
→ 创建Release
```

并增加：

```yaml
permissions:
  contents: write
```

## 3. “ESLint已配置”目前名不副实

虽然新增了 `.eslintrc.cjs`，但 `package.json`：

- 没有安装 `eslint`；

- 没有Vue解析插件；

- 没有 `lint` 脚本；

- CI也没有执行前端lint。

所以目前只是放了一个配置文件，实际不能完成Vue代码检查。

## 4. 测试环境隔离顺序有错误

测试代码先导入：

```python
from app.main import app
```

之后才设置：

```python
STOCK_DATA_DIR
```

但 `app.main` 导入时已经初始化了全局 `settings`，因此后面设置环境变量已经太晚。测试很可能仍然使用默认数据目录，而不是 `tests/test_data`。

应在任何 `app` 模块导入前设置环境变量，或者使用 `monkeypatch` 后重新加载配置模块。

现有11个测试也主要是基础CRUD，只覆盖：

- 模块查询和保存；

- 常用组合；

- 创建备份；

- 无效备份拒绝。

还没有覆盖：

- AI异步任务；
- 图片压缩和16张限制；
- 会话令牌；
- Host校验；
- 数据库迁移；
- 成功备份后完整恢复；
- 恢复失败数据库回滚；
- PyInstaller程序启动；
- 前端页面流程；
- 自动更新。

---

# 备份还剩两个完善点

现在备份比以前可靠很多，但还应修：

1. 上传备份时使用 `await file.read()` 一次把整个文件读入内存，尚未限制压缩包本身大小。
2. 临时文件固定使用 `restore.zip`、`restore_extract`、`db_rollback.db`，没有恢复锁；连续点击或并发请求可能互相覆盖。
3. `manifest.json` 中 `schema_version` 仍固定写成 `1`，而数据库迁移当前已经到版本4。

应从数据库读取真实版本写入manifest，并检查备份版本是否高于当前程序支持版本。

---

# 最终结论

这次可以改口为：

> **Windows端的核心业务和大部分工程底座已经完成，可以进入macOS构建准备阶段；但Keychain依赖、PyInstaller资源/导入、CI触发和Sparkle更新链路仍未达到可用状态。**

现在不是推倒重写，而是再完成最后一轮工程修正：

```text
修复Keyring依赖
→ 修复PyInstaller动态导入和资源路径
→ 修复测试隔离
→ 修复CI触发
→ 用真实Sparkle工具生成签名
→ 让版本号随Tag变化
→ GitHub Actions生成第一个arm64 .app
→ 在你的M芯片Mac上安装测试
```

完成前三项后，就可以合理地说：**Windows上能做的主体工作基本做到位了。**

[1]: https://sparkle-project.org/documentation/publishing/?utm_source=chatgpt.com "Publishing an update - Sparkle: open source software update framework for macOS"
[2]: https://sparkle-project.org/documentation/?utm_source=chatgpt.com "Documentation - Sparkle: open source software update framework for macOS"
