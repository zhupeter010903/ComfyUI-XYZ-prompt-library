# XYZ Image Gallery — ARCHITECTURE

> 架构说明文档。本文档基于 `PROJECT_SPEC.md`，聚焦于"如何组织代码、组件如何协作、数据如何流动"。不包含具体实现代码。
>
> 目标读者：即将参与该子模块开发或评审的工程师；阅读本文档后应能回答：代码放在哪里、我要改的功能对应哪个模块、磁盘上的一张图片是怎么变成浏览器里的一张缩略图的、从零开始应该先写什么。
>
> **v2 重构要点（本次修订核心）**：
> 1. **单一写入者模型（Single Writer）** — 所有 SQLite 写操作汇入 `repo.WriteQueue`，按优先级串行执行，根除 `database is locked`。
> 2. **异步最终一致性（Async Metadata Sync）** — DB 是事实来源，先提交事务再异步写 PNG，新增 `metadata_sync_status` 字段与重试机制。
> 3. **批量操作增量提交（Per-Op Commit）** — `execute_move` / `bulk_delete` 改为"操作一个、入队一个"，崩溃后磁盘与索引依然一致。
> 4. **Watcher 心跳与补偿扫描（Watchdog Reconciliation）** — 30 s 周期的 `delta_scan` 兜底丢失的文件系统事件。
> 5. **性能强化** — 缩略图 LIFO 视口优先、FTS5 分词器显式配置、indexer 元数据解析进程池化。

---

## 1. 项目目录结构

Gallery 子模块寄生在现有的 `ComfyUI-XYZNodes` 插件内部，**共享** ComfyUI 的 aiohttp 服务端、`WEB_DIRECTORY` 与进程生命周期，但代码与数据完全自包含在 `gallery/` 与 `gallery_data/` 两个目录下，保证与既有 XYZ 节点互不影响（约束 **C-8**）。

```
ComfyUI-XYZNodes/
├── PROJECT_SPEC.md
├── ARCHITECTURE.md                   ← 本文档
│
├── __init__.py                       插件入口；除了注册现有节点外，首次 import 时
│                                     触发 gallery 子模块的初始化（见 §3.1）。
│
├── gallery/                          后端包（Python，纯服务端）
│   ├── __init__.py                   Gallery 子模块装配入口
│   ├── routes.py                     aiohttp HTTP + WS 路由层
│   ├── service.py                    用例编排层（业务流程）
│   ├── repo.py                       SQLite 仓储层（所有 SQL 集中点）
│   │                                 ★ 内嵌 WriteQueue + 单一写入者线程（§4.6）
│   ├── db.py                         Schema / 迁移 / PRAGMA / FTS5（含分词器配置）
│   ├── indexer.py                    冷启动扫描 + 增量 delta-scan + 单事件索引
│   │                                 ★ 元数据解析阶段进程池化（§4.7）
│   ├── metadata.py                   PNG tEXt/iTXt 读写（纯函数）
│   ├── metadata_sync.py              ★【新】异步 PNG 块同步 Worker（§4.8）
│   ├── thumbs.py                     缩略图生成 + LRU 淘汰
│   │                                 ★ LIFO 视口优先队列（§4.9）
│   ├── watcher.py                    watchdog 观察者 + Coalescer
│   │                                 ★ 心跳 + 30s 周期补偿扫描（§4.10）
│   ├── ws_hub.py                     WebSocket 广播枢纽
│   ├── folders.py                    注册根目录管理（output/input/custom）
│   ├── paths.py                      路径校验与沙箱
│   └── vocab.py                      prompt/tag 归一化 + 词表维护
│
├── js/                               前端（由 ComfyUI 的 WEB_DIRECTORY 暴露）
│   ├── gallery_topbar.js             顶栏按钮注册（唯一被 ComfyUI 前端加载的入口）
│   └── gallery_dist/                 预构建 SPA 产物（约束 C-9）
│       ├── index.html                SPA shell
│       ├── app.js                    路由 + 启动
│       ├── api.js                    REST + WS 客户端
│       ├── views/
│       │   ├── MainView.*            侧边栏 + 网格 + 顶部工具栏
│       │   └── DetailView.*          详情页 / 元数据面板 / 导航
│       ├── components/
│       │   ├── VirtualGrid.*         虚拟滚动网格
│       │   ├── ThumbCard.*           单个缩略图卡片（★ 显示同步状态徽标）
│       │   ├── FolderTree.*          目录树
│       │   ├── Autocomplete.*        prompt / tag 建议
│       │   ├── BulkBar.*             批量编辑工具栏（★ 增量进度展示）
│       │   ├── MovePicker.*          移动目标选择器
│       │   └── ConfirmModal.*        破坏性操作确认弹窗
│       └── stores/
│           ├── filters.*             FilterSpec / SortSpec 响应式状态
│           ├── selection.*           Selection 包络（explicit / all_except）
│           ├── folders.*             目录树缓存
│           ├── vocab.*               自动补全 LRU 缓存
│           └── connection.*          WS 连接 + 重连 + 焦点对账
│
└── gallery_data/                     运行时生成（git-ignored，C-12）
    ├── gallery.sqlite (+ WAL)        索引数据库
    ├── gallery_config.json           根目录 + 偏好（C-10，人类可读）
    ├── gallery_audit.log             破坏性操作审计日志（C-11）
    └── thumbs/
        └── ab/abc123....webp         2 字符分片的缩略图磁盘缓存
```

**边界说明**

- `gallery/` 只能依赖 ComfyUI 核心（`server.PromptServer`、`folder_paths`），不能 import `ComfyUI-XYZNodes` 下除自身外的任何模块（C-8）。
- `gallery_data/` 位于插件内部而非 ComfyUI 的 `output/`，这样用户清空或同步 `output/` 不会污染索引状态（C-12）。
- 前端只有 `gallery_topbar.js` 会被 ComfyUI 主界面加载；SPA 的所有资源走 `/xyz/gallery/static/*`，与 ComfyUI 前端隔离。
- **写入路径单一化**：除迁移脚本外，**任何对 SQLite 的写操作都必须经过 `repo.WriteQueue`**；直接调用 `cursor.execute("INSERT…")` 是 lint-禁止的。

---

## 2. 每个模块的职责

### 2.1 后端模块（`gallery/`）

| 模块 | 职责 | 关键不变式 |
| --- | --- | --- |
| `__init__.py` | 装配入口：确保 DB 文件存在、跑迁移、启动后台线程（含 WriteQueue 写入者、metadata_sync Worker、watcher 心跳）、注册路由。幂等。 | 不阻塞 ComfyUI 主事件循环（NFR-1）。 |
| `routes.py` | aiohttp 处理器，**只做 I/O**：解析请求、校验形状、调用 `service`、序列化响应、设置缓存头。无业务逻辑。 | 任何 CPU/磁盘操作 > 5 ms 必须 `run_in_executor`（C-2）。 |
| `service.py` | 用例编排层。把"列出图片"、"批量移动"等业务流程拆成对 `repo` / `indexer` / `thumbs` / `ws_hub` / `paths` / `metadata_sync` 的调用序列。事务边界与**写入优先级**归它决定。 | 所有跨模块副作用按"DB → enqueue PNG → 广播"的顺序保序。 |
| `repo.py` | 唯一与 SQLite 交互的入口。**内嵌 `WriteQueue`（优先级队列）+ 单一写入者线程**；对外暴露同步读 API 与异步写入 API（`enqueue_write(priority, op)` 返回 `Future`）。拥有连接池、预编译语句、游标分页、tag-AND / prompt-AND 查询构造器、Selection 解析。 | 写并发 = 1（C-1 强化）；读并发不受影响（WAL）。 |
| `db.py` | Schema DDL、前向兼容的版本化迁移、FTS5 虚拟表及其触发器、WAL / NORMAL / MMAP 等 PRAGMA。**显式声明 FTS5 分词器**（`unicode61` + `tokenchars` 配置，§4.7.2）。 | 迁移只前进不后退（C-4）。 |
| `indexer.py` | 三个入口：冷启动全量扫描、单根 delta-scan、单事件 upsert。对每个文件走 `(size, mtime_ns)` 指纹短路。**元数据解析（CPU 密集）走 ProcessPool**；解析结果回流到主线程后**统一通过 `repo.WriteQueue` 入队**。 | 幂等（C-3）；解析并行，写入串行。 |
| `metadata.py` | PNG `tEXt` / `iTXt` 块纯函数读写。读：ComfyUI 原生字段；写：只写 `xyz_gallery.*` 前缀的块；write-temp + rename。 | 绝不修改原有 ComfyUI 块（C-6，FR-23）；纯函数无副作用。 |
| `metadata_sync.py` ★【新】 | 异步 PNG 同步 Worker：消费 `image.metadata_sync_status='pending'` 队列，调用 `metadata.write_xyz_chunks`，成功后通过 `repo.WriteQueue` 把状态置 `ok`，失败置 `failed` 并按指数回退重试（最多 3 次）。 | DB 已是事实来源，PNG 写失败 **不回滚** DB；UI 通过状态字段感知。 |
| `thumbs.py` | WebP 生成（Pillow + ProcessPool）、磁盘缓存寻址、LRU 淘汰、按需生成。**请求队列采用 LIFO**：用户视口请求总是后进先出，避免被冷启动批量任务阻塞（§4.9）。 | 永不批量加载，内存峰值 ≤ 300 MB（NFR-7）；视口请求 P95 < 200 ms。 |
| `watcher.py` | 每个注册根挂一个 `watchdog` Observer；事件先入 `Coalescer` 合并、去抖、溢出降级。**新增心跳线程**：每 30 s 触发一次轻量级 `indexer.delta_scan`（仅做 `(size, mtime_ns)` 比对），作为事件丢失的兜底（§4.10）。 | 事件流 O(1) DB 写成本；不丢事件（事件 + 周期补偿双保险）。 |
| `ws_hub.py` | WebSocket 连接池 + 广播。事件类型新增 `image.sync_status_changed`（PNG 同步成功/失败时由 `metadata_sync` 触发）。 | Fire-and-forget；一致性兜底由前端焦点对账完成。 |
| `folders.py` | 注册根目录的 CRUD；持久化到 `gallery_config.json`。 | 禁止重叠的自定义根。 |
| `paths.py` | 所有来自客户端的路径必须经过 `resolve()` 且落在某个注册根内。 | 任何文件操作前的最后一道闸。 |
| `vocab.py` | `normalize_prompt()` 纯函数 + `tag` / `prompt_token` 词表的 `usage_count` 增减（增减操作通过 `WriteQueue` 入队）。 | 唯一的 token 归一化入口。 |

### 2.2 前端模块（`js/gallery_dist/`）

| 模块 | 职责 |
| --- | --- |
| `gallery_topbar.js` | 通过 `app.registerExtension` 在 ComfyUI 顶栏挂一个按钮，点击 `window.open('/xyz/gallery')`。 |
| `app.js` | SPA 入口：初始化 router、store、建立 WS 连接、挂载根视图。 |
| `api.js` | 薄客户端：REST 调用 + WS 订阅 + 错误信封解析。 |
| `views/MainView` | 组合 `FolderTree` + 过滤器面板 + 顶部工具栏 + `VirtualGrid`。 |
| `views/DetailView` | 渲染左图右元数据双栏；处理缩放 / 上一张 / 下一张；**显示 `metadata_sync_status` 与"重试同步"按钮**。 |
| `components/VirtualGrid` | 仅渲染可视视口 ± 2 屏的卡片（NFR-6）。 |
| `components/ThumbCard` | 缩略图 + 文件名 + 收藏按钮 + 右键菜单 + Bulk checkbox + **同步状态徽标**（`pending` 黄、`failed` 红）。 |
| `components/Autocomplete` | 前缀触发、debounce、前缀结果 LRU 缓存、键盘导航。 |
| `components/FolderTree` | 目录树 + 递归切换 + "管理自定义目录"模态入口。 |
| `components/BulkBar` | 批量模式下的顶栏；**进度条由"已记录/总数"驱动**（增量提交语义，§4.5）。 |
| `components/MovePicker` | 目标目录选择 + preflight 结果预览 + 单文件重命名覆盖。 |
| `components/ConfirmModal` | 所有破坏性操作共用。 |
| `stores/filters` | `FilterSpec` + `SortSpec` + 布局状态。 |
| `stores/selection` | `Selection` 包络（`explicit` / `all_except`）。 |
| `stores/folders` | 目录树缓存。 |
| `stores/vocab` | 自动补全前缀 → 结果 LRU。 |
| `stores/connection` | WS 状态机、`window.onfocus` 对账、订阅 `image.sync_status_changed` 更新徽标。 |

---

## 3. 数据流：磁盘 → 索引 → API → 前端

下图展示一张图片从落盘到出现在浏览器里，以及用户编辑（收藏 / 标签 / 移动 / 删除）的完整闭环。**v2 关键变化**：所有 DB 写入都汇入 `WriteQueue`，PNG 写入由独立 Worker 异步消化。

### 3.1 写入路径（文件系统事件 → 索引 → 前端）

```
[磁盘]                              [ComfyUI 进程：多生产者 → 单写入者 → 异步同步]                          [浏览器 Tab]

新文件落盘            ┌──────────┐
     │                │ watchdog │
     └────────────►   │ Observer │ ──────┐
 ComfyUI 出图 /       └────┬─────┘       │
 手动拷贝 / 同步           │原始事件      │
                           ▼              │
                     ┌─────────────┐      │  心跳（30s 周期补偿）
                     │  Coalescer  │      │  ┌──────────────────┐
                     │ (watcher.py)│      └─►│  Heartbeat       │
                     └──────┬──────┘         │ (watcher.py)     │
                            │ 250 ms 去抖     │ 触发 delta_scan  │
                            │ 50 条/批        └─────────┬────────┘
                            ▼                          │
                     ┌──────────────────────────┐      │
                     │  Indexer (主线程协调)    │◄─────┘
                     │  ┌────────────────────┐  │
                     │  │ ProcessPool 解析   │  │  CPU 密集：PNG 头 + 元数据
                     │  │ (2~4 worker，§4.7) │  │  返回 ParsedRecord
                     │  └─────────┬──────────┘  │
                     └────────────┼─────────────┘
                                  │ 解析结果汇总
                                  ▼
                  ╔═══════════════════════════════════════════╗
                  ║      repo.WriteQueue（优先级队列）        ║
                  ║                                           ║
                  ║   HIGH  ← service (用户 PATCH/收藏/标签)  ║
                  ║   MID   ← service (批量增量提交)          ║
                  ║   LOW   ← indexer / metadata_sync 状态回写║
                  ║                                           ║
                  ║      ┌─────────────────────────────┐      ║
                  ║      │  Single Writer Thread       │      ║
                  ║      │  顺序消费 → 一个事务一个 op │      ║
                  ║      └──────────────┬──────────────┘      ║
                  ╚═════════════════════│═════════════════════╝
                                        │ commit 后
                                        ▼
                                 ┌──────────────┐
                                 │ SQLite (WAL) │ ◄── 唯一事实来源（C-1）
                                 └──┬───────┬───┘
                                    │       │ 触发 PNG 待同步
                                    │       ▼
                                    │  ┌────────────────────┐
                                    │  │ metadata_sync      │  status=pending → ok / failed
                                    │  │ Worker (后台)      │  失败：指数回退 ≤3 次
                                    │  └─────────┬──────────┘
                                    │            │ 回写状态（LOW 优先级入队）
                                    │            ▼
                                    │      回到 WriteQueue
                                    │
                                    ▼
                            ┌────────────┐    image.upserted /
                            │   ws_hub   │──► image.updated /         ──►  stores/connection
                            └────────────┘    image.sync_status_changed     │
                                                                            ▼
                                                              filters 命中判断 → 补丁 VirtualGrid
```

**关键不变式**

- **DB 是事实来源**。WS 事件只是"让前端别等下一次轮询"；真正的对账靠焦点 reconciliation。
- **写入串行、读取并发**。WriteQueue 单消费者根除了 `database is locked`，WAL 仍允许任意并发读。
- **PNG 与 DB 解耦**。DB 提交即视为写成功；PNG 失败由 `metadata_sync` 重试，不影响业务返回。
- **事件不丢**。watchdog + 30s 心跳 delta_scan 双重保障。

### 3.2 读取路径（用户打开 Gallery → 看到缩略图）

```
浏览器打开新 Tab                          aiohttp                          SQLite / 文件系统
────────────────                        ────────                          ────────────────

GET /xyz/gallery                ───►   routes.serve_spa         ───►  返回 index.html + app.js

app.js 启动，建立 WS            ───►   routes.ws_handler        ───►  ws_hub 注册连接

GET /xyz/gallery/folders        ───►   service.list_folders     ───►  repo.folder_tree(...)
                                                                       └─ 单次 SELECT + Python 拼树（读，无队列）

GET /xyz/gallery/images?...     ───►   service.list_images      ───►  repo.build_tag_and_query(...)
   (FilterSpec+SortSpec+cursor)          │                              ├─ 选 rarest tag
                                         │                              ├─ 游标分页 (sort_key, id)
                                         │                              └─ 200 条 ImageRecord
                                         │                                  （含 metadata_sync_status）
                                         │
                                         └──► JSON 响应（含 next_cursor）

<img src=".../thumb/123?v=...">  ───►   routes.thumb            ───►  thumbs.request(id, src=VIEWPORT)
   (懒加载，IntersectionObserver)         │                              ├─ LIFO 入队，前置于冷启动批量
                                          │                              ├─ 命中磁盘 → stream
                                          │                              └─ 未命中 → ProcessPool 生成

用户改 tag / 收藏              ───►   PATCH /xyz/gallery/image/{id}
                                        │
                                        ├─ service.update_image
                                        │     ① repo.enqueue_write(HIGH, update_op) → await Future
                                        │     ② DB 提交成功 → 标记 sync_status='pending'（同事务）
                                        │     ③ ws_hub.broadcast('image.updated')   ← 立即返回 200
                                        │
                                        └─ 后台：metadata_sync 异步消费 pending → 写 PNG
                                               成功 → enqueue LOW: status='ok' → ws 'sync_status_changed'
                                               失败 → 退避重试 → 终究失败 → status='failed' → 广播
```

### 3.3 批量操作路径（两阶段 + 增量提交）

移动和删除都走 **preflight → execute**。**v2 关键变化**：execute 阶段不再"全部完成才一次性写 DB"，而是**操作一个、记录一个**——每成功移动/删除一个物理文件，立即向 `WriteQueue` 入队（MID 优先级）一条更新。即便进程在批中崩溃，磁盘现状与索引完全一致。

```
前端 BulkBar                    后端                              文件系统

POST bulk/move/preflight   ───► service.preflight_move
  { selection, target }              │
                                     ├─ repo.resolve_selection
                                     ├─ paths.assert_inside_root
                                     ├─ shutil.disk_usage
                                     ├─ listdir(target) 冲突探测 + 自动改名
                                     └─ PLAN_STORE.put(plan)（TTL 5 分钟）
  ◄────────────  返回 MovePlan（未触碰任何文件）

用户在 MovePicker 预览 / 覆盖改名

POST bulk/move/execute     ───► service.execute_move
  { plan_id, rename_overrides }      │
                                     ├─ _re_check_conflicts
                                     ├─ for each mapping in plan:           ┌──────────────────────────────────────┐
                                     │     try:                             │  增量提交（Per-Op Commit）           │
                                     │       os.replace / copy2+unlink ────►│ 物理操作成功 → 立刻入队              │
                                     │       repo.enqueue_write(MID,        │ DB 与磁盘永远不会偏离超过 1 条记录   │
                                     │             move_op(id, new_path))   │ 崩溃后重启走 delta_scan 自愈         │
                                     │       ws_hub.broadcast_progress(i+1) └──────────────────────────────────────┘
                                     │     except FileError:
                                     │       记录失败项；继续下一条
                                     │
                                     └─ 收尾：
                                          ws_hub.broadcast('bulk.completed', {ok, failed})
                                          gallery_audit.log 写最终摘要
```

> bulk_delete 同理：每删除一个文件立即入队 `delete_op(id)`；进程被 kill 也只损失"还没物理删除"的尾部，已删文件已落 DB。

---

## 4. 关键组件交互方式

### 4.1 装配顺序（冷启动）

1. ComfyUI 启动 → 扫描 `custom_nodes/` → `import ComfyUI-XYZNodes` → 触发 `gallery/__init__.py`。
2. `gallery/__init__` 同步执行（耗时 < 50 ms，NFR-1）：
   - 打开 / 创建 `gallery.sqlite`，运行 `db.migrate()`（含 v3 迁移：新增 `metadata_sync_status` 列）；
   - 读 `gallery_config.json`；
   - 注册 HTTP + WS 路由。
3. 启动后台线程（按依赖顺序）：
   1. **`repo.WriteQueue` 写入者线程**（首先启动，所有写依赖它）；
   2. `metadata_sync` Worker 线程（消费 pending）；
   3. `thumbs` ProcessPool（含 LIFO 调度协程）；
   4. `indexer` 主线程协调器（含解析 ProcessPool）；
   5. `watcher` Observer + 心跳线程（30 s 周期 delta_scan）；
   6. `thumbnail_cache` LRU janitor、`image.last_accessed` 刷盘任务。
4. 后台开始 delta-scan；HTTP 端立刻可用，`/index/status` 返回 `scanning: true`。

### 4.2 请求调用链（典型读请求）

```
aiohttp request
   └─ routes.list_images              ← 只解析 query / 校验形状
        └─ service.list_images        ← 编排
             ├─ vocab.normalize_prompt(positive_tokens)
             ├─ repo.resolve_tag_ids(tokens)              ← 直接走读连接
             ├─ repo.build_tag_and_query(...)
             ├─ await loop.run_in_executor(repo.execute_read)
             └─ 序列化为 ImageRecord[]（含 sync_status 字段）
```

读取**不进** WriteQueue，直接走 WAL 下的并发只读连接；不会被写阻塞。

### 4.3 写请求链（以 PATCH tag 为例）

```
routes.patch_image
   └─ service.update_image(id, patch)
        ├─ repo.get_image(id)                                        读
        ├─ paths.assert_inside_root(image.path)
        ├─ vocab.normalize_tags(patch.tags)
        │
        ├─ future = repo.enqueue_write(                              ★ HIGH 优先级
        │       priority=HIGH,
        │       op=UpdateImageOp(
        │           image_id=id,
        │           patch=patch,
        │           also_set={'metadata_sync_status': 'pending'}
        │       ))
        ├─ await future                                              ← 串行写者执行该事务
        │
        ├─ ws_hub.broadcast('image.updated', {...})                  ← 立即返回前端
        │
        └─ metadata_sync.notify(image_id)                            ← 唤醒同步 Worker
                 │
                 │ （异步，不阻塞响应）
                 ▼
            metadata.write_xyz_chunks(...)  → 成功
                 │
                 └─ repo.enqueue_write(LOW, SetSyncStatusOp(id, 'ok'))
                         └─ ws_hub.broadcast('image.sync_status_changed', {id, 'ok'})
```

**新顺序**：DB 先（HIGH） → 立即广播 + 200 → PNG 后（异步） → 状态回写（LOW） → 二次广播。

> 与 v1 的差异：v1 要求"PNG 写失败回滚 DB"，导致 PATCH 响应延迟受 PNG IO 影响、且 PNG 是慢且易失败的环节。v2 把 DB 作为唯一事实来源，PNG 是衍生物；用户感知的写延迟降到一次 DB 事务（~ms 级）。

### 4.4 多 Tab 一致性

- 任何写操作的唯一真相是 `WriteQueue` 串行后的 SQLite 事务；多 Tab 并发写在队列里自然串行。
- 写完成后 `ws_hub` 向所有连接广播；发起方 Tab 走"乐观 UI + 权威确认"。
- 短暂 WS 断连用焦点对账兜底；对账时除拉 `/index/status` 与 `/images`，**还需重新拉取可视图片的 `sync_status`**，确保失败徽标不丢。

### 4.5 批量操作的增量提交语义

- **入队粒度 = 单个文件**。每条物理操作成功后立即 `enqueue_write(MID, ...)`。
- `WriteQueue` 在两个用户 PATCH（HIGH）之间会插入若干 MID 批量 op，保证用户交互不被批量饿死。
- 前端进度条**以"WS 收到的 progress 事件数"驱动**，与 DB 已确认条数一一对应；不再展示"伪进度"。
- 崩溃恢复：重启后 `indexer.delta_scan` 在 30 s 内自动发现"DB 仍指向旧路径但磁盘已无该文件 / 新路径有未索引文件"，补齐差异。

### 4.6 WriteQueue 与 Single Writer（核心组件）

**位置**：`repo.py` 内部，对外暴露 `enqueue_write(priority, op) -> Future` 与若干 `*_op` 工厂。

**结构**：

```
                ┌──────────────────────────────────────────────┐
                │           repo.WriteQueue (in-mem)           │
                │                                              │
   生产者：     │   PriorityQueue<(priority, seq, op, future)> │
   - service    │                                              │
   - indexer    │   3 个优先级：HIGH(0) / MID(1) / LOW(2)      │
   - meta_sync  │   FIFO 二级序号（seq）保证同优先级保序        │
   - vocab      │                                              │
                └────────────────────┬─────────────────────────┘
                                     │ get()
                                     ▼
                ┌──────────────────────────────────────────────┐
                │      Single Writer Thread (写连接独占)        │
                │                                              │
                │   while True:                                │
                │     batch = drain_until(deadline=5ms,        │
                │                         max=64,              │
                │                         only_same_priority)  │
                │     with conn.tx():                          │
                │       for op in batch: op.apply(conn)        │
                │     for op in batch: op.future.set_result()  │
                └──────────────────────────────────────────────┘
```

**优先级语义**

| 优先级 | 来源 | 典型 op |
| --- | --- | --- |
| HIGH | `service` 处理用户交互 | PATCH 收藏/标签、单条移动、删除单条 |
| MID  | `service` 的批量增量提交 | bulk_move 单条记录、bulk_delete 单条记录 |
| LOW  | `indexer` 全量/增量索引、`metadata_sync` 状态回写、`vocab` `usage_count` ± | upsert image、set sync_status、tag count 累加 |

**饥饿防护**：连续处理 LOW 时，每 N=200 条强制 yield 一次让 HIGH/MID 抢占；同优先级走 FIFO 不会插队。

**事务批量**：写者每次 `drain` 至多 64 条**同优先级**操作合并到一个事务，吞吐 × 5–10。HIGH 单条操作不等待，立即提交，保证用户感知延迟。

**异常隔离**：单条 op 抛错不影响同事务其余 op 吗？——为保证可观测性，**每条 op 在子保存点（SAVEPOINT）内执行**，单条失败 rollback 该 savepoint 并把异常塞进对应 future，其余 op 正常 commit。

### 4.7 Indexer 的并发模型（解析并行 / 写入串行）

```
                 ┌────────────────────────────────────────────┐
                 │                Indexer 主线程              │
                 │                                            │
   待处理事件 ──►│   submit(file_path) → ProcessPool          │
                 │              │                             │
                 │              │ (2~4 workers, CPU 密集)     │
                 │              ▼                             │
                 │   ┌──────────────────────────┐             │
                 │   │ Worker 进程：             │             │
                 │   │   - PIL 读 PNG 头         │             │
                 │   │   - 抽 tEXt/iTXt 块       │             │
                 │   │   - vocab.normalize       │             │
                 │   │   - 计算 fingerprint      │             │
                 │   │ 返回 ParsedRecord         │             │
                 │   └─────────────┬─────────────┘             │
                 │                 │ as_completed             │
                 │                 ▼                          │
                 │   汇总成 LOW 优先级 op 入 WriteQueue       │
                 │   （UpsertImageOp / TagDiffOp / PromptOp） │
                 └────────────────────────────────────────────┘
```

- **CPU 阶段并行**：`ProcessPoolExecutor(max_workers=min(4, cpu_count-1))`；绕过 GIL。
- **IO/写阶段串行**：所有解析结果回到主线程，通过 `repo.WriteQueue` 串行提交。
- **背压**：主线程维护 in-flight 上限（默认 256），超过则暂停喂入 ProcessPool。

#### 4.7.2 FTS5 分词器配置

`db.py` 中创建 `image_fts` 时**显式指定**：

```
tokenize = "unicode61
            remove_diacritics 2
            tokenchars '_-+.()[]{}<>:/\\@#'
            separators ', \t\n'"
```

理由：

- 默认分词会把 `(masterpiece:1.2)`、`embedding:foo`、`<lora:xxx:0.7>` 等切散，搜索 `lora:xxx` 失败。
- 上述 `tokenchars` 把 SD/ComfyUI prompt 中常见的标点纳入 token 内部，保留权重括号和路径分隔符的语义。
- `remove_diacritics 2` 兼容多语言用户输入。
- 分词器变更**必须伴随 schema 版本升级 + 全量 reindex 触发**（`db.migrate` 检测到差异时排队 LOW 优先级 reindex 任务）。

### 4.8 metadata_sync Worker（异步最终一致性）

```
                 ┌──────────────────────────────────────────────┐
                 │            metadata_sync.Worker              │
                 │                                              │
   触发源：       │   ① 主动通知：service 写 DB 后 notify(id)    │
                 │   ② 周期巡检：每 60 s SELECT WHERE status     │
                 │                = 'pending' OR (= 'failed'    │
                 │                AND retry_count < 3 AND       │
                 │                next_retry_at <= now)         │
                 │                                              │
                 │   for each pending id:                       │
                 │     try:                                     │
                 │       metadata.write_xyz_chunks(...)         │  IO 密集
                 │       enqueue_write(LOW, SetSyncOk(id))      │
                 │       ws_hub.broadcast('sync_status_changed')│
                 │     except IOError as e:                     │
                 │       retry_count += 1                       │
                 │       next_retry_at = now + 2^n · 5s         │
                 │       enqueue_write(LOW, SetSyncFailed(...)) │
                 └──────────────────────────────────────────────┘
```

**Schema 影响**（v3 迁移）：

| 列 | 类型 | 默认 | 说明 |
| --- | --- | --- | --- |
| `metadata_sync_status` | TEXT | `'ok'` | `pending` / `ok` / `failed` |
| `metadata_sync_retry_count` | INT | 0 | 失败累计次数 |
| `metadata_sync_next_retry_at` | INT | NULL | unix ts，用于退避调度 |
| `metadata_sync_last_error` | TEXT | NULL | 最近一次错误信息（截断 256） |

**索引**：`CREATE INDEX idx_image_sync ON image(metadata_sync_status) WHERE metadata_sync_status != 'ok'`（部分索引，规模再大也 O(failed)）。

**前端表现**：`ThumbCard` / `DetailView` 根据 `sync_status` 显示徽标；`failed` 时提供"重试同步"按钮 → 命中 `POST /image/{id}/resync` 把 `retry_count` 清零、状态改回 `pending`。

### 4.9 Thumbs 的 LIFO 视口优先

```
                 ┌────────────────────────────────────────────┐
                 │             thumbs.Scheduler                │
                 │                                            │
   请求来源：     │   stack[VIEWPORT] : LIFO（视口请求）       │
   - HTTP /thumb │   queue[BACKGROUND]: FIFO（冷启动批量）    │
   - 冷启动批量  │                                            │
                 │   调度策略：                               │
                 │     while True:                            │
                 │       if stack[VIEWPORT]: pop()            │
                 │       elif queue[BACKGROUND]: get()        │
                 │       else: sleep                          │
                 │                                            │
                 │   ProcessPool 并发执行                     │
                 └────────────────────────────────────────────┘
```

- **LIFO 的意义**：用户滚动很快时，最早请求的缩略图往往已滚出视口，让最新请求先做才符合直觉。
- **去重**：同一个 image_id 在两个队列里只保留最新一次请求，旧请求作废（避免重复生成）。
- **取消**：用户请求附 `AbortController`；`/thumb` handler 注册取消回调，调度器看到取消标记直接跳过。
- **背景任务限速**：冷启动批量只填 BACKGROUND 队列；视口非空时 BACKGROUND worker 立即让出（`worker_pool` 中固定保留 1 个 slot 给 VIEWPORT，防止 BACKGROUND 把池占满）。

### 4.10 Watcher 心跳与补偿扫描

```
                 ┌────────────────────────────────────────────┐
                 │            watcher 模块（v2）              │
                 │                                            │
   ┌──────────┐  │   ① 主路径：watchdog Observer → Coalescer  │
   │ watchdog │──┼─► 250 ms debounce → 50 条/批 → indexer     │
   └──────────┘  │                                            │
                 │   ② 心跳路径：HeartbeatThread              │
   ┌──────────┐  │      while not stop:                       │
   │ Timer 30s│──┼─►     for root in registered_roots:        │
   └──────────┘  │           indexer.delta_scan(root,         │
                 │                              mode='light') │
                 │      （仅 (size, mtime_ns) 比对，不读元数据）│
                 │                                            │
                 │   ③ 自检日志：                             │
                 │      每 5 分钟把 (events_seen, events_     │
                 │      coalesced, scans_done, drifts_found)  │
                 │      写入 gallery_audit.log                │
                 └────────────────────────────────────────────┘
```

- **light delta_scan**：只 `os.scandir` + 与 DB `(size, mtime_ns)` 比对，不调用 metadata 解析；发现差异才入队真正的 indexer 事件。在 5 万规模下单次 < 200 ms。
- **drift 报告**：补偿扫描发现的差异通过 `index.drift_detected` WS 事件告知前端（隐藏在调试面板，便于诊断 watchdog 不可靠的环境，如某些 SMB 挂载）。
- **作用**：覆盖 watchdog 已知的丢事件场景——网络盘、容器卷、休眠/唤醒、Coalescer 溢出降级遗漏。

---

## 5. 技术选型

### 5.1 后端

| 类别 | 选择 | 理由 |
| --- | --- | --- |
| 语言 / 运行时 | Python ≥ 3.10 | ComfyUI 自身要求；`match` 语法、`|` 类型联合对代码质量有益。 |
| HTTP / WS 服务器 | **aiohttp**（复用 ComfyUI 的 `PromptServer.instance`） | 零新增端口（C-7、NFR-18）。 |
| 持久化 | **SQLite（stdlib）+ FTS5** | 单文件、零运维；WAL + 单写者模型下并发读 + 串行写延迟可预测。 |
| SQLite 模式 | `journal_mode=WAL`、`synchronous=NORMAL`、`temp_store=MEMORY`、`mmap_size=256 MiB`、**`busy_timeout=5000`** | 单写者后 busy 几乎不发生，busy_timeout 仅作兜底。 |
| **写入并发** | **WriteQueue 单消费者线程**（自研，§4.6） | 杜绝 `database is locked`；优先级保证用户交互延迟可控。 |
| **元数据同步** | **`metadata_sync` 异步 Worker**（自研，§4.8） | 解耦慢 IO 与用户响应；DB 是事实来源。 |
| 图像处理 | **Pillow** | — |
| 缩略图并发 | `ProcessPoolExecutor(≤ min(4, cpu_count))` + **LIFO 调度器** | 视口优先；冷启动不阻塞用户。 |
| 索引解析并发 | `ProcessPoolExecutor(≤ min(4, cpu_count-1))` | CPU 密集解析并行，结果汇总仍单写。 |
| 文件系统监听 | **watchdog** + 自研 Heartbeat | 30 s 周期 delta_scan 兜底丢事件场景。 |
| 路径处理 | `pathlib` + 统一 POSIX 字符串存储 | — |
| PNG 元数据 | 手写 `tEXt` / `iTXt` chunk 读写 | 精确控制（C-6）。 |
| 哈希 | `xxhash`（可选）；缩略图 key 用 `hashlib.sha1` | — |

**显式不选**：

- 异步 ORM —— 与单写者模型语义重叠且更难审计 SQL。
- Redis / 外部 MQ —— WriteQueue 内存优先级队列已胜任，重启重置符合"事件不持久"语义。
- 多写者线程 + 互斥锁 —— v1 经验表明 SQLite 的锁等待在批量场景下尾延迟极差。

### 5.2 前端

| 类别 | 选择 | 理由 |
| --- | --- | --- |
| 框架 | **Vue 3，importmap ESM** | 零 build step；体积小。 |
| 备选 | 预编译 React + Vite | — |
| 路由 | Hash 路由（自研） | — |
| 样式 | 原生 CSS + CSS variables | — |
| 状态 | Vue 3 `reactive` + 自实现 store | — |
| HTTP | `fetch` + AbortController | 配合缩略图 LIFO 调度的取消语义。 |
| WS | 原生 `WebSocket` + 指数回退 + onfocus 对账 | — |
| 虚拟滚动 | 自实现 | — |
| 图片加载 | `<img loading="lazy">` + `IntersectionObserver` | — |

### 5.3 开发 / 交付

| 类别 | 选择 |
| --- | --- |
| 测试 | `pytest`；新增单元：`WriteQueue` 优先级与饥饿防护、`metadata_sync` 重试退避、`bulk_move` 中途崩溃恢复、`watcher.Heartbeat` 漂移检测、`thumbs.Scheduler` LIFO 抢占。 |
| Lint | `ruff`、ESLint；自定义 ruff 规则禁止 `repo` 之外出现裸 `cursor.execute` 写语句。 |
| 日志 | Python `logging` → 轮转 `gallery_audit.log` + stderr。 |

---

## 6. MVP 路径（优先级分级）

> v2 调整：将"WriteQueue + Single Writer"提前到 L1（基础底座）；"metadata_sync 异步化"在 L2 引入；"批量增量提交"与"watcher 心跳"在 L3 引入；"分词器/LIFO/进程池"在 L4 调优。

### MVP-L0：骨架可联通（~1 天）

1. `gallery/__init__.py` 不崩溃；`GET /xyz/gallery` 返回占位 HTML。
2. `gallery_topbar.js` 顶栏按钮。
3. `gallery_data/` 目录创建。

**交付**：点击按钮 → 新 Tab → "Hello Gallery"。

### MVP-L1：最小只读回路 + 写入底座（~4–6 天）

1. `db.py` Schema v1 + 基础迁移。
2. **`repo.py` 的 `WriteQueue` 与 Single Writer 线程**（即使第一版只有 indexer 一个生产者，也走它，避免后期改造）。
3. `metadata.py` 读 PNG。
4. `indexer.py` 冷启动扫描 + 指纹短路；解析**先单线程**，写入走 WriteQueue。
5. `thumbs.py` 按需生成 + 简单磁盘缓存（先 FIFO，LIFO 留给 L4）。
6. `repo.py` 三个查询：列表、详情、目录树。
7. `routes.py`：`/images`、`/image/{id}`、`/thumb/{id}`、`/raw/{id}`、`/folders`。
8. 前端：SPA 骨架 + VirtualGrid + ThumbCard + 基础过滤 + DetailView。

**交付**：5 000 张 `output/`，冷启动 < 10 s；DB 永不出现 lock 错误。

### MVP-L2：可编辑 + 实时 + 异步同步（~4–6 天）

1. `vocab.py` `normalize_prompt`。
2. Schema v2：tag/prompt 词表 + 迁移；**v3：新增 `metadata_sync_status` 等列**。
3. `metadata.py` 写路径（write-temp + rename）。
4. **`metadata_sync.py` Worker + 周期巡检 + WS `sync_status_changed`**。
5. `PATCH /image/{id}` 走 `enqueue_write(HIGH)` + 立即广播 + 异步 PNG。
6. `watcher.py` + `Coalescer` + `ws_hub`。
7. 前端：收藏/标签编辑、**`ThumbCard` 同步状态徽标**、WS 订阅、focus 对账（含状态字段）。
8. tag filter（AND）+ Autocomplete + `/vocab/tags`。

**交付**：外部新图 ≤ 2 s 出现；PATCH 响应延迟与 PNG IO 无关；PNG 写失败可见、可重试。

### MVP-L3：批量操作 + 心跳兜底（~3–4 天）

1. `Selection` 包络（前端 + 后端 SQL 展开）。
2. `POST /bulk/favorite`、`POST /bulk/tags`（HIGH 优先级单条入队）。
3. **两阶段 move + 增量提交**（每条物理操作后立即 `enqueue_write(MID)`）。
4. **批量 delete + 增量提交 + ConfirmModal + audit log**。
5. **`watcher.HeartbeatThread`：30 s 周期 light delta_scan**。
6. 前端 BulkBar 进度条以 WS progress 事件驱动。

**交付**：1 000 张批量移动中途 kill 进程，重启后 30 s 内 DB 与磁盘完全一致；用户 PATCH 不被批量饿死。

### MVP-L4：规模优化与长尾（按需）

1. **`thumbs.Scheduler` LIFO 视口优先 + 取消**（缩略图目录逼近 2 GB 时 LRU 淘汰也在此层）。
2. **`indexer` 元数据解析 ProcessPool（2~4 worker）**。
3. **FTS5 分词器显式配置 + 触发全量 reindex**（在 prompt/标签搜索体感不佳时启用）。
4. tag-AND / prompt-AND 自适应查询（`EXISTS` / `INTERSECT`）。
5. Timeline 布局。
6. 自定义根目录管理 UI。
7. `/index/rebuild` 端点。
8. dedupe 视图。
9. Prompt autocomplete + `/vocab/prompts`。

### MVP 依赖图

```
L0 骨架
 └─► L1 只读回路 + WriteQueue 底座 ────────────────► 解决"看图" + 杜绝写竞争
      └─► L2 编辑 + 实时 + 异步同步 ──────────────► 解决"管理" + 写延迟解耦
           └─► L3 批量操作 + 心跳兜底 ────────────► 解决"规模化操作" + 不丢事件
                └─► L4 性能与长尾（LIFO/进程池/分词器） ► 随规模增长投入
```

---

## 附录 A：模块依赖速查

```
routes.py       ──► service.py ──► repo.py    ──► db.py
                         │              │
                         │              └─► (sqlite3, WriteQueue 内嵌)
                         │
                         ├──► indexer.py ──► metadata.py ──► (Pillow)
                         │         │
                         │         ├──► vocab.py
                         │         ├──► (ProcessPool 解析)
                         │         └──► repo.enqueue_write(LOW)
                         │
                         ├──► metadata_sync.py ──► metadata.py
                         │         │
                         │         └──► repo.enqueue_write(LOW)
                         │
                         ├──► watcher.py ──► (watchdog) + Heartbeat
                         │         │
                         │         └──► indexer.py
                         │
                         ├──► thumbs.py  ──► (Pillow + ProcessPool, LIFO Scheduler)
                         │
                         ├──► paths.py   ──► folders.py
                         │
                         └──► ws_hub.py

  —————— 约束 ——————
  ① 箭头单向，不允许反向依赖（尤其 repo 不得 import service）。
  ② routes 只知 service；UI 逻辑永远不下沉到 repo。
  ③ vocab / metadata / paths 是纯函数模块，任何层可用。
  ④ ★ 所有写入必须经 repo.enqueue_write(...)；ruff 自定义规则强制。
  ⑤ ★ metadata_sync 只通过 LOW 优先级写状态；不发起业务写。
```

## 附录 B：关键性能预算速查

| 环节 | 预算 | 来源 / 备注 |
| --- | --- | --- |
| ComfyUI 冷启动被 gallery 阻塞 | ≤ 50 ms | NFR-1 |
| Gallery 页首屏可交互（20 k 图） | < 1 s | NFR-2 |
| 过滤 / 排序 P95（50 k 图） | < 100 ms | NFR-3 |
| 自动补全 P95 | < 30 ms | NFR-4 |
| 网格滚动 | 60 fps | NFR-5 |
| 前端 DOM 节点上限 | 视口 × 3 | NFR-6 |
| 后端常驻内存 | ≤ 300 MB | NFR-7 |
| 文件系统事件 → UI | ≤ 2 s | FR-20（事件路径） |
| **Watchdog 漏事件 → UI**（兜底） | ≤ 30 s | ★ 心跳周期，§4.10 |
| **PATCH 响应（不含 PNG）** | P95 < 50 ms | ★ DB 写 + 广播即返回 |
| **PNG 同步延迟** | 中位数 < 1 s；失败重试退避 5/10/20 s | ★ §4.8 |
| **WriteQueue 排队延迟（HIGH）** | P95 < 20 ms（即使 LOW 队列 ≥ 1 万） | ★ 饥饿防护，§4.6 |
| **缩略图视口请求 P95** | < 200 ms（即使背景批量进行中） | ★ LIFO，§4.9 |
| **bulk_move/delete 单条吞吐** | ≥ 200 op/s | 增量提交 + 批量事务合并 |
| **崩溃恢复后 DB-磁盘漂移** | 0 条（增量提交） + ≤ 30 s 检出（心跳） | §4.5 + §4.10 |

每完成一个 MVP 层都应当照表回归测量；任一指标跌破预算视为 L4 优化的触发器。

---

## 附录 C：核心组件伪代码骨架（设计层，非实现）

> 仅描述控制流与不变式，便于评审与后续实现对照；非可运行代码。

### C.1 `repo.WriteQueue` 写入循环

```
class WriteQueue:
    HIGH, MID, LOW = 0, 1, 2
    LOW_BATCH_YIELD = 200   # 处理 N 条 LOW 后强制 yield 检查 HIGH/MID
    DRAIN_DEADLINE_MS = 5
    MAX_BATCH = 64

    def enqueue_write(priority, op) -> Future:
        future = Future()
        seq = next(self._seq_counter)            # 全局单调，保证同优先级 FIFO
        self._pq.put((priority, seq, op, future))
        return future

    # ===== 单一写入者线程 =====
    def _writer_loop():
        conn = open_write_connection()           # WAL 模式、独占的写连接
        low_streak = 0
        while not self._stop:
            first = self._pq.get(block=True)     # 阻塞直到有任务
            batch = [first]
            current_priority = first.priority
            deadline = now() + DRAIN_DEADLINE_MS

            # 同优先级合并：在很短的窗口里继续吸纳同级 op
            while len(batch) < MAX_BATCH and now() < deadline:
                try:
                    nxt = self._pq.get(timeout=remaining_to(deadline))
                except Empty:
                    break
                if nxt.priority != current_priority:
                    self._pq.put(nxt)            # 不同优先级回放
                    break
                batch.append(nxt)

            # 饥饿防护：连续 LOW 太久就强制 yield 一次（仅做一个空 select 让出）
            if current_priority == LOW:
                low_streak += len(batch)
                if low_streak >= LOW_BATCH_YIELD:
                    low_streak = 0
                    if self._has_higher_priority_waiting():
                        self._pq.put(*batch)      # 放回，先服务高优先级
                        continue
            else:
                low_streak = 0

            # 单事务执行整批；每条 op 在 SAVEPOINT 内，单条失败不污染整批
            with conn.tx():
                for item in batch:
                    sp = conn.savepoint()
                    try:
                        result = item.op.apply(conn)
                        sp.release()
                        item.future.set_result(result)
                    except Exception as e:
                        sp.rollback()
                        item.future.set_exception(e)
            # commit 后，订阅者（service / metadata_sync）可基于 future 继续广播
```

**不变式**

1. 任何时刻**只有一个线程**对写连接调用 `execute`。
2. 同优先级严格 FIFO（`seq` 单调）。
3. HIGH 不会被任何积压的 LOW 阻塞超过一个事务的时间（≤ 几 ms）。
4. 单条 op 失败 → 该 op `future.exception()`；其余 op 正常生效。
5. 异常永不沉默：所有异常要么进入 future，要么被日志记录后线程**重启**（守护线程模式）。

### C.2 `service.execute_move` 增量提交

```
def execute_move(plan_id, rename_overrides):
    plan = PLAN_STORE.get(plan_id) or raise NotFound
    _re_check_conflicts(plan)                    # 复核磁盘现状
    overrides = apply_overrides(plan, rename_overrides)

    progress = {ok: 0, failed: 0, total: len(plan.mappings)}
    futures = []                                  # 跟踪入队的写 op，最后等齐

    for mapping in plan.mappings:                 # 顺序处理，便于推进进度
        try:
            # 1) 先做物理操作；同盘走 os.replace 原子，跨盘走 copy2 + unlink
            do_physical_move(mapping.src, mapping.dst)

            # 2) 物理成功后立刻入队 DB 更新（MID 优先级）
            fut = repo.enqueue_write(
                priority=MID,
                op=MoveImageOp(
                    image_id=mapping.image_id,
                    new_path=mapping.dst,
                    also_set={'metadata_sync_status': 'pending'}  # 路径变了，PNG 需要重写元数据
                )
            )
            futures.append(fut)
            progress.ok += 1

            # 3) 即时广播进度（前端进度条由此驱动）
            ws_hub.broadcast('bulk.progress', {plan_id, **progress})

        except FileError as e:
            progress.failed += 1
            audit.log('move_failed', mapping, e)
            ws_hub.broadcast('bulk.progress', {plan_id, **progress})
            continue                              # 不中断整个批

        # 让出：在大批量中插入"协作点"，给 HIGH 优先级（用户交互）抢占机会
        if progress.ok % 50 == 0:
            cooperative_yield()

    # 等待已入队的 DB 更新全部 commit（容忍单条失败：检查 future.exception()）
    for fut in futures:
        try:
            fut.result(timeout=30)
        except Exception as e:
            audit.log('db_update_failed_post_move', e)

    # 唤醒 metadata_sync 处理因路径变化而产生的 pending（路径在元数据中无影响时也无害）
    metadata_sync.notify_many([m.image_id for m in plan.mappings])

    ws_hub.broadcast('bulk.completed', {plan_id, **progress})
    audit.log('move_completed', plan_id, progress)
    return progress
```

**不变式**

1. **每一次 DB 与磁盘的状态偏离 ≤ 1 条记录**（"先物理后入队"且入队不等待 commit）。即便此刻进程崩溃，重启后 `delta_scan`（30 s 内由心跳触发）能从磁盘事实重新追平 DB。
2. 单条失败不阻断整批；失败明细落 `gallery_audit.log`。
3. 用户在批量进行中发起 PATCH 不会被饿死（HIGH 优先级 + 协作点让出）。
4. `metadata_sync_status` 在路径变更时统一标 `pending`，由后台 Worker 重新写入新路径下的 PNG 块；UI 通过徽标可观察。
5. `bulk_delete` 走相同模式：物理 `unlink` 成功 → 立即 `enqueue_write(MID, DeleteImageOp(id))` → 广播进度。

---

> **变更清单（v1 → v2）速览**
>
> - 新增模块 `metadata_sync.py`；`repo.py` 内嵌 `WriteQueue` + Single Writer。
> - Schema v3 迁移：新增 `metadata_sync_status / retry_count / next_retry_at / last_error` 与部分索引。
> - `service.update_image`：取消"PNG 失败回滚 DB"，改为"DB 即事实 + 异步重试 + 状态可见"。
> - `service.execute_move` / `bulk_delete`：批量"操作一个、记录一个"，增量入队 MID。
> - `watcher.py`：新增 `HeartbeatThread`（30 s 周期 `delta_scan` light 模式）。
> - `thumbs.py`：新增 `Scheduler`（VIEWPORT LIFO 优先于 BACKGROUND FIFO）。
> - `indexer.py`：解析阶段 `ProcessPoolExecutor(2~4 worker)`，写入仍走 `WriteQueue`。
> - `db.py`：FTS5 显式 `tokenize` 配置；分词器变更触发全量 reindex。
> - WS 事件新增 `image.sync_status_changed`、`bulk.progress`、`bulk.completed`、`index.drift_detected`。
> - 性能预算附录新增：HIGH 排队延迟、PNG 同步延迟、视口缩略图延迟、崩溃恢复漂移上限。
