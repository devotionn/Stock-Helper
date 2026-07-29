我已经把 `devotionn/Stock-Helper` 当前代码、最近三次提交和主要前后端文件完整过了一遍。

# 一、总体结论

这套代码不是空架子，已经具备了一个比较完整的 **一期业务原型**：

- 12个固定模块；
- 文字录入和自动保存；
- 单图、多图上传；
- 剪贴板截图粘贴；
- 图片预览、删除、排序；
- 自定义模块组合；
- 多模态AI分析；
- 历史记录和输入快照；
- AI复盘、操作建议；
- SQLite数据库；
- 手动备份和恢复；
- 大字体、大按钮页面。

但它目前仍然属于：

> **Windows开发环境下可以继续调试的业务原型，而不是能够直接交付给李叔 Mac mini M4 使用的正式版本。**

我的综合评价：

| 方面           | 当前评价 |
| -------------- | -------: |
| 需求匹配度     |     8/10 |
| 页面易用性     |     8/10 |
| 后端业务完整度 |     7/10 |
| 数据库设计     |     7/10 |
| AI调用稳定性   |     5/10 |
| 数据安全与恢复 |     4/10 |
| 本地接口安全   |     3/10 |
| macOS部署能力  |     1/10 |
| 自动更新能力   |     0/10 |
| 自动测试与CI   |     1/10 |

**作为第一版原型是合格的；作为真实交付版本，目前还不能直接放到李叔电脑里长期使用。**

---

# 二、现在代码做得比较好的地方

## 1. 核心业务方向没有跑偏

代码确实是围绕我们前面确定的简单逻辑开发的，没有搞复杂知识库、多智能体或量化交易。

数据库固定初始化12个模块，包含一周策略、股票1至4、技术派观点、钱说观点、大盘走势、反向操作、AI复盘、行业板块和操作建议。

组合分析也保留了用户选择顺序：

```text
0 → 1 → 7 → 8
```

后端会按照数组顺序生成模块快照，并把顺序传给AI。

这一点符合李叔的真实需求。

## 2. 文字自动保存设计不错

文字保存使用了 `revision` 乐观锁。

当前页面版本和数据库版本不一致时，会返回409，避免两个页面同时编辑导致内容被静默覆盖。

前端还实现了5秒防抖自动保存，并显示：

- 已自动保存；
- 保存中；
- 未保存。

这对60多岁的用户很重要。

## 3. 图片处理比普通原型认真

图片不是只看文件扩展名，而是通过Pillow打开并验证真实格式，同时检查：

- 文件大小；
- 图片尺寸；
- 总像素数量；
- 实际图片格式。

文件使用SHA-256命名，可以避免同名覆盖；最新版还改成先写临时文件，再进行原子替换，方向是正确的。

## 4. SQLite基础配置合理

数据库启用了：

- WAL模式；
- 外键；
- busy timeout；
- `synchronous=FULL`。

对于单机、单用户、数据量不大的本地系统，这个选择合适，不需要MySQL。

## 5. 历史分析保存了输入快照

分析时不仅保存AI结果，还保存了当时各模块的：

- 模块编号；
- 模块名称；
- 排列顺序；
- 文字内容；
- 图片引用。

这意味着以后修改当前模块，不会改变以前保存的文字快照。这个思路符合复盘要求。

## 6. AI图片传输问题已经修正

最初代码使用：

```text
file:///本地图片路径
```

远程AI当然无法读取客户Mac上的本地文件。最新版已经把图片转换成Base64 Data URI，再发送给远程多模态API。

这个修复是必要且正确的。

---

# 三、必须优先修复的问题

下面这些不是“以后优化”，而是正式交付前必须解决。

# P0-1：现在的数据目录不适合macOS应用

当前数据保存在：

```text
backend/data/
```

因为代码把 `data_dir` 设置成后端代码目录下的 `data`。

这在开发源码中可以运行，但打包成 `.app` 后会产生严重问题：

- `.app` 内部属于应用本体，不应该写入客户数据；
- 应用签名后修改内部文件可能破坏签名完整性；
- 更新整个应用时可能覆盖数据；
- 用户移动应用位置后数据路径变化；
- 从只读位置或DMG启动时可能无法写入；
- PyInstaller打包后路径结构与源码目录不同。

前端目录也直接假设存在：

```text
项目根目录/frontend/dist
```

打包成Mac应用后，这个路径也不再成立。

## 必须改成

李叔的数据统一保存在：

```text
~/Library/Application Support/Stock Helper/
├── database/
│   └── stock_helper.db
├── assets/
│   ├── original/
│   └── thumbnails/
├── backups/
├── logs/
├── temp/
├── updates/
└── runtime/
```

应用程序本体放在：

```text
/Applications/股票分析助手.app
```

**应用和客户数据必须彻底分离。**

---

# P0-2：本地接口目前存在明显安全风险

后端虽然只监听 `127.0.0.1`，这是正确的，但当前CORS配置为：

```python
allow_origins=["*"]
allow_credentials=True
allow_methods=["*"]
allow_headers=["*"]
```

与此同时：

- 接口没有任何本地身份验证；
- 任意接口都可以直接调用；
- 设置接口会把完整AI密钥返回给前端。

这意味着李叔在浏览器中打开一个恶意网页时，该网页理论上可能访问本机的股票分析助手接口，读取设置、修改数据、调用AI，甚至尝试删除历史记录。

“只监听本机”并不代表浏览器里的其他网站无法访问本机接口。

## 必须处理

正式版本需要：

1. 生产环境彻底关闭通配符CORS；
2. 开发环境只允许 `http://127.0.0.1:5173`；
3. 检查 `Host`、`Origin` 和 `Referer`；
4. 启动时生成随机本地会话令牌；
5. 写操作必须校验本地会话；
6. AI密钥不再保存在普通SQLite设置表；
7. macOS使用Keychain保存密钥；8.设置接口只返回：

```json
{
  "has_api_key": true,
  "masked_api_key": "sk-****8A3F"
}
```

不能把完整密钥重新发给浏览器。

另外，仓库当前是 **public公开仓库**。这是商业客户项目，建议源码仓库改为private；自动更新的二进制文件以后可以放到独立的发布仓库或对象存储。

---

# P0-3：备份恢复功能存在数据损坏和路径安全风险

当前备份思路是对的，使用了SQLite在线备份API，并把数据库和图片压缩成 `.shbackup`。

但恢复逻辑还不能正式使用。

## 问题一：ZIP路径穿越

恢复图片时，代码直接将压缩包中的文件名拼接到图片目录：

```python
rel = name[len("assets/"):]
target = settings.assets_dir / rel
```

如果压缩包里出现：

```text
assets/../../其他文件
```

可能把文件写到目标目录之外。

即使李叔一般只使用系统自己生成的备份，也不应该保留这种风险。

## 问题二：直接覆盖正在使用的数据库

恢复时直接执行：

```python
shutil.copy2(..., settings.db_path)
```

此时FastAPI仍在运行，其他请求仍可能打开SQLite连接。直接替换正在运行的数据库存在：

- WAL不一致；
- `-wal`、`-shm`残留；
- 部分恢复；
- 并发写入；
- 数据库损坏。

## 问题三：不是完整恢复

图片只是在原目录上追加和覆盖，没有删除备份中不存在的旧文件。因此“恢复”后并不一定等于备份时的状态。

## 问题四：缺少完整校验

现在只检查压缩包中是否有：

```text
manifest.json
database.db
```

还缺少：

- 备份文件大小限制；
- 解压后总大小限制；
- 文件数量限制；
- SHA-256校验；
- SQLite `integrity_check`；
- 数据库版本兼容检查；
- ZIP Bomb防护；
- 路径安全检查；
- 失败自动回滚。

## 问题五：备份失败可能仍显示成功

后端备份失败时不是返回HTTP错误，而是返回：

```json
{
  "success": false,
  "message": "备份失败……"
}
```

但前端不检查 `success`，始终使用成功样式提示。

所以可能出现：

> 备份失败：磁盘空间不足

但提示框颜色仍然是绿色成功。

## 正确方案

恢复必须采用：

```text
上传备份
→ 保存到唯一临时目录
→ 校验压缩包
→ 校验所有路径
→ 校验manifest和SHA-256
→ 解压到隔离目录
→ SQLite integrity_check
→ 创建恢复前备份
→ 进入维护状态，阻止其他写操作
→ 原子替换数据库和图片目录
→ 重新初始化数据库连接
→ 启动健康检查
→ 成功后删除临时文件
→ 失败则自动恢复原数据
```

---

# P0-4：当前没有macOS应用和自动更新代码

仓库现在只有Windows启动脚本：

```bat
cd /d "%~dp0backend"
python run.py
```

以及创建Windows `.lnk` 快捷方式的PowerShell脚本。

目前仓库里还没有发现：

- macOS `.app` 启动壳；
- Apple Silicon arm64打包配置；
- PyInstaller spec；
- Swift/AppKit启动器；
- Sparkle自动更新；
- GitHub Actions工作流；
- Developer ID签名；
- Apple公证；
- appcast更新文件；
- GitHub Releases自动发布；
- 更新校验和回退。

所以现在的代码 **不能直接部署到李叔的Mac mini M4上作为正式应用**。

---

# 四、AI分析部分的问题

## 1. 实际上不是后台异步分析

后端接口会一直等待AI返回：

```python
result = await call_ai(...)
```

然后才向浏览器返回分析记录。

前端也会一直卡在当前请求中，提示用户等待30至120秒。

虽然数据库设计了：

```text
pending
running
completed
failed
interrupted
```

但当前并没有真正实现“提交任务后后台运行”。

### 风险

- 浏览器关闭或网络中断时状态不好处理；
- 请求超过代理或客户端超时会失败；
- 重复点击可能生成重复分析；
- 无法真正恢复或重新执行中断任务。

### 建议

改成：

```text
POST /api/analysis
→ 立即创建记录
→ 返回 202 + analysis_id
→ 后端后台任务执行AI
→ 前端每2秒查询状态
→ 完成后自动进入结果页
```

不需要引入Celery或Redis，单机系统使用一个简单的内存任务队列和SQLite状态表就够了。

## 2. 图片没有控制分析数量和发送大小

每张原始图片都直接读取到内存，再转换成Base64。

当前单张图片最大允许20MB。

假如选择8个模块，每个模块有5张20MB图片，理论原始数据就达到800MB；Base64还会额外增加约三分之一体积。

真实问题更多是：

- 请求体过大；
- AI接口拒绝；
- 调用费用过高；
- 请求超时；
- 内存瞬间升高；
- 大量Retina截图没有必要使用原始分辨率。

### 正确做法

保留原图不变，但在AI分析前生成临时分析图：

- 最长边压缩至1600至2048像素；
- JPEG或WebP质量约80至88；
- 单张建议控制在2MB以内；
- 一次分析最多限制10至16张图片；
- 超过数量时让用户选择；
- 估算请求大小后再提交。

## 3. 目前只兼容一种API格式

当前请求和返回结构固定为OpenAI兼容格式：

```text
messages
choices[0].message.content
```

如果后面改用不同格式的火山、Anthropic、Gemini或其他接口，代码不能只修改地址就直接使用。

应该建立：

```text
AIProvider
├── OpenAICompatibleProvider
├── VolcengineProvider
├── AnthropicProvider
└── GeminiProvider
```

一期只实现真正使用的一个供应商也可以，但接口层要分开。

## 4. JSON结果校验不够严格

AI返回结果解析失败时，`parse_ai_result()` 返回 `None`，但调用仍然返回：

```python
error: None
```

后端随后把分析标记为 `completed`，即使结构化结果为空。

应该使用Pydantic定义固定结果模型，检查七个字段是否完整；解析失败时：

- 可以保留原始文本；
- 标记为 `completed_with_warning`；
- 或自动要求AI重新格式化一次；
- 不应直接当作完全成功。

---

# 五、数据库和历史快照中的具体问题

## 1. 历史图片顺序保存错误

保存分析图片快照时，`order_index` 使用的是模块在组合中的序号 `idx`：

```python
(analysis_id, mid, idx, img["id"], ...)
```

这意味着同一个模块的所有图片都可能保存成相同顺序。

例如模块1有三张图片，本来顺序是：

```text
1、2、3
```

快照中可能全部变成：

```text
模块排列序号 = 1
```

历史详情再按照这个字段排序时，图片顺序无法保证。

应增加：

```text
module_order_index
image_order_index
```

分别保存模块顺序和模块内图片顺序。

## 2. 同一张图片可以重复插入同一模块

图片文件虽然按照SHA-256复用，但 `draft_assets` 没有：

```sql
UNIQUE(module_id, asset_id)
```

上传接口也会直接新增关联记录。

结果可能是：

- 同一张图重复显示；
- Vue使用相同 `img.id` 作为key；
- 删除一次可能删除该模块中所有相同关联；
- 图片顺序异常。

正式版应禁止同一图片在同一模块中重复添加，或者为关联记录单独返回 `draft_asset_id`。

## 3. 数据库迁移机制过于临时

现在迁移方式是启动时检查三个字段，不存在就执行 `ALTER TABLE`。

这可以应付一次小改动，但自动更新以后会不断出现：

```text
1.0 → 1.1 → 1.2 → 2.0
```

必须建立明确的迁移版本：

```text
schema_version
migration_history
```

例如：

```text
001_initial.sql
002_add_review_flags.sql
003_add_image_order.sql
004_move_secret_to_keychain.sql
```

每次升级前自动备份，迁移全部成功后才提交版本。

## 4. 保存模块版本时返回时间为空

新建模块版本后，接口直接返回：

```python
created_at=""
```

应该插入后重新查询数据库记录，返回真实时间。

---

# 六、前端面向李叔还需要调整的地方

## 1. Mac上不应该写“Ctrl+V”

页面目前提示：

```text
支持上传或直接 Ctrl+V 粘贴截图
```

李叔使用Mac，应显示：

```text
按 Command + V 粘贴截图
```

或者根据系统自动显示：

```text
Mac：⌘V
Windows：Ctrl+V
```

实际粘贴事件本身可以工作，主要是提示文字要改。

## 2. 离开页面前可能丢失5秒内的文字

页面离开时只清除了自动保存计时器：

```javascript
if (autoSaveTimer) clearTimeout(autoSaveTimer);
```

假如李叔刚输入内容，不到5秒就点击“返回工作台”，计时器被清除，最后的内容可能没有保存。

必须在：

- 点击返回；
- 路由切换；
- 页面关闭；
- 应用退出；

之前执行一次最终保存，保存失败则提示用户不要离开。

## 3. 备份位置不应该让老人手工输入路径

现在页面要求手工填写类似：

```text
D:\Backups
```

而且仍然是Windows示例。

Mac正式版应该由原生应用弹出文件夹选择窗口：

```text
选择备份文件夹
```

李叔只需要点击：

```text
桌面
文稿
iCloud Drive
移动硬盘
```

不应该要求他理解文件系统路径。

## 4. 上传成功提示不准确

逐张上传时，即使某些图片失败，循环结束后仍会提示：

```text
图片上传完成
```

应显示：

```text
成功上传4张，失败1张
```

并保留失败文件名。

## 5. 图片选择范围与后端不一致

前端使用：

```html
accept="image/*"
```

这会允许用户选择HEIC、TIFF等后端可能不支持的图片。

Mac截图多数是PNG，但iPhone和相册图片常见HEIC。需要二选一：

- 前端只允许JPG、PNG、WEBP；
- 或增加HEIC自动转换能力。

考虑到李叔可能从微信、iPhone和Mac相册传图，我倾向于支持HEIC读取后自动转成JPEG，同时保留原文件名。

---

# 七、工程化目前明显不足

前端脚本只有：

```text
dev
build
preview
```

没有：

- 单元测试；
- ESLint；
- 类型检查；
- Playwright；
- 构建校验。

后端依赖中也没有：

- pytest；
- pytest-asyncio；
- ruff；
- mypy；
- coverage。

正式项目至少要加入：

```text
后端：
pytest
pytest-asyncio
ruff

前端：
Vitest
Playwright
ESLint

CI：
后端测试
前端构建
API集成测试
macOS arm64打包测试
备份恢复测试
数据库迁移测试
```

---

# 八、建议采用的最终macOS结构

```text
股票分析助手.app
└── Contents/
    ├── MacOS/
    │   └── StockHelperLauncher
    ├── Resources/
    │   ├── backend/
    │   │   └── stock-helper-server
    │   ├── web/
    │   │   └── dist/
    │   ├── migrations/
    │   └── default-config/
    ├── Frameworks/
    │   └── Sparkle.framework
    └── Info.plist
```

客户数据独立存放：

```text
~/Library/Application Support/Stock Helper/
├── database/
├── assets/
├── backups/
├── logs/
├── temp/
├── runtime/
└── update-state/
```

启动过程：

```text
李叔点击“股票分析助手”
→ 检查是否已经运行
→ 启动FastAPI子进程
→ 等待 /api/health 返回正常
→ 打开默认浏览器
→ 建立本地安全会话
→ 李叔开始使用
```

退出过程：

```text
点击“退出股票分析助手”
→ 停止接受新任务
→ 等待正在保存的内容完成
→ 关闭数据库连接
→ 向后端发送SIGTERM
→ 等待后端退出
→ 超时后再强制结束
```

---

# 九、GitHub自动发布应该补充的内容

建议仓库新增：

```text
.github/
└── workflows/
    ├── ci.yml
    └── release-macos.yml

packaging/
└── macos/
    ├── launcher/
    ├── stock-helper.spec
    ├── build_app.sh
    ├── codesign.sh
    ├── notarize.sh
    └── generate_appcast.sh

backend/
├── migrations/
└── tests/

frontend/
├── tests/
└── e2e/
```

发布流程：

```text
你在Windows提交代码
→ GitHub Actions运行测试
→ macOS ARM环境构建Vue
→ 打包FastAPI arm64程序
→ 构建.app
→ Developer ID签名
→ Apple公证
→ Sparkle签名更新包
→ 生成appcast.xml
→ 上传GitHub Releases
→ 李叔的Mac自动发现更新
```

更新前必须自动执行：

```text
数据库备份
→ 图片索引检查
→ 当前版本记录
→ 更新包验签
→ 安装新版
→ 数据库迁移
→ 健康检查
→ 成功后完成更新
```

失败则：

```text
不提交数据库迁移
→ 恢复更新前数据
→ 保留旧版应用
→ 显示“更新未完成，已恢复原版本”
```

---

# 十、最终判断

这份代码的特点非常明显：

> **业务实现比工程交付走得快。**

目前核心页面和基础业务已经做出了七八成，说明产品逻辑基本确定，不需要推倒重写。

但是下面四部分需要重构或补齐：

1. **macOS数据目录和启动方式；**
2. **本地接口安全与Keychain；**
3. **可靠的备份、恢复和数据库迁移；**
4. **GitHub Actions、macOS arm64打包、签名、公证和自动更新。**

所以不建议现在直接在这份代码上加一个Mac启动脚本就交付。正确顺序是：

```text
先修数据与安全底座
→ 再修AI任务和备份恢复
→ 再完成macOS应用壳
→ 再接GitHub自动构建和Sparkle更新
→ 最后在你的M系列测试Mac进行完整升级测试
→ 确认无误后才安装到李叔的Mac mini M4
```

最准确的项目阶段定义是：

> **一期功能原型基本成型，但尚未进入macOS正式交付和长期维护阶段。**
