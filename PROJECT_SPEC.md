# XYZ Image Gallery — PROJECT_SPEC

> A standalone image gallery sub-module living inside the existing
> `ComfyUI-XYZNodes` plugin. It shares the package, the web directory and the
> aiohttp routing surface of the host plugin, but is otherwise independent of
> the existing nodes.

---

## 1. Overview

The XYZ Image Gallery is a ComfyUI plugin that turns local image folders
(default `output/` and `input/`, plus user-defined custom folders) into a fast,
filterable, taggable gallery.

* **Entry point**: a button in the ComfyUI top-bar.
* **Surface**: clicking the button opens a **new browser tab** at
  `/xyz/gallery` served by ComfyUI's aiohttp server. The gallery is a full
  single-page application; it does **not** render inside the LiteGraph canvas.
* **Scale target**: smooth UX with **2 000 – 50 000 images**, where each image
  is **≥ 1024 × 1024** (typical SDXL/Flux outputs of 2 – 10 MB).
* **Persistence**: a SQLite-backed index plus an on-disk thumbnail cache live
  inside the plugin folder, so the gallery never re-scans every image at
  startup.
* **Live**: filesystem changes (new generations, renames, deletions, manual
  moves) are reflected without manual refresh.

---

## 2. Functional Requirements

### 2.1 Top-bar entry

* FR-1 Register a top-bar button in ComfyUI labelled **"Gallery"** with an
  icon. Clicking it opens `/xyz/gallery` in a new tab.
* FR-2 The gallery page is fully usable without an active ComfyUI workflow.

### 2.2 Main view — left sidebar

#### 2.2.1 Filter panel (collapsible, top of sidebar)

Vertical stack of controls; collapse state is persisted per browser.

| ID    | Control                | Behaviour                                                                                                                                                                                                                                                                  |
| ----- | ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-3a | **Name filter**        | Label `name filter:` + text input. Case-insensitive substring match against filename. Debounced (250 ms).                                                                                                                                                                   |
| FR-3b | **Positive prompt**    | Label `positive prompt filter:` + text input. Comma-separated tokens; matches images whose positive prompt contains **all** tokens (AND semantics). While typing the **current** token, show top-20 autocomplete suggestions sourced from the indexed prompt vocabulary. Click a suggestion to complete the current token. |
| FR-3c | **Tag filter**         | Same UX as FR-3b but matches against the gallery-managed `tags` field. Suggestions sourced from the tag vocabulary.                                                                                                                                                        |
| FR-3d | **Favorite filter**    | Label `favorite filter:` + dropdown: `all` / `favorite` / `not favorite`.                                                                                                                                                                                                  |
| FR-3e | **Model filter**       | Label `model filter:` + dropdown: `all` + every distinct model name in the index.                                                                                                                                                                                          |
| FR-3f | **Date filter**        | Label `date filter:` + `before` toggle button + date picker + `after` toggle button + date picker. Each toggle independently enables its bound. Filter is applied to **image creation date** from metadata, falling back to file mtime.                                     |

* FR-4 All filters compose with AND semantics. The filter state is
  reflected in the URL query string (sharable / bookmarkable).

#### 2.2.2 Folder panel (below filters)

* FR-5 Tree view of folders and sub-folders.
* FR-6 Default roots: ComfyUI `output/` and `input/`. These are
  **non-removable**.
* FR-7 Toolbar with two buttons:
  * **Recursive toggle** — choose between *only the selected folder* and
    *the selected folder + all descendants*.
  * **Manage custom folders** — opens a modal where the user can:
    * add a new custom root folder (absolute path with validation),
    * remove an existing custom root (`output` and `input` excluded).
* FR-8 Folder selection narrows the working set; combined with the filter
  panel via AND.

### 2.3 Main view — center

#### 2.3.1 Top toolbar

| ID     | Control                                                                                                                                                                                                                                              |
| ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| FR-9a  | Slider controlling the **number of thumbnails per row** (e.g. 2 – 12).                                                                                                                                                                               |
| FR-9b  | Sort dropdown: `name`, `time`, `size`, `folder`; each with ascending / descending toggle.                                                                                                                                                            |
| FR-9c  | Layout switch: **compact grid** ⇄ **timeline**. Timeline groups thumbnails into vertical buckets driven by the active sort key (date buckets for `time`, alphabet buckets for `name`, size buckets for `size`, folder buckets for `folder`).         |
| FR-9d  | **Bulk-edit** toggle. See 2.3.2.                                                                                                                                                                                                                     |

#### 2.3.2 Bulk edit mode

When enabled, each thumbnail gains a checkbox. Additional buttons appear:

* FR-10a `Select all in current view` / `Clear selection`. *Current view* =
  current `folder + filter` result, **not** just the visually rendered slice.
* FR-10b Bulk **favorite / un-favorite**.
* FR-10c Bulk **add tags / remove tags**. The tag input must support the same
  autocomplete UX as FR-3c.
* FR-10d Bulk **move**. Opens a folder-picker modal. On collision the system
  follows FR-19 (rename loop with confirmation).

#### 2.3.3 Thumbnail grid

* FR-11 All thumbnails share the same display size and aspect ratio
  (`object-fit: cover`).
* FR-12 Filename rendered below the thumbnail (truncated with tooltip).
* FR-13 Top-right corner: **favorite** toggle button reflecting current state;
  click toggles without leaving the grid.
* FR-14 **Right-click** context menu: `Move…`, `Delete…`.
* FR-15 **Left-click** opens the **detail page** for that image, preserving
  the current `folder + filter + sort` context.

### 2.4 Detail page

* FR-16 Layout: 2-pane.
  * **Left**: original image with zoom in/out, fit-to-screen, 1:1, pan.
    Two buttons step to the **previous / next** image **within the current
    `folder + filter + sort` set**, wrapping at the ends.
  * **Right**: metadata pane.
* FR-17 Read-only metadata fields (sourced from PNG/EXIF/ComfyUI workflow
  payload):
  * size (`width × height`)
  * creation date
  * positive prompt — with **copy to clipboard** button
  * negative prompt — with **copy to clipboard** button
  * model
  * seed — with **copy to clipboard** button
  * cfg
  * sampler
  * scheduler
* FR-18 Editable, gallery-owned fields:
  * `tags` (with autocomplete identical to FR-3c)
  * `favorite` (toggle)
* FR-19 Action buttons:
  * **Download image** (original file)
  * **Download workflow** (`.json` extracted from PNG metadata, disabled if
    none)
  * **Back** to main view (restores prior scroll position and selection)
  * **Delete** (with confirmation modal — see FR-21). Deletion sends the
    user back to the main view.

### 2.5 Cross-cutting behaviour

* FR-20 **Auto-update**: any change in a watched folder (new file, deletion,
  rename, mtime change) is reflected in the gallery within ≤ 2 s, without
  user-initiated refresh, via WebSocket push from backend to frontend.
* FR-21 **Delete confirmation**: every delete (single or bulk) shows a modal
  requiring explicit confirmation. The modal lists the file count and total
  size.
* FR-22 **Move collision**: if any source filename collides with an existing
  file in the destination folder, the system proposes a renamed version
  (`<stem> (1).<ext>`, then `(2)`, …) and shows a confirmation step. The
  loop continues until **every** moved file has a unique name in the target,
  then performs the move atomically.
* FR-23 The gallery **reads** ComfyUI-written metadata (positive/negative
  prompt, model, seed, cfg, sampler, scheduler, workflow) from PNG `tEXt` /
  `iTXt` chunks. The gallery **writes** only its own `tags` and `favorite`
  fields, into a dedicated PNG chunk (key prefix `xyz_gallery.`), so it
  never corrupts the original ComfyUI metadata.
* FR-24 Gallery-owned fields are **also** mirrored into the SQLite index, so
  losing a single PNG chunk never loses gallery state, and so all queries
  hit the index, not the filesystem.

---

## 3. Non-Functional Requirements

### 3.1 Performance

* NFR-1 **Cold start of ComfyUI** must not be blocked by the gallery. The
  scanner runs in a background thread; ComfyUI's main loop is never blocked
  for more than ~50 ms by gallery startup work.
* NFR-2 **Cold start of the gallery page**: < 1 s to interactive on a
  20 000-image library; thumbnails appear progressively.
* NFR-3 **Filter / sort latency** on the index: P95 < 100 ms for 50 000
  images on a single SSD.
* NFR-4 **Autocomplete latency**: P95 < 30 ms per keystroke, even with
  ≥ 50 000 distinct tokens in the vocabulary.
* NFR-5 **Scroll**: 60 fps during virtual scroll on an integrated GPU;
  thumbnails decoded asynchronously.
* NFR-6 **Memory ceiling** (frontend): the DOM never holds more than ~3×
  the visible viewport's worth of thumbnail nodes (virtual scrolling).
* NFR-7 **Memory ceiling** (backend): peak resident size of the indexer ≤
  300 MB regardless of library size; thumbnails are streamed, never loaded
  in bulk.

### 3.2 Scalability

* NFR-8 Linear scan cost only on first index of a folder; subsequent
  startups perform a delta scan (compare cached `(path, mtime, size)` →
  re-index only changed entries).
* NFR-9 Watcher-based incremental updates: each filesystem event costs
  O(1) DB writes plus one thumbnail render.
* NFR-10 The architecture must remain functional up to **100 000** images
  without code changes (only longer first-time indexing).

### 3.3 Robustness

* NFR-11 Index and thumbnail cache are **rebuildable**: deleting them
  (manually or via a "rebuild" button) must restore correct behaviour
  with no data loss for user-managed fields, because user-managed fields
  are mirrored into PNG chunks (FR-23/24).
* NFR-12 All write operations to images are atomic (write-temp + rename).
* NFR-13 All destructive UI operations require confirmation (FR-21).
* NFR-14 Concurrent multi-tab usage: writes are serialised through the
  backend; the WebSocket fan-out keeps every tab consistent.

### 3.4 Compatibility

* NFR-15 Backend: Python ≥ 3.10, aiohttp (already used by ComfyUI), Pillow,
  watchdog, sqlite3 (stdlib).
* NFR-16 Frontend: evergreen browsers (Chromium ≥ 110, Firefox ≥ 110,
  Safari ≥ 16). No build step required for the user; bundled assets are
  shipped pre-built in `js/gallery_dist/`.
* NFR-17 Cross-platform: Windows, macOS, Linux. Path handling must be
  `pathlib`-based; folder paths stored as POSIX strings in the index.

### 3.5 Security & privacy

* NFR-18 The HTTP API is bound to whatever interface ComfyUI itself binds.
  No new ports are opened.
* NFR-19 Custom folder paths must be validated to be **readable
  directories**. Folder operations (move, delete) are restricted to paths
  inside one of the registered roots — never arbitrary FS access via the
  API.

---

## 4. System Architecture

### 4.1 High-level diagram

```
                    ┌──────────────────────────────────────────────┐
                    │            ComfyUI process                   │
                    │                                              │
   Top-bar button ──┼──► aiohttp (PromptServer.instance.routes)    │
   /xyz/gallery     │           │                                  │
                    │           ▼                                  │
                    │   ┌───────────────┐    ┌───────────────────┐ │
                    │   │ Gallery API   │◄──►│  Index (SQLite)   │ │
                    │   │  (routes.py)  │    │  + FTS5 virtual   │ │
                    │   └───────┬───────┘    │  + inverted maps  │ │
                    │           │            └───────────────────┘ │
                    │           ▼                                  │
                    │   ┌───────────────┐    ┌───────────────────┐ │
                    │   │ Indexer +     │◄──►│  Thumbnail cache  │ │
                    │   │ Watcher (BG)  │    │   (.webp on disk) │ │
                    │   └───────┬───────┘    └───────────────────┘ │
                    │           │                                  │
                    │           ▼                                  │
                    │   ┌───────────────┐                          │
                    │   │ WebSocket hub │──► live updates to tabs  │
                    │   └───────────────┘                          │
                    └──────────────────────────────────────────────┘
                                ▲
                                │ HTTP + WS
                                ▼
                    ┌──────────────────────────────────────────────┐
                    │              Browser (new tab)               │
                    │   SPA: virtual-scroll grid, detail view,     │
                    │        filter/sort/bulk-edit, autocomplete.  │
                    └──────────────────────────────────────────────┘
```

### 4.2 Backend modules (Python)

All under `ComfyUI-XYZNodes/gallery/`:

| Module                | Responsibility                                                                                                |
| --------------------- | ------------------------------------------------------------------------------------------------------------- |
| `__init__.py`         | Wires the gallery into the host plugin: registers routes, starts background services on first import.         |
| `routes.py`           | All `/xyz/gallery/...` aiohttp handlers; pure I/O, no business logic.                                         |
| `service.py`          | Use-case layer: list/filter/move/delete/tag/favorite. Coordinates `repo`, `indexer`, `thumbs`, `ws_hub`.      |
| `repo.py`             | SQLite repository (CRUD + complex queries). Owns the connection pool and prepared statements.                 |
| `db.py`               | Schema, migrations, FTS5 setup, pragmas (`journal_mode=WAL`, `synchronous=NORMAL`).                           |
| `indexer.py`          | Initial scan + delta scan + per-event indexing. Extracts ComfyUI metadata via `metadata.py`.                  |
| `metadata.py`         | PNG chunk reader/writer for both ComfyUI fields (read-only) and gallery fields (R/W). Pure functions.         |
| `thumbs.py`           | Thumbnail generator (Pillow); on-demand + lazy + LRU eviction; output format WebP, 320×320 cover.             |
| `watcher.py`          | `watchdog` observers per registered root; debounced event coalescing; pushes to indexer queue.                |
| `ws_hub.py`           | WebSocket fan-out for live updates (`image.upserted`, `image.deleted`, `folder.changed`, `index.progress`).   |
| `folders.py`          | Manages root folder registry (`output`, `input`, custom). Persists to `gallery_config.json`.                  |
| `paths.py`            | Path validation + sandboxing (every path must resolve under a registered root).                               |
| `vocab.py`            | Tag / prompt-token vocabulary maintenance (counts, autocomplete queries).                                     |

### 4.3 Frontend modules (JavaScript)

Under `ComfyUI-XYZNodes/js/`:

| Module                                | Responsibility                                                                                          |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `gallery_topbar.js`                   | Loaded by ComfyUI (`WEB_DIRECTORY`). Adds the top-bar button via `app.registerExtension`.               |
| `gallery_dist/` (pre-bundled)         | The SPA assets shipped with the plugin: HTML shell, CSS, ESM modules. Served by `routes.py`.            |
| `gallery_dist/app.js` (entry)         | Bootstraps the SPA, mounts the router (`/`, `/image/:id`).                                              |
| `gallery_dist/views/MainView.*`       | Sidebar + grid + toolbar.                                                                               |
| `gallery_dist/views/DetailView.*`     | Detail page.                                                                                            |
| `gallery_dist/components/...`         | `VirtualGrid`, `ThumbCard`, `Autocomplete`, `FolderTree`, `BulkBar`, `ConfirmModal`, `MovePicker`, etc. |
| `gallery_dist/stores/...`             | Reactive state: `filters`, `selection`, `folders`, `vocab`, `connection`.                               |
| `gallery_dist/api.js`                 | Thin REST + WS client.                                                                                  |

### 4.4 Process & data flow

1. **Plugin import**: `__init__.py` imports `gallery`. `gallery.__init__`
   ensures the SQLite file exists, runs migrations, starts the indexer
   thread, mounts watchers on the registered roots, and registers HTTP
   routes.
2. **Top-bar button**: `gallery_topbar.js` is auto-loaded by ComfyUI; on
   click → `window.open('/xyz/gallery')`.
3. **Gallery page**: `routes.py` serves `gallery_dist/index.html`. The SPA
   opens a WS connection to `/xyz/gallery/ws` and issues `GET
   /xyz/gallery/images?...` for the first page.
4. **Live updates**: watcher event → debounced queue → `indexer` → SQLite
   write → `ws_hub.broadcast(...)` → frontend store patches local state.

---

## 5. Key Design Constraints (MUST follow)

* **C-1 Single source of truth = SQLite index.** All UI queries (filter,
  sort, count, paginate, autocomplete) hit the index, **never** the
  filesystem. Filesystem reads happen only inside `indexer`, `thumbs`,
  `metadata`, and binary endpoints.
* **C-2 No blocking work on the ComfyUI event loop.** All scanning,
  hashing, thumbnailing, and PNG metadata writing run in a dedicated
  worker thread / process pool. aiohttp handlers `await`
  `loop.run_in_executor(...)` for any CPU-bound or disk-bound call > 5 ms.
* **C-3 Idempotent indexing.** Re-running the indexer on an unchanged
  folder must be a no-op (detected via `(size, mtime_ns)` fingerprint
  before any expensive work).
* **C-4 Schema migrations are forward-only and versioned** in `db.py`.
  Never break an existing user's index without an automated migration.
* **C-5 Sandbox every path.** Any path coming from the client must be
  resolved (`Path.resolve()`) and verified to be inside a registered
  root before any read/write. Reject otherwise with HTTP 400.
* **C-6 Original ComfyUI metadata is read-only.** The gallery may add
  new chunks (`xyz_gallery.tags`, `xyz_gallery.favorite`) but must
  never modify or drop pre-existing ComfyUI chunks (`prompt`,
  `workflow`, `parameters`, …).
* **C-7 No new ports, no external network calls.** Everything is served
  on ComfyUI's existing aiohttp server. Thumbnails and originals are
  served by the gallery itself; the SPA never reaches outside.
* **C-8 Decoupled from existing nodes.** The gallery package depends on
  ComfyUI core (`server.PromptServer`, `folder_paths`) but **not** on
  any module under `ComfyUI-XYZNodes` other than its own subtree.
  Removing/renaming an existing node must not affect the gallery.
* **C-9 Frontend ships pre-built.** Users do not run `npm install`. The
  build artefact lives in `js/gallery_dist/` and is committed to the
  repo. Any framework choice must respect this (CDN ESM or pre-bundled).
* **C-10 Config is human-readable JSON.** `gallery_config.json` (roots,
  user preferences) lives next to the SQLite file and is editable by
  hand for recovery.
* **C-11 All destructive operations (delete, move with overwrite) are
  confirmed by an explicit user action and logged** to a rolling
  `gallery_audit.log` (last 30 days).
* **C-12 The DB and thumbnail cache live inside the plugin folder**, not
  in `output/`, so syncing or wiping ComfyUI's outputs never corrupts
  gallery state.

---

## 6. Data Model

### 6.1 SQLite schema (logical)

> Types use SQLite affinities; see `db.py` for the canonical DDL.

#### `image` — one row per indexed image

| Column                      | Type      | Notes                                                                                                     |
| --------------------------- | --------- | --------------------------------------------------------------------------------------------------------- |
| `id`                        | INTEGER PK | auto-increment surrogate                                                                                 |
| `path`                      | TEXT UNIQUE NOT NULL | absolute POSIX path                                                                            |
| `folder_id`                 | INTEGER FK → `folder.id` | the immediate registered root the file belongs to (for fast root scoping)                  |
| `relative_path`             | TEXT NOT NULL | path relative to the registered root, used for display & sub-folder scoping                           |
| `filename`                  | TEXT NOT NULL | basename, lower-cased duplicate stored in `filename_lc` for case-insensitive search                   |
| `filename_lc`               | TEXT NOT NULL | lower-cased filename for indexed substring search                                                     |
| `ext`                       | TEXT NOT NULL | e.g. `png`, `jpg`, `webp`                                                                             |
| `width` / `height`          | INTEGER   |                                                                                                          |
| `file_size`                 | INTEGER   | bytes                                                                                                    |
| `mtime_ns`                  | INTEGER   | filesystem mtime (ns); used for delta scan                                                               |
| `created_at`                | INTEGER   | seconds-epoch; preferred = ComfyUI metadata creation date, fallback = ctime                              |
| `content_hash`              | TEXT      | optional `xxhash64` of file body, for dedup detection (computed lazily)                                  |
| **ComfyUI metadata (read-only)** |       |                                                                                                          |
| `positive_prompt`           | TEXT      |                                                                                                          |
| `negative_prompt`           | TEXT      |                                                                                                          |
| `model`                     | TEXT      | indexed                                                                                                  |
| `seed`                      | INTEGER   |                                                                                                          |
| `cfg`                       | REAL      |                                                                                                          |
| `sampler`                   | TEXT      |                                                                                                          |
| `scheduler`                 | TEXT      |                                                                                                          |
| `workflow_present`          | INTEGER   | 0/1; the workflow JSON itself is **not** copied into the DB, only flagged                                |
| **Gallery-owned**           |           |                                                                                                          |
| `favorite`                  | INTEGER   | 0/1, indexed                                                                                             |
| `tags_csv`                  | TEXT      | denormalised CSV for quick read; canonical store is the `image_tag` join table                           |
| `indexed_at`                | INTEGER   | epoch                                                                                                    |

Indexes:
* `UNIQUE(path)`
* `INDEX(folder_id, relative_path)`
* `INDEX(filename_lc)`
* `INDEX(model)`
* `INDEX(favorite)`
* `INDEX(created_at)`
* `INDEX(file_size)`
* `INDEX(mtime_ns)`

#### `folder` — registered roots and discovered sub-folders

| Column         | Type    | Notes                                                          |
| -------------- | ------- | -------------------------------------------------------------- |
| `id`           | PK      |                                                                |
| `path`        | TEXT UNIQUE | absolute POSIX                                              |
| `kind`        | TEXT    | `output` / `input` / `custom`                                  |
| `parent_id`   | INTEGER FK → `folder.id` NULL | NULL = registered root                       |
| `display_name` | TEXT   |                                                                |
| `removable`   | INTEGER | 0 for `output`/`input`, 1 for custom                           |

#### `tag` — gallery tag vocabulary

| Column        | Type    | Notes                                  |
| ------------- | ------- | -------------------------------------- |
| `id`          | PK      |                                        |
| `name`        | TEXT UNIQUE NOT NULL |                           |
| `usage_count` | INTEGER | maintained on insert/delete in `image_tag` |

#### `image_tag` — many-to-many

| Column    | Type    | Notes |
| --------- | ------- | ----- |
| `image_id`| FK      |       |
| `tag_id`  | FK      |       |
| PK = `(image_id, tag_id)`; `INDEX(tag_id, image_id)` for inverted queries.

#### `prompt_token` — positive-prompt vocabulary

| Column      | Type    | Notes                                                                  |
| ----------- | ------- | ---------------------------------------------------------------------- |
| `id`        | PK      |                                                                        |
| `token`     | TEXT UNIQUE | output of the **Prompt Normalization Pipeline** (see §8.8): lower-cased, weight-stripped, LoRA-stripped, punctuation-cleaned, whitespace-collapsed |
| `usage_count` | INTEGER |                                                                      |

> **Critical invariant.** Raw prompt strings are **never** tokenised by a
> bare `split(',')`. Every token written to `prompt_token` /
> `image_prompt_token` must come out of `vocab.normalize_prompt(text)`
> (§8.8). This keeps the vocabulary bounded (typically ≤ 5 000 distinct
> tokens for a 100 000-image library, vs. > 1 M for a naive split) and
> keeps autocomplete meaningful.

#### `image_prompt_token` — many-to-many (for prompt-token AND-filter)

| Column      | Type    |
| ----------- | ------- |
| `image_id`  | FK      |
| `token_id`  | FK      |
PK + `INDEX(token_id, image_id)`.

#### `image_fts` — FTS5 virtual table

```
fts5(filename, positive_prompt, negative_prompt, tags, content='image', tokenize='unicode61 remove_diacritics 2')
```
Synced via triggers on `image` insert/update/delete. Used for:
* substring acceleration when name filter has ≥ 3 chars,
* fallback fuzzy search if the deterministic AND-filters return nothing.

#### `thumbnail_cache` — authoritative LRU index for the on-disk thumbnail folder

The filesystem alone cannot answer "which thumbnail is the oldest?" cheaply
once we have ≥ 100 000 entries — `os.scandir` over 100 k+ shards plus per-file
`stat()` is multi-second on cold cache. Cache bookkeeping therefore lives in
SQLite, and the on-disk `.webp` files are treated as a *materialisation* of
the rows in this table.

| Column          | Type    | Notes                                                                |
| --------------- | ------- | -------------------------------------------------------------------- |
| `hash_key`      | TEXT PK | `sha1(path + mtime_ns)`; matches the on-disk filename stem           |
| `image_id`      | INTEGER FK → `image.id` ON DELETE CASCADE | back-ref for orphan cleanup            |
| `size_bytes`    | INTEGER NOT NULL | physical size of the cached `.webp` on disk                 |
| `created_at`    | INTEGER NOT NULL | epoch seconds; when the thumb was first generated           |
| `last_accessed` | INTEGER NOT NULL | epoch seconds; **monotonically updated on every HTTP hit**  |

Indexes:
* `INDEX(last_accessed)` — drives LRU eviction
* `INDEX(image_id)` — drives orphan cleanup when an image row is deleted

Eviction policy (see §8.3): when `SUM(size_bytes)` exceeds the configured
budget (default 2 GB), evict rows in `ORDER BY last_accessed ASC` until the
total is back under 80 % of the budget, deleting the corresponding `.webp`
files in the same transaction. A periodic janitor (every 5 min, low priority)
also reconciles disk vs. DB to recover from crash-induced drift.

### 6.2 Domain DTOs (used across the API)

```text
ImageRecord {
    id: int
    path: str
    folder: { id, kind, display_name, relative_dir }
    filename: str
    ext: str
    size: { width, height, bytes }
    created_at: ISO-8601
    metadata: {
        positive_prompt: str | null
        negative_prompt: str | null
        model: str | null
        seed: int | null
        cfg: float | null
        sampler: str | null
        scheduler: str | null
        has_workflow: bool
    }
    gallery: {
        favorite: bool
        tags: [str]
    }
    thumb_url: str   // /xyz/gallery/thumb/{id}?v={mtime_ns}
    raw_url:   str   // /xyz/gallery/raw/{id}
}

FolderNode {
    id, path, kind, display_name, removable,
    children: [FolderNode],
    image_count_self: int,
    image_count_recursive: int
}

FilterSpec {
    name: str | null
    positive_tokens: [str]   // raw user input; backend re-runs them
                             //   through normalize_prompt() (§8.8) before
                             //   resolving to token_ids.
    tag_tokens: [str]        // same: normalised on the server.
    favorite: 'all' | 'yes' | 'no'
    model: str | null
    date_after: ISO-date | null
    date_before: ISO-date | null
    folder_id: int | null
    recursive: bool
}

SortSpec {
    key: 'name' | 'time' | 'size' | 'folder'
    dir: 'asc' | 'desc'
}

PageCursor {
    last_sort_key_value: any
    last_id: int           // tie-breaker for stable order
}

// Bulk-selection envelope. Used by every /bulk/* endpoint.
//
// Two modes:
//   1. Explicit mode  → mode = "explicit", ids = [int...]
//      Used when the user has hand-picked a small set of cards.
//   2. Inverted mode  → mode = "all_except",
//                       filters = <FilterSpec snapshot>,
//                       excluded_ids = [int...]
//      Used when the user clicked "Select all in current view": the
//      frontend stores ONE boolean + a (typically tiny) exclusion set
//      instead of materialising 100 000 ids in memory or on the wire.
//
// The backend resolves "all_except" to a server-side subquery — it
// NEVER expands to a list of ids in Python.
Selection {
    mode: 'explicit' | 'all_except'
    ids?: [int]                  // present when mode = 'explicit'
    filters?: FilterSpec         // present when mode = 'all_except'
    excluded_ids?: [int]         // present when mode = 'all_except'
}
```

### 6.3 On-disk layout

```
ComfyUI-XYZNodes/
├── PROJECT_SPEC.md
├── gallery/                          # backend package
│   └── ...
├── js/
│   ├── gallery_topbar.js             # top-bar entry
│   └── gallery_dist/                 # pre-built SPA
│       ├── index.html
│       ├── app.js
│       └── ...
└── gallery_data/                     # created at runtime (git-ignored)
    ├── gallery.sqlite                # index DB (WAL files alongside)
    ├── gallery_config.json           # roots + prefs
    ├── gallery_audit.log
    └── thumbs/
        └── ab/abc123def....webp      # 2-char shard prefix to keep dirs small
```

---

## 7. API Design

All endpoints are mounted under the existing aiohttp instance via
`PromptServer.instance.routes`, with prefix `/xyz/gallery`. JSON
request/response unless noted.

### 7.1 Page & assets

| Method | Path                          | Purpose                                                |
| ------ | ----------------------------- | ------------------------------------------------------ |
| GET    | `/xyz/gallery`                | Serves SPA `index.html`.                               |
| GET    | `/xyz/gallery/static/*`       | Serves `js/gallery_dist/*` (cache-busted by hash).     |

### 7.2 Folders

| Method | Path                                  | Body / Query                       | Returns                                |
| ------ | ------------------------------------- | ---------------------------------- | -------------------------------------- |
| GET    | `/xyz/gallery/folders`                | `?include_counts=true`             | tree of `FolderNode`                   |
| POST   | `/xyz/gallery/folders`                | `{ "path": str }`                  | new `FolderNode` (kind=`custom`)       |
| DELETE | `/xyz/gallery/folders/{id}`           |                                    | 204; rejects `output`/`input`          |
| POST   | `/xyz/gallery/folders/{id}/rescan`    |                                    | `{ "scheduled": true }`                |

### 7.3 Images — listing & detail

| Method | Path                                  | Notes                                                                                              |
| ------ | ------------------------------------- | -------------------------------------------------------------------------------------------------- |
| GET    | `/xyz/gallery/images`                 | Query: `FilterSpec` flattened + `SortSpec` + `cursor` + `limit` (default 200). Returns `{ items: [ImageRecord], next_cursor, total_estimate }`. Cursor-based for stable scrolling. |
| GET    | `/xyz/gallery/images/count`           | Same query → `{ "total": int }`. Used by virtual scroll height estimate when needed.               |
| GET    | `/xyz/gallery/image/{id}`             | Full `ImageRecord`.                                                                                |
| GET    | `/xyz/gallery/image/{id}/neighbors`   | Query: same `FilterSpec`+`SortSpec` → `{ prev_id, next_id }`. Powers the detail-page nav buttons.  |

### 7.4 Images — binary

| Method | Path                                    | Notes                                                                            |
| ------ | --------------------------------------- | -------------------------------------------------------------------------------- |
| GET    | `/xyz/gallery/thumb/{id}?v={mtime_ns}`  | Returns the cached WebP thumbnail; generates on-demand if absent. `Cache-Control: public, max-age=31536000, immutable` (key includes `mtime_ns`). |
| GET    | `/xyz/gallery/raw/{id}`                 | Streams the original file. Supports HTTP `Range`. `Content-Disposition: inline`. |
| GET    | `/xyz/gallery/raw/{id}/download`        | Same content; `Content-Disposition: attachment`.                                 |
| GET    | `/xyz/gallery/image/{id}/workflow.json` | Extracted workflow; 404 if absent.                                               |

### 7.5 Mutations — single image

| Method | Path                                          | Body                                            | Notes |
| ------ | --------------------------------------------- | ----------------------------------------------- | ----- |
| PATCH  | `/xyz/gallery/image/{id}`                     | `{ "favorite"?: bool, "tags"?: [str] }`         | Updates DB **and** PNG chunks atomically. |
| DELETE | `/xyz/gallery/image/{id}`                     | `{ "confirm": true }`                           | Hard delete from disk and index.          |
| POST   | `/xyz/gallery/image/{id}/move`                | `{ "target_folder_id": int, "rename"?: str }`  | If `rename` is omitted and a collision exists, returns `409` with a suggested name; client retries with `rename`. |

### 7.6 Mutations — bulk

> **Selection model.** Every bulk endpoint accepts the polymorphic
> `Selection` envelope (§6.2). For `mode = "all_except"` the backend
> resolves the target rowset with a single subquery (the same subquery
> the listing endpoint would use, minus pagination) and applies
> `WHERE id NOT IN (excluded_ids)`. The frontend therefore never
> serialises a 100 000-id array over HTTP.

| Method | Path                                  | Body                                                                                                | Notes |
| ------ | ------------------------------------- | --------------------------------------------------------------------------------------------------- | ----- |
| POST   | `/xyz/gallery/bulk/favorite`          | `{ "selection": Selection, "value": bool }`                                                         | Single transaction; emits one `vocab.changed` (no-op) + one summary `image.updated` per affected id. |
| POST   | `/xyz/gallery/bulk/tags`              | `{ "selection": Selection, "add": [str], "remove": [str] }`                                         | Tags are normalised the same way as prompt tokens (§8.8) before write. |
| POST   | `/xyz/gallery/bulk/move/preflight`    | `{ "selection": Selection, "target_folder_id": int }`                                               | **Phase 1 of the two-phase move (§8.7).** Pure read + in-memory simulation: validates target writability, estimates required free bytes, and returns `{ plan_id, total_bytes, free_bytes, mappings: [{id, src, dst, conflict?: "renamed"\|"clean"}], unresolved_conflicts: [...] }`. No file is touched. |
| POST   | `/xyz/gallery/bulk/move/execute`      | `{ "plan_id": str, "rename_overrides"?: { "<id>": "<new_name>" } }`                                 | **Phase 2.** Server replays the previously-validated plan, performs every `os.replace`, then commits all path changes inside one SQLite transaction. Partial-failure rollback is best-effort: any successfully-moved file is recorded in the DB before a later failure aborts the plan, so on-disk state is always consistent with the index. |
| POST   | `/xyz/gallery/bulk/delete`            | `{ "selection": Selection, "confirm": true }`                                                       | Same pre-flight pattern: dry-run resolves the row set first, then physical deletes are batched in 200-row chunks per WS heartbeat. |
| POST   | `/xyz/gallery/bulk/resolve_selection` | `{ "selection": Selection, "limit"?: int }`                                                         | Diagnostics endpoint: returns the resolved id count (and optionally the first `limit` ids) without performing any mutation. Used by the confirm modal to display "you are about to affect N files".|

### 7.7 Vocab / autocomplete

| Method | Path                              | Query                        | Returns                                          |
| ------ | --------------------------------- | ---------------------------- | ------------------------------------------------ |
| GET    | `/xyz/gallery/vocab/tags`         | `?prefix=...&limit=20`       | `[ { name, usage_count } ]`, sorted by `usage_count desc, name asc`. |
| GET    | `/xyz/gallery/vocab/prompts`      | `?prefix=...&limit=20`       | same shape over `prompt_token`.                  |
| GET    | `/xyz/gallery/vocab/models`       |                              | `[str]` distinct model names.                    |

### 7.8 Index lifecycle

| Method | Path                              | Notes                                                                 |
| ------ | --------------------------------- | --------------------------------------------------------------------- |
| GET    | `/xyz/gallery/index/status`       | `{ scanning: bool, pending_events: int, last_full_scan_at, totals }`. |
| POST   | `/xyz/gallery/index/rebuild`      | Wipes index + thumbnails, re-scans roots in background.               |

### 7.9 WebSocket

`ws://.../xyz/gallery/ws` — server → client only (client may send pings).

Event envelope:
```text
{ "type": <string>, "data": <object>, "ts": <epoch_ms> }
```

| Type                | Data                                              | When                                            |
| ------------------- | ------------------------------------------------- | ----------------------------------------------- |
| `image.upserted`    | `ImageRecord` (compact)                           | After indexing a new or modified file           |
| `image.deleted`     | `{ "id": int, "path": str }`                      | After a file is removed from disk               |
| `image.updated`     | `{ "id": int, "favorite"?, "tags"?, "moved_to"? }`| After a mutation API call                       |
| `folder.changed`    | `FolderNode` (subtree)                            | After a folder add/remove/rename                |
| `index.progress`    | `{ done, total, phase }`                          | During a full scan / rebuild                    |
| `vocab.changed`     | `{ "kind": "tag"\|"prompt", "added":[], "removed":[] }` | After tag/prompt vocab deltas             |

> **Consistency model — deliberately simple.** This is a single-user
> local plugin. We do **not** introduce per-event sequence numbers, vector
> clocks, or strict-ordering buffers; the WS channel is fire-and-forget
> "backend pushes, frontend patches local state". The only safety net is
> a lightweight reconciliation pass that the frontend triggers on
> `window.onfocus` (and on WS reconnect): a single `GET
> /xyz/gallery/index/status` plus, if its `last_event_ts` is newer than
> the last event the tab actually applied, a `GET /xyz/gallery/images`
> for the currently visible window. This catches missed events from
> short disconnects without paying the complexity cost of a fully
> ordered protocol.

### 7.10 Error envelope

All errors return:
```text
{ "error": { "code": "<machine_code>", "message": "<human>", "details"?: {...} } }
```
HTTP status follows REST conventions (`400` validation, `404` missing,
`409` conflict for collisions, `500` unexpected).

---

## 8. Performance Strategy

### 8.1 Indexing

* **First scan** walks the registered roots once, in a background thread,
  in batches of 500 files per DB transaction (`BEGIN ... COMMIT`).
* Per file: `stat()` first; if `(size, mtime_ns)` matches the cached row,
  **skip everything else** (this makes restarts ~free).
* Otherwise: open with Pillow only to read header dims and PNG text
  chunks; close immediately. Thumbnails are **not** generated during
  indexing — they're produced lazily on first request, then cached.
* `xxhash64` is computed only on demand (e.g. dedupe view), never during
  the bulk scan.
* SQLite is opened with:
  * `PRAGMA journal_mode = WAL;`
  * `PRAGMA synchronous = NORMAL;`
  * `PRAGMA temp_store = MEMORY;`
  * `PRAGMA mmap_size = 256 MiB;`

### 8.2 Live updates — Dict Coalescing + Delta-Scan fallback

A naive `queue.Queue` consumer collapses under real-world event storms
(unzip of a 5 000-file archive, `git pull` over the output folder,
syncing a Dropbox / OneDrive folder). At ~1 000 events/s we hit two
failure modes simultaneously: queue overflow drops events silently, and
SQLite contention causes `database is locked` errors that propagate
back to the indexer thread. The watcher therefore uses a
**dict-coalescing buffer** in front of the indexer, with an automatic
fallback to a **bounded delta scan** when the buffer saturates.

**Pipeline.**

```
watchdog raw events ──►  Coalescer (in-memory dict)  ──► Indexer worker
                              │                                 │
                              │  if len(buffer) > HIGH_WATERMARK│
                              ▼                                 ▼
                         clear buffer                  one delta-scan task
                              │                                 │
                              └────────────►  scheduler  ◄──────┘
```

**Coalescer rules** (`watcher.Coalescer`):

* Keyed by absolute path. Value is the *latest observed* event kind +
  the timestamp of the most recent occurrence. Repeated events on the
  same path within the debounce window collapse into a single pending
  entry — `created` then `modified` ⇒ `upserted`; `created` then
  `deleted` ⇒ entry dropped entirely; `moved(a → b)` is split into
  `deleted(a)` + `upserted(b)` so it composes with everything else.
* A background timer drains entries older than `DEBOUNCE_MS` (default
  250 ms) into the indexer in micro-batches of up to 50, each wrapped
  in a single SQLite transaction.
* The coalescer has a hard size cap, `HIGH_WATERMARK = 500`. When the
  buffer would exceed it the watcher drops the in-memory buffer
  entirely and schedules **one** `delta_scan(folder_id)` task per
  affected registered root instead. This is strictly cheaper than
  draining hundreds of correlated events one-by-one, and it
  guarantees correctness because `delta_scan` re-derives the truth
  from `(path, size, mtime_ns)` directly (the same fingerprint used
  by the cold-start indexer, §8.1).
* Delta-scan tasks themselves are coalesced: only one scan can be
  in-flight per root at a time; while one is running, additional
  triggers for the same root just set a `dirty` flag that re-arms the
  scan when the current one finishes.

Pseudo-code:

```python
class Coalescer:
    DEBOUNCE_MS = 250
    HIGH_WATERMARK = 500
    FLUSH_BATCH = 50

    def __init__(self, indexer, scheduler):
        self._buf: dict[str, _PendingEvent] = {}
        self._lock = threading.Lock()
        self._indexer = indexer
        self._scheduler = scheduler

    def on_event(self, path: str, kind: EventKind, root: FolderRoot):
        with self._lock:
            prev = self._buf.get(path)
            merged = _merge(prev, kind)            # upsert+delete=drop, etc.
            if merged is None:
                self._buf.pop(path, None)
            else:
                self._buf[path] = _PendingEvent(merged, time.monotonic_ns())

            if len(self._buf) >= self.HIGH_WATERMARK:
                self._buf.clear()
                self._scheduler.request_delta_scan(root)
                return

    def drain_due(self):
        now = time.monotonic_ns()
        cutoff = now - self.DEBOUNCE_MS * 1_000_000
        with self._lock:
            ready = [(p, e) for p, e in self._buf.items() if e.ts <= cutoff]
            for p, _ in ready:
                self._buf.pop(p, None)

        for batch in _chunks(ready, self.FLUSH_BATCH):
            self._indexer.apply_batch(batch)        # one SQLite TX per batch
```

### 8.3 Thumbnails — SQLite-tracked LRU

* Format: **WebP** quality 78, generated with Pillow's `thumbnail`
  using `Image.Resampling.LANCZOS`, max 320 × 320, then cropped to the
  card's display ratio (`object-fit: cover` is achieved server-side to
  avoid sending oversized images).
* Generation runs in a `concurrent.futures.ProcessPoolExecutor`
  (bypasses the GIL; image decode is CPU-bound), bounded to
  `min(4, cpu_count)` workers.
* Disk cache key = `sha1(path + mtime_ns)`, sharded into 256 sub-dirs by
  the first 2 hex chars of the key.
* HTTP responses use long-lived immutable caching keyed on `mtime_ns`
  in the URL, so the browser never re-fetches an unchanged thumbnail.

**LRU bookkeeping.** Eviction is driven by the `thumbnail_cache` table
(§6.1), not by `os.scandir` over 100 k+ shards. The previous design's
"walk the cache directory and `stat()` every file to find the oldest"
costs seconds on cold cache and easily 100 ms on warm cache; the table
turns it into a single indexed query.

* On every served `GET /xyz/gallery/thumb/{id}`:
  ```sql
  UPDATE thumbnail_cache
     SET last_accessed = :now
   WHERE hash_key = :hash;
  ```
  Performed asynchronously after the response is flushed (the HTTP
  request never waits on it). To avoid write amplification we batch
  these touches: the route only marks the hash in an in-memory set,
  and a background task flushes the set every 10 s with a single
  `executemany`. A 10 s window of inaccurate `last_accessed` is
  irrelevant for an LRU whose budget is measured in days.
* On generation: insert into `thumbnail_cache(hash_key, image_id,
  size_bytes, created_at, last_accessed)` inside the same transaction
  that materialises the file on disk.
* Eviction (triggered after each insert, throttled to once per 30 s):
  ```sql
  -- 1. how big are we?
  SELECT COALESCE(SUM(size_bytes), 0) FROM thumbnail_cache;

  -- 2. if over budget, pick victims (drop until we are under 80 % of budget)
  SELECT hash_key, size_bytes
    FROM thumbnail_cache
   ORDER BY last_accessed ASC
   LIMIT :batch;
  ```
  For each victim: `os.unlink(path_for(hash_key))` then
  `DELETE FROM thumbnail_cache WHERE hash_key = ?`, all inside one
  transaction so a crash never leaves an orphan row.
* A daily janitor reconciles drift in both directions (file present
  on disk but no DB row → delete file; row present but file missing →
  delete row). This keeps the table authoritative even after a hard
  crash or a manual `rm` of the thumbs dir.

### 8.4 Query performance

* Every filter dimension is backed by either a B-tree index or an
  inverted join table — no full scans on the hot path.

**Tag / prompt-token AND filter — short-circuit strategy.**
The previous draft used `GROUP BY image_id HAVING COUNT(DISTINCT tag_id) = N`.
That works at 5 000 rows but degrades sharply by 100 000+: SQLite must
materialise the full `image_tag` rowset for every requested tag, then
sort, then aggregate, even when the answer is provably empty after the
first tag. We replace it with a strategy SQLite's planner can actually
short-circuit.

Two equivalent forms are accepted by `repo.list_images`; the planner
chooses based on tag selectivity (provided via the `usage_count`
hints), but both share the *driving table = rarest tag* invariant:

```sql
-- Form A: nested EXISTS, driven by the rarest tag.
-- Selectivity is exploited via the order in which we resolve tag IDs
-- in Python: rarest first (smallest usage_count), so the outer scan
-- is the smallest possible set, and each EXISTS short-circuits per row.
SELECT i.*
  FROM image AS i
  JOIN image_tag AS it0
    ON it0.image_id = i.id AND it0.tag_id = :tag_id_rarest
 WHERE EXISTS (SELECT 1 FROM image_tag
                WHERE image_id = i.id AND tag_id = :tag_id_2)
   AND EXISTS (SELECT 1 FROM image_tag
                WHERE image_id = i.id AND tag_id = :tag_id_3)
   -- ... one EXISTS per remaining tag ...
   AND i.folder_id IN (:folder_ids)        -- folder scope, optional
   AND (:fav IS NULL OR i.favorite = :fav) -- favourite filter, optional
 ORDER BY i.created_at DESC, i.id DESC
 LIMIT :limit;
```

```sql
-- Form B: INTERSECT of inverted lists.
-- Preferred when N >= 4 tags AND every tag has comparable cardinality;
-- INTERSECT lets SQLite stream-merge sorted id lists without a hash
-- aggregate.
SELECT image_id FROM image_tag WHERE tag_id = :tag_id_rarest
INTERSECT
SELECT image_id FROM image_tag WHERE tag_id = :tag_id_2
INTERSECT
SELECT image_id FROM image_tag WHERE tag_id = :tag_id_3
-- ...
;
-- Then JOIN the resulting id set back to `image` for projection + sort.
```

`repo.py` builds the SQL dynamically from the resolved `tag_id` list:

```python
def build_tag_and_query(tag_ids: list[int], extras: FilterExtras) -> Query:
    # Resolve ids in Python first, then sort by usage_count ASC so the
    # rarest tag drives the join. Empty resolution → return empty.
    if not tag_ids:
        return EMPTY_QUERY
    ordered = sorted(tag_ids, key=lambda t: vocab.usage_count(t))
    rarest, *rest = ordered

    if len(ordered) >= 4 and _all_dense(ordered):
        return _intersect_form(rarest, rest, extras)
    return _exists_form(rarest, rest, extras)
```

The exact same construction is used for prompt tokens against
`image_prompt_token`. Combined tag-AND + prompt-AND filters are
expressed as additional `EXISTS` clauses against the second table —
SQLite's planner happily reuses the same driving row.

* Name substring filter:
  * length < 3 chars → simple `LIKE '%x%'` on `filename_lc` (acceptable
    even at 50 k rows because `filename_lc` is < 100 bytes/row),
  * length ≥ 3 chars → FTS5 `MATCH 'x*'` for prefix tokens.
* Sorting + pagination is **cursor-based** on `(sort_key, id)` — never
  `OFFSET` — so deep scrolling stays O(log N).
* Counts: server returns an **estimate** for very large result sets
  (`SELECT COUNT(*)` capped at a budget of 25 ms; otherwise reports
  `total_estimate` flagged as approximate). Exact counts only when the
  client requests `/images/count` explicitly (used for `Select all`).

### 8.5 Autocomplete

* `tag.name` and `prompt_token.token` columns are `COLLATE NOCASE` and
  indexed.
* Suggestion query:
  ```text
  SELECT name FROM tag
   WHERE name LIKE :prefix || '%'
   ORDER BY usage_count DESC, name ASC
   LIMIT 20;
  ```
* Frontend additionally caches per-prefix results in an in-memory LRU
  to suppress duplicate keystroke fetches.

### 8.6 Frontend rendering

* **Virtual scroll**: a windowed grid renders only the rows whose
  bounding box intersects the viewport ± 2 viewport heights. The
  grid's total height is computed from the (estimated) total count
  and the slider-controlled card size.
* **Image decode**: `<img loading="lazy" decoding="async">`, plus
  `IntersectionObserver` to assign `src` only when the card is within
  500 px of the viewport. Off-screen `<img>` elements have `src`
  cleared on aggressive evictions to keep GPU memory bounded.
* **State**: a single observable store. Selection uses the polymorphic
  `Selection` envelope (§6.2), **never** a `Set<100_000_ids>`:

  ```ts
  type SelectionState =
    | { mode: 'explicit';  ids: Set<number> }
    | { mode: 'all_except'; filters: FilterSpec; excludedIds: Set<number> };
  ```

  Toggling a single card mutates `ids` (explicit) or `excludedIds`
  (all_except) — both O(1). Clicking *Select all in current view*
  flips into `all_except` with `excludedIds = ∅` and an immutable
  snapshot of the active `FilterSpec`. Bulk endpoints accept this
  envelope verbatim, so the wire payload of "select everything in a
  100 000-image gallery" is < 200 bytes regardless of library size.
  Visual rendering of "is this card checked?" is derived:
  `(mode === 'explicit' ? ids.has(id) : !excludedIds.has(id))`.
* **WS reconciliation**: incoming `image.upserted` / `image.deleted`
  events patch the local index of the current query. If the event
  doesn't match the current `FilterSpec`, the count is bumped /
  decremented but no card is added/removed.
* **Focus reconciliation**: on `window.onfocus` (and on WS reconnect)
  the store fires a single `GET /xyz/gallery/index/status`. If the
  server's `last_event_ts` is newer than the most recently applied
  event in this tab, the store re-fetches just the currently visible
  page of `/xyz/gallery/images`. This is the *entire* drift-recovery
  mechanism — see the WS consistency note in §7.9.
* **Routing**: client-side hash router (`#/`, `#/image/<id>`) so
  Back/Forward and direct links work without server roundtrips.
* **Persisted UI state**: filter values, sort, layout, cards-per-row,
  recursive toggle, and the "main view" scroll position are stored in
  `localStorage` and restored on next visit.

### 8.7 Move / delete throughput — two-phase Pre-flight + Execution

A naive loop `for src in selection: os.replace(src, dst)` cannot be
rolled back: if file 437 of 500 fails (target dir suddenly read-only,
disk full, name collision discovered mid-flight), the first 436 are
already moved and the SQLite paths are now lying. We therefore split
every bulk move into two strictly-ordered phases.

**Phase 1 — Pre-flight (`POST /xyz/gallery/bulk/move/preflight`).**
Pure read + in-memory simulation, **no filesystem write**. Returns a
`plan_id` keyed in a short-lived in-memory store (TTL 5 min).

```python
def preflight_move(selection: Selection, target: FolderRow) -> MovePlan:
    ids = repo.resolve_selection(selection)             # SQL, never list expansion
    rows = repo.get_paths(ids)                          # [(id, src_abs)]

    # 1. Sandbox + writability.
    paths.assert_inside_root(target.path)
    if not os.access(target.path, os.W_OK):
        raise PreflightError("target_not_writable", target=target.path)

    # 2. Disk space estimate.
    total_bytes = sum(r.file_size for r in rows)
    free_bytes  = shutil.disk_usage(target.path).free
    if total_bytes > free_bytes * 0.95:                 # 5 % safety margin
        raise PreflightError("insufficient_space",
                             needed=total_bytes, free=free_bytes)

    # 3. Conflict resolution. Build the full src→dst mapping in memory,
    #    accounting for collisions both with existing files in the target
    #    AND with other files inside the same batch.
    taken: set[str] = set(_listdir_lower(target.path))
    mappings: list[Mapping] = []
    for r in rows:
        candidate = r.filename
        if candidate.lower() in taken:
            candidate = _next_free_name(r.filename, taken)   # "foo (1).png", "(2)" ...
        taken.add(candidate.lower())
        mappings.append(Mapping(
            id=r.id, src=r.path, dst=os.path.join(target.path, candidate),
            conflict="renamed" if candidate != r.filename else "clean",
        ))

    plan = MovePlan(id=uuid4().hex, target=target, mappings=mappings,
                    total_bytes=total_bytes, expires_at=now() + 300)
    PLAN_STORE.put(plan)
    return plan
```

The frontend renders the plan, lets the user override individual
renames (`rename_overrides`), and only then calls Phase 2.

**Phase 2 — Execution (`POST /xyz/gallery/bulk/move/execute`).**
Replays the validated plan. Filesystem moves first (in chunks, with WS
progress events), then **one** SQLite transaction commits every
`UPDATE image SET path = ?, folder_id = ?, relative_path = ?` and the
matching `image_tag` / `image_prompt_token` rows are unaffected (they
key on `image_id`, not path).

```python
def execute_move(plan_id: str, overrides: dict[int, str]) -> MoveResult:
    plan = PLAN_STORE.pop(plan_id)
    if plan is None or plan.expires_at < now():
        raise ExecError("plan_expired_or_unknown")

    plan = _apply_overrides(plan, overrides)
    _re_check_conflicts(plan)              # cheap: just listdir + set diff

    moved: list[Mapping] = []
    try:
        for m in plan.mappings:
            try:
                os.replace(m.src, m.dst)                       # atomic intra-volume
            except OSError:                                    # cross-volume
                shutil.copy2(m.src, m.dst)
                _verify_size(m.src, m.dst)
                os.unlink(m.src)
            moved.append(m)
            ws_hub.broadcast_progress(plan_id, len(moved), len(plan.mappings))
    finally:
        # Whatever ACTUALLY moved, we record. The DB never disagrees with
        # what is on disk. A partial failure leaves a partially-moved
        # batch but ZERO inconsistency between the index and reality.
        with repo.tx() as tx:
            for m in moved:
                tx.update_image_path(m.id, m.dst, plan.target.id)

    return MoveResult(moved=len(moved), planned=len(plan.mappings))
```

**Bulk delete** follows the same shape but Phase 1 only checks
sandbox + selection resolution; Phase 2 deletes in 200-row chunks with
a transaction per chunk (intermediate crashes leave the index
truthful). All bulk operations stream `image.updated` /
`image.deleted` events as they make progress, so the UI never waits
on the full batch.

---

### 8.8 Prompt Normalization Pipeline

A bare `text.split(',')` is catastrophic for the `prompt_token`
vocabulary. On a 50 000-image library it produces *hundreds of
thousands* of distinct rows because `(masterpiece:1.2)`,
`(masterpiece:1.3)`, `( masterpiece :1.4)`, `<lora:add_detail:0.6>`,
`masterpiece.`, and `masterpiece` all hash to different strings.
Autocomplete becomes useless and the table becomes a write
hotspot. Every prompt — both at index time (`indexer`) and at
query time (filter input) — therefore goes through a single
`vocab.normalize_prompt()` function.

**Pipeline stages** (applied in order, all on lower-cased input):

1. **Strip LoRA / hyper-network tags** — drop the entire
   `<lora:name:weight>` / `<lyco:...>` / `<hypernet:...>` fragment.
   These are syntax, not vocabulary; we may later index them in a
   separate `image_lora` table, but they never enter `prompt_token`.
2. **Strip BREAK / AND / control keywords** — A1111-style
   `BREAK`, `AND`, `ADDCOMM`, etc., are dropped.
3. **Unwrap weight syntax** — `(word:1.5)` → `word`,
   `[word:0.7]` → `word`, nested `((word))` → `word`. The numeric
   weight itself is discarded.
4. **Strip leftover grouping punctuation** — `()`, `[]`, `{}`, `\`.
5. **Split on commas and `|`** — these are the only real token
   separators in SD-style prompts.
6. **Per-token clean-up** — collapse internal whitespace, trim
   leading/trailing punctuation (`.,;:`), drop tokens that are
   numeric-only, single-character, or > 64 characters.
7. **Stop-word filter** — a small built-in deny-list (`a`, `an`,
   `the`, `of`, `and`, …) plus user-extensible `gallery_config.json
   :: prompt_stopwords`.
8. **Deduplicate** within the same image (set semantics).

```python
# vocab.py  —  pure functions, no I/O
import re

_RE_LORA      = re.compile(r"<(?:lora|lyco|hypernet)\s*:[^>]+>",  re.IGNORECASE)
_RE_KEYWORD   = re.compile(r"\b(BREAK|AND|ADDCOMM|ADDBASE)\b")
# Recursive weight unwrap: (word:1.5)  /  [word:0.7]  /  {word}  /  ((word))
_RE_WEIGHTED  = re.compile(r"[\(\[\{]\s*([^\(\)\[\]\{\}:]+?)\s*(?::\s*-?\d*\.?\d+)?\s*[\)\]\}]")
_RE_PUNCT     = re.compile(r"[\(\)\[\]\{\}\\]")
_RE_SPLIT     = re.compile(r"[,\|]+")
_RE_WS        = re.compile(r"\s+")
_RE_TRIM      = re.compile(r"^[\.,;:!\?\-_]+|[\.,;:!\?\-_]+$")
_RE_NUM_ONLY  = re.compile(r"^\d+(?:\.\d+)?$")

_DEFAULT_STOP = frozenset({
    "a", "an", "the", "of", "and", "or", "with", "in", "on", "for",
    "to", "by", "at", "is", "as",
})

def normalize_prompt(text: str | None,
                     extra_stopwords: frozenset[str] = frozenset()
                     ) -> list[str]:
    if not text:
        return []
    s = text.lower()

    # 1. LoRA / hyper-network tags - removed wholesale.
    s = _RE_LORA.sub(" ", s)
    # 2. Pipeline keywords.
    s = _RE_KEYWORD.sub(" ", s)
    # 3. Recursively unwrap weight syntax until a fixed point is reached.
    for _ in range(8):                  # bounded; deep nesting is pathological
        new_s = _RE_WEIGHTED.sub(r"\1", s)
        if new_s == s:
            break
        s = new_s
    # 4. Drop leftover grouping punctuation.
    s = _RE_PUNCT.sub(" ", s)

    # 5. Real token split.
    raw_tokens = _RE_SPLIT.split(s)

    stopwords = _DEFAULT_STOP | extra_stopwords
    out: list[str] = []
    seen: set[str] = set()
    for t in raw_tokens:
        # 6. Per-token clean-up.
        t = _RE_WS.sub(" ", t).strip()
        t = _RE_TRIM.sub("", t).strip()
        if not t or len(t) == 1 or len(t) > 64:
            continue
        if _RE_NUM_ONLY.match(t):
            continue
        # 7. Stop-words.
        if t in stopwords:
            continue
        # 8. Per-image dedup.
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out
```

Two consequences worth calling out:

* **Tag normalisation reuses the same function.** Bulk tag input
  (`POST /xyz/gallery/bulk/tags`) is run through `normalize_prompt`
  with an empty stopword set so that tags like `My Tag`, `my tag`,
  and `(my tag:1.2)` are treated as a single canonical `my tag`.
* **Re-indexing is required when the stopword set changes.** A
  config-bump increments `vocab_version` in `gallery_config.json`;
  the indexer detects the bump on next start and re-derives
  `image_prompt_token` for every row whose `image.indexed_at <
  vocab_version_changed_at`. This is incremental — it does not
  re-read PNG headers — so it costs seconds, not minutes.

---

## 9. Out of Scope (v1)

* Multi-user auth (gallery inherits ComfyUI's existing access model).
* Cloud storage backends.
* Image editing / re-generation from the gallery (the "send to ComfyUI"
  flow is left for a future spec).
* Trash / undo for deletes (deletes are immediate after confirmation).
* Mobile-first layout (the SPA is responsive but optimised for
  desktop ≥ 1280 px wide).

---

## 10. Open Questions (to confirm before implementation)

1. **Frontend stack**: vanilla TS + custom virtual grid, or Vue 3 ESM
   via importmap (no build step), or pre-bundled React via Vite? All
   three satisfy C-9; default recommendation is **Vue 3 + importmap**
   for fastest iteration without a build pipeline shipped to users.
2. ~~**Tag/prompt token normalisation**: lower-case + trim is mandatory;
   should we also strip leading `(weight)` syntax …?~~ **Resolved:**
   see §8.8 *Prompt Normalization Pipeline*. Weight syntax, LoRA tags,
   control keywords, and stopwords are all stripped; the canonical
   pipeline is a single function (`vocab.normalize_prompt`) used by
   both the indexer and the filter input.
3. **Workflow extraction**: extract from the `workflow` PNG chunk
   only, or also fall back to the legacy `parameters` chunk used by
   some forks? Default = **both**, prefer `workflow`.
4. **Date semantics**: "creation date" should prefer the ComfyUI
   metadata timestamp if present, otherwise file `ctime`, otherwise
   `mtime`. Confirm preference order.
5. **Custom folder sandbox**: should we forbid registering a custom
   folder that is an ancestor / descendant of an already-registered
   one (to avoid double-indexing)? Default = **forbid overlap**.
