# XYZ Image Gallery — TASKS

> 基于 `PROJECT_SPEC.md` 与 `ARCHITECTURE.md` 拆解的开发任务清单。
> 每个任务粒度 1–2 小时，定义清晰的输入 / 输出与可独立测试的验收标准，
> 标注依赖、优先级（P0 / P1 / P2）和是否属于 MVP。
>
> **MVP 范围 = `MVP-L0` + `MVP-L1` + `MVP-L2` + `MVP-L3`**（共 25 个任务标记为 ✅ MVP）。
> L4（性能与长尾）任务在文末以 P2 列出，**非 MVP**，按规模触发再启动。
>
> 图例：
> - 优先级：**P0** 阻塞下游 / 不做就没法继续；**P1** 必做但可短暂滞后；**P2** 体验或规模优化
> - MVP：✅ 必须完成 / ❌ 非必须
> - 依赖：列出**直接前置**任务 ID

---

## 总览（MVP 关键路径）

```
L0  ─►  L1（只读回路 + WriteQueue 底座）  ─►  L2（编辑 + 实时 + 异步同步）  ─►  L3（批量 + 心跳）
```

| 阶段 | 任务 ID | 名称 | 优先级 | MVP |
| --- | --- | --- | --- | --- |
| L0 | T01 | gallery 包骨架 + 数据目录引导 | P0 | ✅ |
| L0 | T02 | 顶栏按钮 + 占位路由 | P0 | ✅ |
| L1 | T03 | `db.py` Schema v1 + 迁移框架 + PRAGMA | P0 | ✅ |
| L1 | T04 | `repo.WriteQueue` + Single Writer | P0 | ✅ |
| L1 | T05 | `paths.py` + `folders.py` + 配置持久化 | P0 | ✅ |
| L1 | T06 | `metadata.py` PNG 读路径 | P0 | ✅ |
| L1 | T07 | `indexer.py` 冷启动扫描 + 指纹短路 | P0 | ✅ |
| L1 | T08 | `thumbs.py` 按需生成 + `thumbnail_cache` 表 | P0 | ✅ |
| L1 | T09 | `repo.py` 读 API + 游标分页 + 过滤 SQL | P0 | ✅ |
| L1 | T10 | `routes.py` 只读端点（页 / 图 / 缩略图 / 原图 / 目录） | P0 | ✅ |
| L1 | T11 | SPA shell + 路由 + `api.js` | P0 | ✅ |
| L1 | T12 | `MainView`：`FolderTree` + 过滤器面板 | P0 | ✅ |
| L1 | T13 | `VirtualGrid` + `ThumbCard` | P0 | ✅ |
| L1 | T14 | `DetailView` + 缩放 + `/neighbors` | P0 | ✅ |
| L2 | T15 | `vocab.normalize_prompt` + Schema v2 词表 | P0 | ✅ |
| L2 | T16 | Schema v3 迁移：`metadata_sync_*` 列 + 部分索引 | P0 | ✅ |
| L2 | T17 | `metadata.py` 写路径 + `metadata_sync.py` Worker + 重试 | P0 | ✅ |
| L2 | T18 | `ws_hub.py` + WebSocket 路由 | P0 | ✅ |
| L2 | T19 | `PATCH /image/{id}` + `/resync` + `service.update_image` | P0 | ✅ |
| L2 | T20 | `watcher.py` Observer + `Coalescer` | P0 | ✅ |
| L2 | T21 | `/vocab/*` 端点 + `Autocomplete` + tag / prompt 过滤 | P1 | ✅ |
| L2 | T22 | 前端：编辑 UI + 同步徽标 + WS 订阅 + 焦点对账 | P0 | ✅ |
| L3 | T23 | `Selection` 包络 + `/bulk/favorite` + `/bulk/tags` + `BulkBar` | P1 | ✅ |
| L3 | T24 | 两阶段 bulk move + `MovePicker` + 增量提交 | P1 | ✅ |
| L3 | T25 | bulk delete + `ConfirmModal` + 审计日志 + `HeartbeatThread` | P1 | ✅ |
| L4 | T26 | `thumbs.Scheduler` LIFO 视口优先 + 取消 + LRU 淘汰 | P2 | ❌ |
| L4 | T27 | `indexer` 元数据解析 ProcessPool 化 | P2 | ❌ |
| L4 | T28 | FTS5 显式分词器 + tag-AND / prompt-AND 自适应查询 | P2 | ❌ |

---

## L0 — 骨架可联通

### T01 · gallery 包骨架 + 数据目录引导  ✅ MVP · P0

**输入**：现有 `ComfyUI-XYZNodes/__init__.py`；`PROJECT_SPEC §6.3`、`ARCHITECTURE §1 / §3.1 / §4.1`。

**输出**：
- 新建 `gallery/__init__.py`（装配入口，幂等），导入即：
  - 创建 `gallery_data/` 目录（不存在则建），含 `thumbs/` 子目录；
  - 创建空 `gallery.sqlite` 占位（不建表，留给 T03）；
  - 暴露 `setup(app)` / `start_background_services()` 钩子函数（先空实现，后续任务填充）；
- `ComfyUI-XYZNodes/__init__.py` 在加载现有节点之后调用 `gallery.setup(...)`，**异常被捕获并记日志**，绝不阻断现有节点。

**依赖**：无

**测试**：
1. 重启 ComfyUI，主界面节点全部可用；
2. `gallery_data/`、`gallery_data/thumbs/`、`gallery.sqlite` 自动出现；
3. 第二次启动是幂等的（无重复创建错误）；
4. 故意让 `gallery.setup` 抛错，ComfyUI 仍正常启动，日志可见错误。

---

### T02 · 顶栏按钮 + 占位路由  ✅ MVP · P0

**输入**：`PROJECT_SPEC FR-1 / FR-2`；`ARCHITECTURE §1 / §2.2`。

**输出**：
- `js/gallery_topbar.js`：通过 `app.registerExtension` 在顶栏注入按钮，标签 `Gallery`，带图标（用现成的 SVG 即可）；点击 `window.open('/xyz/gallery')`；
- `gallery/routes.py`：注册 `GET /xyz/gallery` 返回最简 HTML，文本 `Hello Gallery`；
- `gallery/__init__.setup()` 调用 `routes.register(PromptServer.instance)`。

**依赖**：T01

**测试**：
1. ComfyUI 顶栏出现 `Gallery` 按钮；
2. 点击后新 Tab 打开，URL 为 `/xyz/gallery`，页面显示 `Hello Gallery`；
3. `curl /xyz/gallery` 返回 200。

---

## L1 — 最小只读回路 + 写入底座

### T03 · `db.py` Schema v1 + 迁移框架 + PRAGMA  ✅ MVP · P0

**输入**：`PROJECT_SPEC §6.1`；`ARCHITECTURE §2.1 / §5.1`；约束 C-4。

**输出**：
- `gallery/db.py`：
  - `connect_read(path)` / `connect_write(path)`：统一应用 `journal_mode=WAL`、`synchronous=NORMAL`、`temp_store=MEMORY`、`mmap_size=256MiB`、`busy_timeout=5000`；
  - 版本化 `migrate(conn)`：读 `PRAGMA user_version`，按 `MIGRATIONS` 列表前向执行；
  - `MIGRATIONS[1]` 创建 `image`、`folder` 两张表 + 全部 `INDEX(...)`（按 §6.1）。
- `gallery/__init__` 在启动时调用一次 `db.migrate(...)`。

**依赖**：T01

**测试**：
1. 首次启动 → `user_version=1`，表结构与索引正确（`PRAGMA index_list`）；
2. 删除 DB 文件再启动 → 自动重建；
3. 手动把 `user_version` 改为 0 再启动 → 重新跑迁移成功；
4. 并发开两个只读连接 + 一个写连接 → 不报 `database is locked`。

---

### T04 · `repo.WriteQueue` + Single Writer  ✅ MVP · P0

**输入**：`ARCHITECTURE §2.1 / §4.6 / 附录 C.1`。

**输出**：
- `gallery/repo.py`：
  - `class WriteQueue` 内嵌 `PriorityQueue<(priority, seq, op, future)>`；优先级 `HIGH=0/MID=1/LOW=2`；同优先级 FIFO（单调 `seq`）；
  - `enqueue_write(priority, op) -> Future` 公共 API；
  - **## UPDATED** — 守护线程 `_writer_loop` 改为 **"一 op 一事务"** 模型：每次从队列取出 **1 条** op，严格按 `BEGIN → op.apply(conn) → COMMIT` 执行；失败则 `ROLLBACK` + `future.set_exception(...)`，**绝不**与其他 op 共享事务；废弃原先"drain 64 条 / 5 ms 单事务 + `SAVEPOINT` 包装"的批事务模型，避免任何 op 部分成功 / 部分回滚导致的数据不一致；
  - **## UPDATED** — 优先级队列、单调 `seq` FIFO、饥饿防护等调度逻辑保持不变（仅事务边界从"一批"收紧为"一条"）；
  - 饥饿防护：处理 LOW 累计 ≥ 200 条且队列内有 HIGH/MID 时让出；
  - `start()` / `stop()` 由 `gallery/__init__` 控制；线程崩溃自动重启 + 错误日志；
  - 提供基础 op 工厂：`UpsertImageOp`、`UpdateImagePathOp`、`DeleteImageOp`（占位空实现，T07/T19/T24 填 SQL）。

**依赖**：T03

**测试**：
1. 单元：1000 个 LOW + 10 个 HIGH 混入 → HIGH 平均出队延迟 < 20 ms；
2. **## UPDATED** — 单元：op.apply 抛异常 → 仅该 op 自身事务 `ROLLBACK`、对应 future 拿到异常；其前后相邻 op 各自独立 `BEGIN/COMMIT`，**不存在**"同批回滚"或"部分提交"中间态（用 `pragma data_version` 或显式断点验证事务边界）；
3. 单元：同优先级 1000 条按 enqueue 顺序拿到结果（验证 FIFO）；
4. 关停信号：`stop()` 后写线程在 200 ms 内退出。

---

### T05 · `paths.py` + `folders.py` + 配置持久化  ✅ MVP · P0

**输入**：`PROJECT_SPEC FR-5/6/7、NFR-19、C-5、C-10、§10 Q5`；`ARCHITECTURE §2.1`。

**输出**：
- `gallery/paths.py`：`assert_inside_root(path, roots) -> Path`，做 `Path.resolve()` + 落点校验；非法抛 `SandboxError`。
- `gallery/folders.py`：
  - 启动时确保 `output/` 与 `input/`（取自 `folder_paths`）作为 `kind in ('output','input')` 写入 `folder` 表（`removable=0`）；
  - 自定义根 CRUD：`add_root(path)` 校验目录可读、不与已有根**互为祖先 / 后代**（默认禁止重叠）；
  - `gallery_data/gallery_config.json` 读写（人类可读，含 `roots`、`prompt_stopwords`、`vocab_version`）。

**依赖**：T03

**测试**：
1. 首启自动注册 `output` / `input`；
2. 加同一路径两次 → 第二次报冲突；
3. 加 `output` 的子目录 → 拒绝（重叠）；
4. `paths.assert_inside_root('../etc/passwd', roots)` 抛 `SandboxError`。

---

### T06 · `metadata.py` PNG 读路径  ✅ MVP · P0

**输入**：`PROJECT_SPEC FR-23 / §10 Q3`；`ARCHITECTURE §2.1`。

**输出**：
- `gallery/metadata.py`：纯函数 `read_comfy_metadata(path) -> ComfyMeta`，从 PNG `tEXt` / `iTXt` 抽取 `prompt` / `workflow` / `parameters` 等；
- 派生 `positive_prompt / negative_prompt / model / seed / cfg / sampler / scheduler / has_workflow`（来源优先级：`workflow` JSON > `parameters` 文本 > 空）；
- 同时返回原始 `xyz_gallery.tags` / `xyz_gallery.favorite`（若存在），供 T07 mirror 回 DB；
- 失败容忍：损坏 / 非 PNG 返回部分字段 + `errors` 列表，不抛。

**依赖**：T01

**测试**：
1. 喂 ComfyUI 生成的 PNG（含 workflow）→ 解析齐全；
2. 喂只含 `parameters`（A1111 风格）的 PNG → 仍能解析关键字段；
3. 喂普通 JPG / 损坏 PNG → 返回空字段 + 错误列表，不抛；
4. 函数无副作用（多次调用结果完全一致）。

---

### T07 · `indexer.py` 冷启动扫描 + 指纹短路  ✅ MVP · P0

**输入**：`PROJECT_SPEC §8.1 / NFR-1 / NFR-8 / C-3`；`ARCHITECTURE §2.1 / §3.1 / §4.7`。

**输出**：
- `gallery/indexer.py`：
  - **## UPDATED** — 模块内维护 `_inflight: set[str]` + `_inflight_lock`，作为 **inflight 去重屏障**：所有进入索引流水线的入口（`cold_scan` 内单文件处理、`delta_scan` 触发的 `index_one`、以及 T20 watcher 回调）在调度前必须先把 **规范化后的绝对路径**（`os.path.realpath` + `os.path.normcase`）尝试加入 `_inflight`；若已存在 → **直接跳过本次请求**（不入队、不解析）；处理完成后必须在 `finally` 中移除该路径，**无论成功、异常、还是指纹短路跳过**，确保不残留；
  - `cold_scan(root)`：在后台线程 `os.walk` 注册根，每文件先 `stat()`；如 `(size, mtime_ns)` 与 DB 行匹配 → 跳过；否则调用 `metadata.read_comfy_metadata` → 组装 `UpsertImageOp` → `repo.enqueue_write(LOW, op)`；
  - 第一版**单线程解析**（ProcessPool 留给 T27）；批次 500 条文件触发一次进度统计；
  - `delta_scan(root, mode='light')`：仅 `(size, mtime_ns)` 比对，发现差异调用 `index_one(path)`；
  - `UpsertImageOp.apply(conn)` 实现：写 `image` 行（含 mirror 回的 favorite/tags_csv），并维护 `folder_id` / `relative_path`；
- 启动时 `gallery/__init__` 为每个根调度一次 `cold_scan`（不阻塞）。

**依赖**：T04, T05, T06

**测试**：
1. 5000 张图的 `output/` 首启全量索引 < 60 s（单核），ComfyUI 主循环不卡；
2. 重启 → 几乎 0 写入（指纹短路），DB 行数不变；
3. 替换 1 张图 → 下次 `delta_scan` 只重写 1 行；
4. 整个过程无 `database is locked`；
5. **## UPDATED** — 对同一文件并发触发 50 次 `index_one(path)` → `_inflight` 内同一 path 至多出现一次，实际 `UpsertImageOp` 入队仅 1 次；处理结束后 `_inflight` 不残留该路径；故意让 `metadata.read_comfy_metadata` 抛异常，`_inflight` 仍被 `finally` 清理（下一次同 path 请求可以正常进入）。

---

### T08 · `thumbs.py` 按需生成 + `thumbnail_cache` 表  ✅ MVP · P0

**输入**：`PROJECT_SPEC §8.3 / §6.1 thumbnail_cache`；`ARCHITECTURE §2.1`（LIFO 留给 T26）。

**输出**：
- `db.MIGRATIONS[2]`：建 `thumbnail_cache(hash_key PK, image_id, size_bytes, created_at, last_accessed)` + 两个索引；
- `gallery/thumbs.py`：
  - `request(image_id) -> bytes | path`：缓存命中直接返回路径；未命中 → Pillow 生成 WebP（最长边 320，q=78，cover 裁剪）→ 落盘到 `thumbs/<2 字符分片>/<sha1(path+mtime_ns)>.webp` → `enqueue_write(LOW, InsertThumbCacheOp)`；
  - `touch(hash_key)`：把 hash_key 加入内存 set，**10 s 周期 flush** 一次 `UPDATE thumbnail_cache SET last_accessed=...`（合并为单条 `executemany`）；
  - 第一版生成是阻塞的（在 `run_in_executor` 内），**FIFO** 调度器留待 T26；
- LRU 淘汰阈值留 TODO（T26 实现）。

**依赖**：T03, T04, T07

**测试**：
1. 首次请求 → 生成 + 落盘；同一 mtime_ns 二次请求 → 命中磁盘；
2. `last_accessed` 在 10 s 内被 flush 一次（不是每次请求都写）；
3. 修改原图（mtime_ns 改变）→ hash_key 改变 → 重新生成；
4. 1000 次并发请求同一 id → 不发生重复生成（同 key 串行）。

---

### T09 · `repo.py` 读 API + 游标分页 + 过滤 SQL  ✅ MVP · P0

**输入**：`PROJECT_SPEC §6.2 / §7.3 / §8.4`；`ARCHITECTURE §2.1 / §4.2`。

**输出**：
- `gallery/repo.py` 增量增加（**只读连接**，不进 WriteQueue）：
  - `get_image(id) -> ImageRecord`；
  - `folder_tree(include_counts) -> [FolderNode]`；
  - `list_images(filter, sort, cursor, limit) -> (items, next_cursor, total_estimate)`：
    - 支持 `name`（< 3 chars `LIKE`，≥ 3 chars 留 FTS5 给 T28）、`favorite`、`model`、`date_after/before`、`folder_id + recursive`；
    - `tag` / `prompt` AND 过滤本任务先用最简 `EXISTS`（rarest-first 留 T28）；
    - 排序键 `name|time|size|folder` 配合稳定 `(sort_key, id)` 游标；
    - `total_estimate`：25 ms 预算内做 `COUNT(*)`，超时返回近似标志。
  - `neighbors(id, filter, sort) -> {prev_id, next_id}`。

**依赖**：T03, T07

**测试**：
1. 单元：构造 1 万行假数据，所有过滤维度组合 P95 < 100 ms；
2. 翻页 50 次 → 不出现重复 / 缺失 id；
3. 中途插入新行 → 游标仍稳定；
4. `neighbors` 在结果集首尾正确返回 `null`（不环绕，`PROJECT_SPEC FR-16` 的 wrap 由前端做）。

---

### T10 · `routes.py` 只读端点（页 / 图 / 缩略图 / 原图 / 目录）  ✅ MVP · P0

**输入**：`PROJECT_SPEC §7.1 / §7.2 / §7.3 / §7.4 / §7.10`；`ARCHITECTURE §2.1 / §4.2`。

**输出**：
- `gallery/routes.py` 增加：
  - `GET /xyz/gallery` → 返回 `gallery_dist/index.html`（T11 才有真内容，先返回占位也行）；
  - `GET /xyz/gallery/static/*` → 静态文件；
  - `GET /xyz/gallery/folders[?include_counts=true]`；
  - `GET /xyz/gallery/images?...`、`GET /xyz/gallery/images/count`；
  - `GET /xyz/gallery/image/{id}` + `GET /xyz/gallery/image/{id}/neighbors`；
  - `GET /xyz/gallery/thumb/{id}?v=...` 设 `Cache-Control: public, max-age=31536000, immutable`；
  - `GET /xyz/gallery/raw/{id}` 支持 HTTP `Range` + `Content-Disposition: inline`；同时 `/raw/{id}/download` 用 `attachment`；
  - `GET /xyz/gallery/image/{id}/workflow.json` 提取 PNG 中的 workflow，404 if absent；
- 统一错误信封 `{ "error": { code, message, details? } }`；
- 任何 > 5 ms 的工作走 `loop.run_in_executor`（C-2）。

**依赖**：T08, T09

**测试**：
1. `curl` 跑通所有端点；
2. `Range: bytes=0-1023` 返回 206 + `Content-Range`；
3. 并发 50 个 `/thumb` 请求 → 不阻塞 `/folders`；
4. 请求不存在 id → 404 且响应体符合错误信封；
5. ComfyUI 主功能（出图）在并发请求下无明显抖动（事件循环健康）。

---

### T11 · SPA shell + 路由 + `api.js`  ✅ MVP · P0

**输入**：`PROJECT_SPEC §7.1 / NFR-16 / C-9`；`ARCHITECTURE §2.2`。

**输出**：
- `js/gallery_dist/index.html`：HTML shell + importmap（Vue 3 ESM）+ `<script type="module" src="/xyz/gallery/static/app.js">`；
- `js/gallery_dist/app.js`：挂载根组件、初始化 hash 路由（`#/`、`#/image/:id`）、装配 stores；
- `js/gallery_dist/api.js`：`get/post/patch/delete` 封装、错误信封解析、`AbortController` 支持；`openWS()` 建立 `/xyz/gallery/ws`（T18 之前可先 stub）；
- `routes.serve_spa` 改为返回真实 `index.html`。

**依赖**：T10

**测试**：
1. 打开 `/xyz/gallery` → SPA 加载，浏览器无 404、无 console 错误；
2. 切换 `#/image/123` 与 `#/` → 视图切换；
3. `api.get('/folders')` 拿到 JSON；非法响应抛友好错误；
4. 不依赖任何 `npm install`（全部 ESM CDN / 本地 js）。

---

### T12 · `MainView`：`FolderTree` + 过滤器面板  ✅ MVP · P0

**输入**：`PROJECT_SPEC FR-3a~f / FR-5~8`；`ARCHITECTURE §2.2`。

**输出**：
- `views/MainView.*`：左侧栏 + 右侧网格容器；
- `components/FolderTree.*`：树形渲染、选择、递归切换（FR-7 第一项）；
- 过滤器面板：name / favorite (`all|favorite|not favorite`) / model 下拉 / 日期 before-after 双开关；
- prompt / tag 输入先做最简 `<input>`（autocomplete 留 T21）；
- `stores/filters.*`：`FilterSpec + SortSpec`；filter 状态写 URL query（FR-4）+ `localStorage` 持久化；
- 折叠状态持久化（FR-2.2.1）。

**依赖**：T11

**测试**：
1. 选择 / 取消选择目录 → 网格内容改变（哪怕暂时只改 query 字符串）；
2. `localStorage` 清空再刷新 → 默认状态；
3. URL 直接带 `?favorite=yes` 进入 → 过滤器面板复现；
4. 折叠 / 展开过滤面板，刷新仍保持。

---

### T13 · `VirtualGrid` + `ThumbCard`  ✅ MVP · P0

**输入**：`PROJECT_SPEC FR-9a/b/c / FR-11~13 / NFR-5/6`；`ARCHITECTURE §2.2 / §3.2`。

**输出**：
- `components/VirtualGrid.*`：基于 `IntersectionObserver` 的虚拟滚动；可视视口 ± 2 屏；总高度 = 估算总数 × 卡片高；按需 `api.get('/images', cursor)` 续翻；
- `components/ThumbCard.*`：`<img loading="lazy" decoding="async">`、`object-fit: cover`、文件名截断 + tooltip、右上角收藏切换（先调用 `PATCH` 由 T19 实现，没就先桩函数）、左键打开详情（hash 路由）、右键菜单占位（菜单项 T24/T25 接）；
- 顶部工具栏：每行卡片数滑块（FR-9a）、排序下拉（FR-9b）；timeline 布局（FR-9c）留 P2（T28 之后）。

**依赖**：T11, T12

**测试**：
1. 50 000 行假数据下滚动顺畅，DOM 节点数稳定在视口 × 3；
2. 改每行数量 → 网格立即重排；
3. 改排序键 → 重新拉数据，游标重置；
4. 左键卡片 → 跳详情；右键 → 出菜单（哪怕先空）。

---

### T14 · `DetailView` + 缩放 + `/neighbors`  ✅ MVP · P0

**输入**：`PROJECT_SPEC FR-16 / FR-17 / FR-19`；`ARCHITECTURE §2.2`。

**输出**：
- `views/DetailView.*`：左图右元数据 2 栏；
- 左：原图 + 缩放（fit / 1:1 / + / -）+ 平移；上一张 / 下一张按钮调用 `/image/{id}/neighbors`，**保持当前 filter+sort**；首尾 wrap（前端做）；
- 右：只读元数据列表 + 各字段 copy-to-clipboard 按钮（positive / negative / seed）；
- 底部按钮：`Download image`（链接 `/raw/{id}/download`）、`Download workflow`（点击调 `/image/{id}/workflow.json`，无则 disable）、`Back`（恢复列表滚动位置 + 选中态：用 `sessionStorage` 暂存）；
- `Delete` 按钮先桩（待 T19 / T25）。

**依赖**：T11, T12, T10

**测试**：
1. 进入详情、按上一张 / 下一张能在当前 filter+sort 内循环；
2. Back 回到主视图，滚动位置与选中卡片复位；
3. 复制按钮把对应字段写入剪贴板；
4. 无 workflow 的 PNG 详情页，下载 workflow 按钮置灰。

---

## L2 — 可编辑 + 实时 + 异步同步

### T15 · `vocab.normalize_prompt` + Schema v2 词表  ✅ MVP · P0

**输入**：`PROJECT_SPEC §8.8 / §6.1 tag* / prompt_token*`；`ARCHITECTURE §2.1`。

**输出**：
- `gallery/vocab.py`：纯函数 `normalize_prompt(text, extra_stopwords) -> [str]`，按 §8.8 8 步流水线实现；
- 暴露 `normalize_tag(text) -> str`（复用流水线，空 stopword 集合）；
- `db.MIGRATIONS[3]` 增表：`tag(id, name UNIQUE NOCASE, usage_count)`、`image_tag(image_id, tag_id, PK)`、`prompt_token(id, token UNIQUE, usage_count)`、`image_prompt_token(image_id, token_id, PK)` + 反向索引；
- `repo` op：`UpsertVocabAndLinksOp`（解析后由 `indexer` 入队 LOW，在写 `image` 同事务里维护 vocab 与连接表）；
- `indexer.cold_scan` 调整：解析阶段同时产出 prompt tokens / 已有 `xyz_gallery.tags`，写入对应 op。

**依赖**：T07

**测试**：
1. `normalize_prompt('(masterpiece:1.2), <lora:foo:0.7>, BREAK, masterpiece.')` → `['masterpiece']`；
2. 单元：50 个语料样本与期望表对齐；
3. 5000 张图重建索引后，`tag.usage_count` 与人工抽样一致；
4. token 总数远小于 `split(',')` 的朴素值（量级证据）。

---

### T16 · Schema v3 迁移：`metadata_sync_*` 列 + 部分索引  ✅ MVP · P0

**输入**：`ARCHITECTURE §4.8 / 附录变更清单`。

**输出**：
- `db.MIGRATIONS[4]` 在 `image` 表增加 4 列：`metadata_sync_status TEXT DEFAULT 'ok'`、`metadata_sync_retry_count INT DEFAULT 0`、`metadata_sync_next_retry_at INT NULL`、`metadata_sync_last_error TEXT NULL`；
- **## UPDATED** — 同一迁移再增加一列：`version INT NOT NULL DEFAULT 0`，作为 image 元数据的**单调版本号**；所有 PATCH / 内部业务更新都必须 `+1`（实现见 T19），用于 `metadata_sync` 的乱序保护与文件单调写（实现见 T17）；老 DB 升级时所有现有行回填 `version=0`；
- 部分索引：`CREATE INDEX idx_image_sync ON image(metadata_sync_status) WHERE metadata_sync_status != 'ok'`；
- `ImageRecord` DTO 增加 `gallery.sync_status` 字段并在 `repo.list_images` / `get_image` 一并选出；**## UPDATED** — DTO 同时增加 `version: int` 字段（一并 SELECT），供 sync worker 与前端做版本对账。

**依赖**：T03

**测试**：
1. 老 DB 升级后 `user_version=4`，所有现有行 `sync_status='ok'`；
2. 部分索引在 `EXPLAIN QUERY PLAN` 中被使用；
3. 列表 / 详情 API 返回新字段；
4. **## UPDATED** — 老 DB 升级后所有现有行 `version=0`；新 INSERT 行默认 `version=0`；列表 / 详情 API 返回 `version` 字段。

---

### T17 · `metadata.py` 写路径 + `metadata_sync.py` Worker + 重试  ✅ MVP · P0

**输入**：`PROJECT_SPEC FR-23 / FR-24 / NFR-12`；`ARCHITECTURE §2.1 / §4.8`。

**输出**：
- `metadata.write_xyz_chunks(path, tags, favorite)`：write-temp + `os.replace`，**只增删 `xyz_gallery.*` 前缀块**，原 ComfyUI 块原样保留（C-6）；
- `gallery/metadata_sync.py`：
  - 启动时拉一个守护线程；
  - **## UPDATED** — 任务模型携带 `version`：`notify(image_id, version)` 由 service 调用时把当前最新的 `image.version` 一起传入；周期巡检改为 `SELECT id, version FROM image WHERE metadata_sync_status='pending' OR (='failed' AND retry_count<3 AND next_retry_at<=now)`，巡检读到的 `version` 直接放进 sync 任务对象；
  - **## UPDATED** — **写盘前必须做版本对账**：在调用 `metadata.write_xyz_chunks(...)` 之前，重新 `SELECT version, favorite, tags_csv FROM image WHERE id=?`；若 `task.version != current_db_version` → **直接跳过本次写**（不视为失败、不增加 retry_count、不更新 sync_status），让对应"最新 version"的 sync 任务接管；该规则保证文件写是**单调**的，**永远不会用旧数据覆盖新数据**；
  - 成功：`enqueue_write(LOW, SetSyncStatusOp(id, 'ok', expected_version=task.version))`；**## UPDATED** — `SetSyncStatusOp.apply` 内附带 `WHERE id=? AND version=?` 守卫，避免在 sync 期间发生新一轮 PATCH 后被旧任务把状态错误地标成 `ok`；
  - 失败：`retry_count+=1, next_retry_at = now + 5*2^n`，`enqueue_write(LOW, SetSyncFailedOp(...))`；超过 3 次留 `failed` 待用户重试。

**依赖**：T04, T16, T06

**测试**：
1. 写完后 PNG 用 `metadata.read_comfy_metadata` 重读，原字段不变 + 新 `xyz_gallery.tags / favorite` 出现；
2. 故意把目标文件设只读 → status 走 `pending → failed`，retry_count 增长到 3 后停；
3. 恢复写权限 → 调 `/resync` 后下一轮成功；
4. 进程崩溃后重启，pending 项被周期巡检自动捡起；
5. **## UPDATED** — 连发两次 PATCH（v1→v2），人为 sleep 让 v1 sync 任务执行晚于 v2 完成 → v1 任务在写盘前发现 `task.version(1) != db.version(2)`，**跳过文件写**且不修改 sync 状态；最终磁盘内容 == v2，最终 DB `sync_status='ok'` 且 `version=2`，**不可能**出现 v1 覆盖 v2 的退化结果。

---

### T18 · `ws_hub.py` + WebSocket 路由  ✅ MVP · P0

**输入**：`PROJECT_SPEC §7.9`；`ARCHITECTURE §2.1 / §4.4`。

**输出**：
- `gallery/ws_hub.py`：连接池（`set[WebSocketResponse]`）、`broadcast(type, data)` 包装事件信封 `{type, data, ts}`、断连清理；
- `routes.ws_handler`：`GET /xyz/gallery/ws` 升级为 WS，注册到 hub，处理 ping/pong；
- 事件类型常量：`image.upserted / image.updated / image.deleted / folder.changed / index.progress / vocab.changed / image.sync_status_changed / bulk.progress / bulk.completed / index.drift_detected`（数据形状由后续任务填）。

**依赖**：T10

**测试**：
1. 浏览器 console 直接 `new WebSocket('/xyz/gallery/ws')` 能连上；
2. 服务端 `ws_hub.broadcast('test', {...})` → 所有连接收到；
3. 客户端断开 → hub 内引用清理；
4. 服务端发 1000 条事件无丢失（弱要求：单机本地）。

---

### T19 · `PATCH /image/{id}` + `/resync` + `service.update_image`  ✅ MVP · P0

**输入**：`PROJECT_SPEC §7.5`；`ARCHITECTURE §3.2 / §4.3`。

**输出**：
- `gallery/service.py`：`update_image(id, patch)` 流程：
  1. `repo.get_image(id)` + `paths.assert_inside_root`；
  2. `vocab.normalize_tag` 整理 tag 列表；
  3. **## UPDATED** — `repo.enqueue_write(HIGH, UpdateImageOp(id, patch, also_set={'metadata_sync_status':'pending'}, bump_version=True))` `await`；`UpdateImageOp.apply` 在**同一事务**内执行 `UPDATE image SET ..., version = version + 1 WHERE id = ? RETURNING version`，把新版本号回传给 service；
  4. `ws_hub.broadcast('image.updated', {..., version: new_version})` 立即返回 200；
  5. **## UPDATED** — `metadata_sync.notify(id, version=new_version)` 异步推送，**必须把刚刚写入的 `version`** 一并交给 sync worker（与 T17 的版本对账配对）。
- `routes.patch_image`、`routes.delete_image`（先桩）、`routes.resync_image`（`POST /image/{id}/resync` 把 retry_count 清零、status 改回 `pending`、唤醒 worker）；**## UPDATED** — `/resync` **不**修改业务字段、**不**递增 `version`，仅复位重试状态，避免假版本扰乱对账。
- `UpdateImageOp.apply`：更新 `image.favorite/tags_csv` + 维护 `image_tag` diff；**## UPDATED** — 同事务内执行 `version = version + 1`，并 `RETURNING version` 给上层。

**依赖**：T04, T15, T17, T18

**测试**：
1. PATCH `{favorite:true}` → 200 < 50 ms（DB 快路径）；
2. 同步广播 `image.updated`；
3. 几秒内自动广播 `image.sync_status_changed` 为 `ok`；
4. PNG 块被改写、原 ComfyUI 块完整无损；
5. **## UPDATED** — 对同一 id 连续 PATCH N 次 → DB 中 `version` 严格 `+N`；每次 `image.updated` / `image.sync_status_changed` 广播均带最新 `version`；调用 `/resync` 前后 `version` 不变。

---

### T20 · `watcher.py` Observer + `Coalescer`  ✅ MVP · P0

**输入**：`PROJECT_SPEC FR-20 / §8.2`；`ARCHITECTURE §2.1 / §3.1`。

**输出**：
- `gallery/watcher.py`：
  - 每个注册根挂一个 `watchdog.Observer`；
  - `class Coalescer`：dict 合并、250 ms debounce、批 50 / 事务、HIGH_WATERMARK=500 溢出 → 清空 buffer + 调度该根的 `delta_scan(light)`；
  - 事件合并规则：`created+modified→upserted`、`created+deleted→drop`、`moved(a→b)→deleted(a)+upserted(b)`；
  - **## UPDATED** — 每条 upserted / deleted 调用 `indexer.index_one` 或 `indexer.delete_one` → 走 WriteQueue；写完由 service 包一层广播 `image.upserted / image.deleted`；watcher **不**自行维护去重表，统一复用 T07 在 `indexer` 模块内的 `_inflight` 屏障：同一路径若已在处理中，watcher 这次回调会被 indexer 直接跳过（避免事件抖动 / 多 Observer 重叠 / cold_scan 与 watcher 并发触发同一文件造成的重复索引与写放大）；inflight 的释放由 indexer 在 `finally` 中统一负责，watcher 不需感知。

**依赖**：T07, T18

**测试**：
1. 往 `output/` 拖入 1 张图 → ≤ 2 s 出现在前端；
2. unzip 一个 1000 文件包 → 不丢、UI 平滑（高水位降级到 delta_scan）；
3. 改名 `a.png → b.png` → 前端先消失再出现（id 可能不同，由 indexer 决定）；
4. 整个过程无 `database is locked` 与 OOM；
5. **## UPDATED** — 对同一文件在 1 s 内连发 100 次 modified 事件 → 实际只触发 **1 次** `UpsertImageOp` 入队（其余被 indexer 的 `_inflight` 跳过）；该次完成后再发新事件可正常处理（即 `_inflight` 已被正确释放，未死锁）。

---

### T21 · `/vocab/*` 端点 + `Autocomplete` + tag / prompt 过滤  ✅ MVP · P1

**输入**：`PROJECT_SPEC §7.7 / FR-3b / FR-3c / NFR-4`；`ARCHITECTURE §2.2`。

**输出**：
- `routes`：`GET /xyz/gallery/vocab/tags?prefix=&limit=20`、`GET /xyz/gallery/vocab/prompts?prefix=&limit=20`、`GET /xyz/gallery/vocab/models`；
- `repo`：`vocab_lookup(table, prefix, limit)`（`COLLATE NOCASE` + `ORDER BY usage_count DESC, name ASC`）；
- `components/Autocomplete.*`：debounce 150 ms、键盘上下选择、Tab/Enter 完成、按当前 token 切片完成（FR-3b 语义）；
- `stores/vocab.*`：前缀 → 结果 LRU；
- `MainView` 把 prompt / tag / model 过滤接入 `Autocomplete`，filter SQL 已在 T09，本任务只补"用户输入 → token 解析（`vocab.normalize_prompt`）→ 调 list_images"。

**依赖**：T15, T12

**测试**：
1. 输入 `mast` → 200 ms 内出现 `masterpiece` 等候选；
2. `/vocab/tags?prefix=&limit=20` P95 < 30 ms（万级词表）；
3. tag AND 过滤：`a, b, c` 选 3 个 → 结果集与人工 SQL 一致。

---

### T22 · 前端：编辑 UI + 同步徽标 + WS 订阅 + 焦点对账  ✅ MVP · P0

**输入**：`PROJECT_SPEC §7.9 注 / FR-13 / FR-18`；`ARCHITECTURE §2.2 / §4.4 / §3.2`。

**输出**：
- `ThumbCard`：收藏按钮接 `PATCH /image/{id}`；右上角同步状态徽标（`pending` 黄、`failed` 红、`ok` 不显示）；
- `DetailView`：标签编辑（共用 T21 `Autocomplete`）、收藏 toggle、`failed` 时显示"重试同步"按钮 → `POST /resync`；
- `stores/connection.*`：建立 WS 后订阅 `image.updated / image.upserted / image.deleted / image.sync_status_changed / index.progress`，patch 本地状态；指数回退重连；
- `window.onfocus` + WS reconnect → `GET /index/status`，若 `last_event_ts > localLast` 则重拉当前可视窗的 `/images`，**包含** `sync_status`。

**依赖**：T19, T18, T21

**测试**：
1. 在 Tab A 点收藏 → Tab B 1 s 内打勾；
2. 拔网线 5 s 再插回 → 自动重连且过滤结果与服务端一致；
3. 强制让 PNG 写失败 → 卡片角出现红徽，点击重试后变绿；
4. 切到别的 Tab 再切回 → 焦点对账触发一次 `/index/status` 请求。

---

## L3 — 批量操作 + 心跳兜底

### T23 · `Selection` 包络 + `/bulk/favorite` + `/bulk/tags` + `BulkBar`  ✅ MVP · P1

**输入**：`PROJECT_SPEC §6.2 Selection / §7.6 / FR-10a/b/c`；`ARCHITECTURE §3.3`。

**输出**：
- `repo.resolve_selection(sel) -> SQL subquery`：`explicit` 直接 `id IN (...)`；`all_except` 用同 `list_images` 的子查询 `WHERE id NOT IN (excluded)`；**绝不在 Python 里 expand 成大列表**；
- `routes`：`POST /bulk/favorite`、`POST /bulk/tags`、`POST /bulk/resolve_selection`；
- `service`：每条受影响 id 入队 HIGH（小批）或 MID（大批）`UpdateImageOp`，每条 `also_set={'metadata_sync_status':'pending'}` + 进度广播；
- `stores/selection.*`：`{ mode:'explicit', ids:Set } | { mode:'all_except', filters, excludedIds:Set }`；
- `components/BulkBar.*`：`Select all in current view` / `Clear` / 收藏 / 取消收藏 / 增减标签；进度条由 WS 计数驱动。

**依赖**：T19, T15, T22

**测试**：
1. 在 5 万图视图点 `Select all` → 网络包 < 1 KB；
2. 批量收藏 1000 张 → DB 全 commit 且 metadata_sync 后续追平；
3. 批量加 3 个 tag → vocab `usage_count` 正确加 3 × N；
4. 批量进行中用户单条 PATCH 不被饿死（HIGH 优先级生效）。

---

### T24 · 两阶段 bulk move + `MovePicker` + 增量提交  ✅ MVP · P1

**输入**：`PROJECT_SPEC §7.6 / §8.7 / FR-22`；`ARCHITECTURE §3.3 / §4.5 / 附录 C.2`。

**输出**：
- `service.preflight_move(sel, target)`：解析 selection、`paths.assert_inside_root`、`shutil.disk_usage` 校验、target `listdir` + 同批内 `_next_free_name` 解决冲突、生成 `MovePlan` 入 `PLAN_STORE`（TTL 5 min）；返回 `plan_id` + mappings；
- `service.execute_move(plan_id, overrides)`：**逐条**物理 `os.replace`（跨盘 fallback `copy2 + verify_size + unlink`），每条成功立即 `enqueue_write(MID, MoveImageOp(id, new_path, also_set='pending'))`，每条广播 `bulk.progress`；批末 `bulk.completed` + 审计；
- `routes`：`POST /bulk/move/preflight`、`POST /bulk/move/execute`、`POST /image/{id}/move`（单条复用同一路径）；
- `components/MovePicker.*`：目录选择 + 冲突 / 重命名预览 + 单条覆盖 + 提交。

**依赖**：T23, T17, T20

**测试**：
1. 1000 张目标无冲突 → 全部移动 + DB 路径全部更新；
2. 制造 50 条冲突 → preflight 给出 `(1).png` / `(2).png` 候选，UI 可单独覆盖；
3. 移动到目标盘空间不足 → preflight 拦截，无任何文件被动；
4. **中途 kill 进程**：磁盘已移动条数 = DB 已更新条数，30 s 内心跳兜底（T25）补齐剩余漂移。

---

### T25 · bulk delete + `ConfirmModal` + 审计日志 + `HeartbeatThread`  ✅ MVP · P1

**输入**：`PROJECT_SPEC §7.6 / FR-21 / NFR-13 / C-11`；`ARCHITECTURE §3.3 / §4.10`。

**输出**：
- `service.bulk_delete(sel)`：preflight 仅 sandbox + 计数；execute 逐条 `os.unlink` 成功 → `enqueue_write(MID, DeleteImageOp(id))` → 广播 `bulk.progress`；批末 `bulk.completed` + 审计；
- `components/ConfirmModal.*`：所有破坏性操作（单 / 批 删除、批 move 覆盖）共用；展示文件数 + 总大小（来自 `/bulk/resolve_selection`）；
- `gallery_audit.log`：滚动 30 天；记录每次破坏性操作的 actor=`ws_client_id` / 时间 / 摘要；
- `gallery/watcher.HeartbeatThread`：守护线程，每 30 s 对每个 root 触发一次 `indexer.delta_scan(root, mode='light')`；发现差异 broadcast `index.drift_detected`；自检日志每 5 min 写入审计文件（events_seen / coalesced / scans_done / drifts_found）。

**依赖**：T23, T20

**测试**：
1. 批量删 100 张 → 模态展示总大小，确认后磁盘 + DB 同步消失；
2. 中途 kill → 重启后 30 s 内心跳删掉 DB 中已无对应文件的行；
3. 在不可靠的网络盘上拔网 → 心跳触发 `index.drift_detected`，前端调试面板可见；
4. `gallery_audit.log` 正确轮转、`tail` 可见每次破坏性操作记录。

---

## L4 — 性能与长尾（**非 MVP**）

### T26 · `thumbs.Scheduler` LIFO 视口优先 + 取消 + LRU 淘汰  ❌ · P2

**输入**：`PROJECT_SPEC §8.3 / NFR-7`；`ARCHITECTURE §4.9`。

**输出**：
- `thumbs.Scheduler`：双队列 `stack[VIEWPORT]`(LIFO) + `queue[BACKGROUND]`(FIFO)；同 image_id 去重保留最新；`AbortController` 取消；ProcessPool 中固定 1 slot 保留给 VIEWPORT；
- LRU 淘汰：基于 `thumbnail_cache` 表 `ORDER BY last_accessed ASC`，越界 2 GB 时降到 80%；事务内 `unlink + DELETE`；30 s 节流；
- 每日 janitor 双向对账（孤儿文件 / 孤儿行）。

**依赖**：T08

**测试**：缩略图目录被人工填到 2.2 GB → 5 min 内回落到 ~1.6 GB；用户快速滚动时视口 P95 < 200 ms。

---

### T27 · `indexer` 元数据解析 ProcessPool 化  ❌ · P2

**输入**：`PROJECT_SPEC §8.1 / NFR-2`；`ARCHITECTURE §4.7`。

**输出**：把 `metadata.read_comfy_metadata` 的调用从主线程移入 `ProcessPoolExecutor(max_workers=min(4, cpu_count-1))`；主线程汇总 `as_completed` 后统一通过 `WriteQueue(LOW)` 入队；in-flight 上限 256 做背压。

**依赖**：T07

**测试**：5 万张冷启动时间相比 T07 单线程版本下降 ≥ 50%；常驻内存仍 ≤ 300 MB（NFR-7）。

---

### T28 · FTS5 显式分词器 + tag-AND / prompt-AND 自适应查询  ❌ · P2

**输入**：`PROJECT_SPEC §8.4`；`ARCHITECTURE §4.7.2`。

**输出**：
- `db.MIGRATIONS[5]`：`image_fts` 用显式 `tokenize='unicode61 remove_diacritics 2 tokenchars ''_-+.()[]{}<>:/\\@#'' separators '', \t\n'''` 重建 + 触发器；首启检测分词器哈希变化 → 排队 LOW 全量 reindex；
- `repo.build_tag_and_query`：基于 `tag.usage_count` 选 rarest 驱动，N≥4 且密集时切 INTERSECT 形式；
- 同样套到 prompt token AND；
- 名字过滤 ≥ 3 字符走 FTS5 `MATCH 'x*'`。

**依赖**：T15, T09

**测试**：5 万图、10 个 tag AND 过滤 P95 < 100 ms；搜 `lora:foo` 能命中。

---

## 附录：依赖图

```
T01 ──► T02
   └──► T03 ──┬─► T04 ──┬─► T07 ──┬─► T08 ──► T10
              │         │         │
              ├─► T05 ──┘         │
              │                   │
              ├─► T09 ────────────┤
              │                   ├─► T15 ──┬─► T19 ─► T22 ─► T23 ─► T24
              ├─► T16 ────────────┘         │                  │
              │                   T18 ◄─────┤                  ├─► T25
              ├─► T17 ◄── T06 ◄── T15       │                  │
              │                             │                  │
              T11 ──► T12 ──► T13 / T14     │                  │
                       └──► T21 ◄───────────┘                  │
                                                                │
              T20 ◄── T07 ───────────────────────────────────────┘
              T20 ──► T22

  L4: T26 ◄ T08 ;  T27 ◄ T07 ;  T28 ◄ T15+T09
```

> 所有 P0 + P1 任务（T01–T25）构成 MVP；按上图自上而下并适度并行，单人约 3–4 周可达 MVP。
