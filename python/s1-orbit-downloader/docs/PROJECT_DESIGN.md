# Sentinel 数据与精密轨道下载管理系统设计

## 目标

把当前命令行下载器扩展成一个本地化的 Sentinel-1 数据管理系统。系统需要支持按行政区、手绘范围、bbox、GeoJSON/WKT 查询影像，选择下载任务，自动下载 Sentinel-1 数据和对应精密轨道文件，并长期管理任务、文件、状态和日志。

第一阶段重点服务 Sentinel-1 SLC/GRD 数据和 `AUX_POEORB` 精密轨道；后续架构保留接入 Sentinel-2/3、Copernicus Data Space、批量处理流程的空间。

## 当前基础

已有能力：

- `s1-dl search`：通过 ASF Search 按 AOI 和时间查询 Sentinel-1。
- `s1-dl download`：查询后下载 Sentinel-1 产品，并下载匹配轨道。
- `s1-dl orbits`：为已有场景名、`.zip`、`.SAFE` 补下载轨道。
- Python 环境由 `uv` 管理。

项目下已有 `全国行政区.geojson`：

- 文件大小约 53MB。
- 顶层类型为 `FeatureCollection`。
- 要素数：477。
- 常见属性：`adcode`、`name`、`center`、`centroid`、`childrenNum`、`level`、`parent`、`acroutes`、`treeID`。
- `level` 分布：多数为 `city`，少量 `district`，省级要素不完整。
- 牡丹江市要素：`adcode=231000`、`name=牡丹江市`、`level=city`、`parent.adcode=230000`。
- 牡丹江市边界范围：`128.232144,43.425798,131.310629,45.9875`。

设计结论：不能每次页面加载都直接解析 53MB GeoJSON。应在首次启动或数据更新时导入 SQLite，建立行政区索引、bbox、简化 WKT，并用内置省份 adcode 表补齐省级树。

## 产品形态

推荐形态：本地 Web 管理器 + 保留 CLI。

```text
浏览器页面
  区域选择、地图查看、查询条件、结果表格、任务监控

FastAPI 后端
  行政区查询、ASF 查询、下载任务、轨道匹配、文件管理

SQLite 数据库
  项目、AOI、搜索任务、场景、下载记录、日志、设置

文件仓库
  Sentinel-1 zip、轨道 EOF、manifest、任务日志

CLI
  保留自动化和批处理入口，复用后端 service 层
```

前端建议使用 Vite + React + TypeScript + Leaflet/MapLibre；后端使用 FastAPI + SQLAlchemy/SQLModel + SQLite。这样后端仍是 Python，能复用现有 ASF 和轨道下载逻辑；前端只负责交互和展示。

如果要先快速交付，也可以用 Streamlit 做 MVP。但作为长期项目，FastAPI + 独立前端更适合任务状态、日志、地图交互和后续扩展。

## 核心流程

### 1. 首次启动

1. 检查 `app.db` 是否存在。
2. 检查行政区索引版本。
3. 如果未导入，读取 `全国行政区.geojson`。
4. 为每个要素计算：
   - 原始 GeoJSON 几何。
   - bbox。
   - 中心点。
   - 原始 WKT。
   - 查询用简化 WKT。
   - 几何 hash。
5. 根据 `parent.adcode` 和内置省份表生成省-市-区县树。
6. 写入 `regions` 表。

### 2. 创建项目

用户创建一个项目，例如：

```text
项目名：牡丹江积雪/形变数据
数据根目录：D:\Sentinel\Mudanjiang
默认产品：SLC
默认波束：IW
默认下载并发：4
```

项目用于隔离任务、下载目录和 manifest。

### 3. 选择 AOI

支持四种来源：

- 行政区：省/市/区县选择，例如 `黑龙江省 -> 牡丹江市`。
- bbox：输入 `min_lon,min_lat,max_lon,max_lat`。
- 上传文件：GeoJSON/WKT。
- 地图绘制：画矩形或多边形。

对于行政区 AOI，系统默认使用行政区边界的简化 WKT 查询 ASF。页面允许切换：

- 精确边界：减少周边误匹配，但 WKT 更长。
- 简化边界：默认推荐。
- bbox：速度快，但会包含边界外数据。

### 4. 查询 Sentinel-1

用户设置：

- 时间范围。
- 产品级别：`SLC`、`GRD_HD`、`GRD_MD`、`OCN`。
- 波束：默认 `IW`。
- 升降轨：`ASCENDING` / `DESCENDING` / 不限。
- 极化：`VV`、`VH`、`VV+VH` 等。
- 相对轨道号：可选。
- 最大结果数。

后端调用 ASF Search，结果写入：

- `search_jobs`
- `scenes`
- `job_scenes`

前端展示可筛选表格：

- 场景名。
- 开始/结束时间。
- 卫星：S1A/S1B/S1C/S1D。
- 产品级别。
- 升降轨。
- 相对轨道。
- 极化。
- 文件大小。
- 是否已有本地产品。
- 是否已有轨道。

### 5. 创建下载任务

用户勾选场景后创建下载任务。任务分三段：

1. 产品下载。
2. 轨道下载。
3. 文件核查和状态归档。

下载任务需要支持：

- 暂停。
- 取消。
- 失败重试。
- 跳过已存在文件。
- 单独补轨道。
- 只查询不下载。
- 只下载轨道。

### 6. 下载数据

产品下载通过 ASF Session 使用 NASA Earthdata 账号。账号密码不写入数据库明文，优先使用：

- 环境变量：`EARTHDATA_USER`、`EARTHDATA_PASS`。
- Windows Credential Manager/keyring。
- 页面临时输入，只保存在内存 session。

下载目录按项目和任务组织：

```text
<data_root>\
  projects\
    <project_slug>\
      jobs\
        <job_id>_<area>_<start>_<end>\
          data\
            S1A_....zip
          orbits\
            S1A_OPER_AUX_POEORB_....EOF
          manifest.csv
          manifest.json
          logs\
            job.log
```

同一个场景如果已在仓库里存在，系统通过 `scene_id` 和文件路径复用，不重复下载。

### 7. 下载精密轨道

轨道不是按位置查询，而是按 Sentinel-1 场景名匹配：

```text
场景名 -> 卫星平台 + 成像时间 -> AUX_POEORB EOF
```

系统行为：

- 默认优先 `AUX_POEORB`。
- 如果精密轨道暂不可用，可允许回退 `AUX_RESORB`，并在 UI 中明确标记。
- 轨道下载失败不应阻断已下载产品，但任务状态应显示 `产品完成 / 轨道失败`。
- 支持后续“一键补齐精密轨道”。

## 系统架构

### 后端模块

建议目录：

```text
src/sentinel_orbit_downloader/
  api/
    app.py                 # FastAPI app
    routes_regions.py
    routes_projects.py
    routes_search.py
    routes_downloads.py
    schemas.py             # API DTO
  core/
    config.py              # 路径、并发、凭据配置
    paths.py               # 文件目录规范
    logging.py
  domain/
    enums.py
    models.py              # 领域对象，不绑定数据库
  services/
    region_catalog.py      # 行政区导入和查询
    aoi.py                 # AOI 转换、简化、bbox
    asf_client.py          # ASF 查询和下载适配
    orbit_client.py        # s1-orbits 适配
    download_manager.py    # 下载编排
    job_runner.py          # 后台任务执行
    inventory.py           # 本地文件扫描和去重
  storage/
    db.py
    orm.py
    repositories.py
    migrations/
  cli.py                   # 继续保留 CLI，调用 services
```

前端建议目录：

```text
frontend/
  package.json
  src/
    api/
    components/
    pages/
    styles/
```

### 数据库模型

#### settings

保存本地配置。

| 字段 | 说明 |
| --- | --- |
| key | 配置名 |
| value | 配置值 |
| updated_at | 更新时间 |

#### regions

行政区索引。

| 字段 | 说明 |
| --- | --- |
| adcode | 行政区代码 |
| name | 名称 |
| level | `country/province/city/district/custom` |
| parent_adcode | 父级代码 |
| province_adcode | 省级代码 |
| center_lon/center_lat | 中心点 |
| min_lon/min_lat/max_lon/max_lat | bbox |
| geometry_json | 原始几何 |
| wkt | 原始 WKT |
| simplified_wkt | ASF 查询用简化 WKT |
| geometry_hash | 几何 hash |

#### projects

用户项目。

| 字段 | 说明 |
| --- | --- |
| id | 项目 ID |
| name | 项目名 |
| slug | 目录友好名称 |
| data_root | 数据根目录 |
| description | 说明 |
| created_at/updated_at | 时间 |

#### aois

项目 AOI。

| 字段 | 说明 |
| --- | --- |
| id | AOI ID |
| project_id | 项目 ID |
| name | AOI 名称 |
| source_type | `region/bbox/upload/drawn` |
| region_adcode | 可选行政区代码 |
| wkt | 查询 WKT |
| bbox | bbox |
| geometry_json | 几何 |
| simplification_tolerance | 简化参数 |

#### search_jobs

一次查询任务。

| 字段 | 说明 |
| --- | --- |
| id | 查询 ID |
| project_id | 项目 ID |
| aoi_id | AOI ID |
| start_time/end_time | 查询时间范围 |
| processing_level | 产品级别 |
| beam_mode | 波束 |
| flight_direction | 升降轨 |
| polarization | 极化 |
| relative_orbit | 相对轨道 |
| max_results | 最大结果 |
| status | `pending/running/succeeded/failed/canceled` |
| result_count | 结果数 |
| error_message | 错误 |
| created_at/finished_at | 时间 |

#### scenes

ASF 场景主表。

| 字段 | 说明 |
| --- | --- |
| scene_id | Sentinel-1 场景名 |
| platform | S1A/S1B/S1C/S1D |
| start_time/stop_time | 成像时间 |
| processing_level | 产品级别 |
| beam_mode | 波束 |
| flight_direction | 升降轨 |
| polarization | 极化 |
| relative_orbit | 相对轨道 |
| size_bytes | 文件大小 |
| download_url | ASF 下载 URL |
| geometry_json | 场景 footprint |
| properties_json | ASF 原始属性 |

#### job_scenes

查询任务和场景的关系。

| 字段 | 说明 |
| --- | --- |
| job_id | 查询 ID |
| scene_id | 场景 ID |
| selected | 用户是否选择下载 |
| product_status | 产品下载状态 |
| orbit_status | 轨道下载状态 |
| product_path | 本地产品路径 |
| orbit_path | 本地轨道路径 |

#### downloads

下载记录。

| 字段 | 说明 |
| --- | --- |
| id | 下载 ID |
| job_id | 任务 ID |
| scene_id | 场景 ID |
| kind | `product/orbit` |
| status | `queued/running/succeeded/failed/skipped/canceled` |
| url | 下载 URL |
| path | 本地路径 |
| bytes_total/bytes_done | 进度 |
| attempt_count | 尝试次数 |
| error_message | 错误 |
| started_at/finished_at | 时间 |

#### job_events

任务日志。

| 字段 | 说明 |
| --- | --- |
| id | 日志 ID |
| job_id | 任务 ID |
| level | `info/warning/error` |
| message | 日志内容 |
| created_at | 时间 |

## API 设计

### 行政区

```text
GET  /api/regions/tree
GET  /api/regions/search?q=牡丹江
GET  /api/regions/{adcode}
GET  /api/regions/{adcode}/geometry?simplified=true
POST /api/regions/reindex
```

### 项目和 AOI

```text
GET  /api/projects
POST /api/projects
GET  /api/projects/{id}
PATCH /api/projects/{id}
DELETE /api/projects/{id}

GET  /api/projects/{id}/aois
POST /api/projects/{id}/aois
```

### 查询

```text
POST /api/search-jobs
GET  /api/search-jobs/{id}
GET  /api/search-jobs/{id}/scenes
POST /api/search-jobs/{id}/select-scenes
```

### 下载

```text
POST /api/download-jobs
GET  /api/download-jobs/{id}
GET  /api/download-jobs/{id}/events
POST /api/download-jobs/{id}/pause
POST /api/download-jobs/{id}/resume
POST /api/download-jobs/{id}/cancel
POST /api/download-jobs/{id}/retry
POST /api/scenes/{scene_id}/download-orbit
```

### 系统状态

```text
GET /api/health
GET /api/settings
PUT /api/settings
GET /api/inventory/scan
```

## 前端页面设计

### 页面 1：首页 / 仪表盘

显示：

- 项目列表。
- 最近查询任务。
- 最近下载任务。
- 下载成功/失败数量。
- 数据目录占用。
- 凭据状态和 ASF 连通性。

### 页面 2：项目详情

显示：

- 项目信息。
- AOI 列表。
- 历史任务。
- 本地数据清单。
- 一键新建查询。

### 页面 3：新建查询

布局：

```text
左侧：区域选择和查询参数
右侧：地图
底部：查询按钮和参数摘要
```

区域选择：

- 省份下拉。
- 城市下拉。
- 搜索框：输入 `牡丹江` 可以直接定位。
- 上传 GeoJSON。
- bbox 输入。
- 地图绘制。

查询参数：

- 时间范围。
- 产品类型。
- 波束。
- 升降轨。
- 极化。
- 相对轨道。
- 最大结果数。

### 页面 4：查询结果

功能：

- 表格排序、筛选、勾选。
- 地图显示选中场景 footprint。
- 显示本地文件存在状态。
- 下载选中产品。
- 只下载轨道。
- 导出 manifest。

### 页面 5：下载任务

功能：

- 进度条。
- 当前下载文件。
- 产品状态。
- 轨道状态。
- 失败原因。
- 暂停/取消/重试。
- 打开本地目录。

### 页面 6：数据仓库

功能：

- 按项目、区域、时间、产品类型筛选本地数据。
- 查看每景产品和轨道是否匹配。
- 补下载缺失轨道。
- 删除任务记录但保留文件。
- 扫描外部已有数据入库。

## 文件和命名规范

项目目录：

```text
<data_root>\
  app.db
  app.log
  regions\
    regions_index_version.json
  projects\
    <project_slug>\
      project.json
      aois\
      jobs\
        <job_id>_<area_slug>_<date_range>\
          data\
          orbits\
          manifests\
          logs\
```

任务目录名示例：

```text
000001_mudanjiang_20240101_20240301_s1_slc
```

manifest：

- `manifest.csv`：给用户打开查看。
- `manifest.json`：完整机器可读版本。

## 状态机

查询任务：

```text
pending -> running -> succeeded
                   -> failed
                   -> canceled
```

下载任务：

```text
queued -> running -> succeeded
                 -> partial_failed
                 -> failed
                 -> paused
                 -> canceled
```

单文件下载：

```text
queued -> running -> succeeded
                 -> skipped
                 -> failed
                 -> canceled
```

产品和轨道状态分开记录。一个任务可以是：

```text
产品全部成功，轨道部分失败
```

这种情况应显示为 `partial_failed`，并允许单独补轨道。

## 关键工程决策

### 行政区边界处理

`全国行政区.geojson` 不作为运行时主数据源，而是导入源。导入后使用 SQLite 查询。

对于 ASF 查询，默认使用 `simplified_wkt`。原因：

- 原始边界可能很长。
- ASF 对复杂 WKT 查询更慢。
- Sentinel-1 景幅较大，过细边界通常没有必要。

简化参数建议：

- 默认 tolerance：`0.01` 度。
- 牡丹江市原始 WKT 约 10755 字符，`0.01` 简化后约 5694 字符。
- 用户可在高级设置中切换为原始边界或 bbox。

### 下载幂等

任何下载开始前先检查：

- 数据库中是否已有该 `scene_id`。
- 本地目标文件是否存在。
- 文件大小是否合理。
- 已有轨道是否覆盖该场景时间。

存在则标记 `skipped`，避免重复下载。

### 凭据

不把 Earthdata 密码明文写入 SQLite。

第一版：

- 支持环境变量。
- 支持页面临时输入。

第二版：

- 接入 `keyring`，在 Windows 上使用凭据管理器。

### 后台任务

本地单用户应用可以先用进程内任务队列：

- `asyncio.Queue` 或 `ThreadPoolExecutor`。
- 下载任务串行调度，单任务内部并发下载。
- 任务状态写 SQLite。

以后如果需要更强任务管理，再接入 RQ/Celery，但第一版不需要。

## 实现阶段

### 阶段 1：服务层重构

目标：把现有 CLI 逻辑拆成可复用 service。

任务：

- 新增 `services/asf_client.py`。
- 新增 `services/orbit_client.py`。
- 新增 `services/aoi.py`。
- CLI 改为调用 service。
- 保持现有 CLI 行为不变。
- 增加基础单元测试。

验收：

- `uv run s1-dl search` 仍可用。
- `uv run s1-dl download` 仍可用。
- `uv run s1-dl orbits` 仍可用。

### 阶段 2：行政区索引

目标：支持从 `全国行政区.geojson` 快速检索牡丹江等行政区。

任务：

- 新增 SQLite。
- 新增 `regions` 表。
- 新增导入命令：`s1-dl regions import 全国行政区.geojson`。
- 新增搜索命令：`s1-dl regions search 牡丹江`。
- 新增导出 AOI 命令：`s1-dl regions export 231000 --format wkt`。

验收：

- 能查到 `牡丹江市 adcode=231000`。
- 能用 `231000` 直接发起查询。

### 阶段 3：项目和任务数据库

目标：所有查询和下载有记录可追踪。

任务：

- 新增 `projects`、`aois`、`search_jobs`、`scenes`、`job_scenes`、`downloads`、`job_events`。
- 查询结果入库。
- 下载结果入库。
- 生成规范目录和 manifest。

验收：

- 查询牡丹江后，数据库可看到任务和场景。
- 下载后，数据库记录产品和轨道路径。

### 阶段 4：FastAPI 后端

目标：提供本地 Web API。

任务：

- 新增 `api/app.py`。
- 实现行政区、项目、查询、下载接口。
- 提供 Swagger 文档。
- 提供 `uv run s1-web` 启动命令。

验收：

- `http://127.0.0.1:8000/docs` 可访问。
- API 能返回牡丹江边界和查询结果。

### 阶段 5：前端 MVP

目标：页面完成主要流程。

任务：

- 项目列表。
- 行政区选择。
- 地图显示边界。
- 查询表单。
- 查询结果表格。
- 创建下载任务。
- 下载任务进度页。

验收：

- 用户能在页面选择 `黑龙江省 -> 牡丹江市`。
- 设置时间范围。
- 查询 Sentinel-1。
- 勾选场景并下载数据和轨道。

### 阶段 6：管理和增强

目标：长期可用。

任务：

- 文件仓库扫描。
- 缺失轨道补齐。
- 失败重试。
- 任务日志查看。
- keyring 凭据管理。
- 导出任务报告。
- 支持 Copernicus Data Space 作为备用数据源。

## 牡丹江市示例流程

1. 用户打开本地页面。
2. 进入项目 `牡丹江 Sentinel-1 数据`。
3. 选择行政区：

```text
黑龙江省 -> 牡丹江市
```

4. 设置：

```text
时间：2024-01-01 至 2024-03-01
产品：SLC
波束：IW
升降轨：不限
极化：不限
```

5. 点击查询。
6. 页面展示 ASF 返回的 Sentinel-1 场景。
7. 用户勾选需要的场景。
8. 点击下载。
9. 系统下载：

```text
data\S1A_....zip
orbits\S1A_OPER_AUX_POEORB_....EOF
manifest.csv
```

10. 下载任务页显示每景产品和轨道状态。
11. 如果某景轨道失败，用户点击“补轨道”。

## 风险和处理

### ASF 下载需要 Earthdata 账号

处理：页面启动时做凭据检查，查询可以不登录，下载时必须登录。

### 精密轨道可能有延迟

处理：允许暂时使用 `AUX_RESORB`，并提供后续补 `AUX_POEORB`。

### 行政区 GeoJSON 层级不完整

处理：用 `parent.adcode` 和内置省级 adcode 表补层级，不依赖文件里存在完整省级 Feature。

### 大范围长时间查询结果过多

处理：限制最大结果数，页面提醒分批查询；任务层支持按月份自动拆分。

### 文件重复和路径混乱

处理：以 `scene_id` 为唯一键，所有任务引用同一场景，文件仓库扫描可修复数据库状态。

## 后续扩展

- Sentinel-2 数据下载。
- Copernicus Data Space 数据源。
- 自动按月份/季度拆分任务。
- InSAR 处理链对接，例如 ISCE、SNAP、MintPy。
- 场景覆盖图层和轨道号统计。
- 下载完成后的数据质量检查。
