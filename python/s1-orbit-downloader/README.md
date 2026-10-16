# Sentinel Orbit Downloader

一个本地可用的 Sentinel-1 数据与精密轨道下载工具，支持：

- 按行政区和时间范围检索 Sentinel-1
- 下载原始 Sentinel-1 产品
- 下载匹配的精密轨道/恢复轨道 `.EOF`
- 用 SQLite 管理项目、任务、场景和下载记录
- 通过本地 Web 页面完成日常操作

当前项目面向 Windows 本机使用场景，已经包含一键启动脚本。

## 当前能力

已实现：

- 行政区 GeoJSON 导入 SQLite
- 按行政区检索 Sentinel-1 场景
- 原始 Sentinel-1 产品下载
- 精密轨道 `.EOF` 下载
- 项目管理
- 任务列表、任务详情、事件日志
- 任务删除与清空
- Earthdata 凭据本地保存

暂未实现：

- GeoTIFF / `.tif` 处理与导出
- 后处理流水线

也就是说，现在项目专注于“检索 + 下载原始数据 + 下载轨道”。

## 目录

- 项目根目录：`C:\Users\16216\Desktop\Code\sentinel-orbit-downloader`
- 默认数据库：`.s1dl\app.db`
- 默认本地数据目录：`.local-data\`
- 行政区源文件：`全国行政区.geojson`

## 环境要求

- Windows
- Python 3.11 - 3.13
- `uv`
- 网络可访问 ASF / Earthdata

## 快速开始

### 1. 一键启动

直接双击：

- `Start-SentinelUI.cmd`

它会自动：

1. 检查 `uv`
2. 执行 `uv sync`
3. 启动本地服务
4. 打开浏览器

停止服务时双击：

- `Stop-SentinelUI.cmd`

启动脚本优先尝试这些端口：

- `8011`
- `8010`
- `8012`
- `8013`
- `8014`

如果端口已被占用，会自动换到下一个可用端口。

### 2. 手动启动

```powershell
cd C:\Users\16216\Desktop\Code\sentinel-orbit-downloader
uv sync
$env:S1DL_API_PORT="8011"
uv run s1-web
```

打开页面：

```text
http://127.0.0.1:8011/
```

Swagger 文档：

```text
http://127.0.0.1:8011/docs
```

## 首次使用流程

### 1. 导入行政区

项目根目录下已经放了：

- `全国行政区.geojson`

在页面中点击：

- `导入行政区`

也可以用命令行：

```powershell
uv run s1-dl regions import
```

### 2. 创建项目

建议先建一个本地项目，例如：

- 项目名称：`牡丹江 Sentinel-1 数据`
- 数据根目录：`.local-data\mudanjiang`

### 3. 配置 Earthdata

下载原始 Sentinel-1 产品必须有 NASA Earthdata 账号。

页面中可填写：

- `Earthdata 用户名`
- `Earthdata 密码`

然后点击：

- `保存凭据`

保存后：

- 用户名和密码会写入本地 SQLite
- 密码不是明文保存
- 密码使用当前 Windows 用户的 DPAPI 加密

如果不想保存，也可以每次手填。

### 4. Earthdata 首次授权 ASF

很多第一次下载失败，不是用户名密码错，而是没有授权 ASF 应用访问 Earthdata。

如果任务日志出现类似错误：

```text
Pre authorization required for this application
```

请先在浏览器登录 Earthdata，然后打开下面链接完成授权：

```text
https://urs.earthdata.nasa.gov/approve_app?client_id=BO_n7nTIlMljdvU6kRRB3g
```

这是一次性的关键步骤。

### 5. 检索并下载

页面典型流程：

1. 搜索行政区，例如 `牡丹江`
2. 选择时间范围
3. 选择产品级别，如 `SLC`
4. 点击 `发起检索`
5. 选中任务
6. 选择下载参数
7. 点击 `启动下载`

如果只想补精密轨道，不下载原始产品：

- 把 `跳过产品` 设为 `是`

## 页面功能说明

### 环境配置

- 导入行政区 GeoJSON
- 查看服务状态

### 项目

- 创建项目
- 刷新项目列表

### 行政区选择

- 按名称或 `adcode` 搜索
- 查看行政区范围框和中心点

### 检索参数

支持：

- 开始日期 / 结束日期
- 产品级别
- 波束模式
- 轨道方向
- 极化
- 相对轨道号
- 最大结果数
- 使用原始行政区边界

### 下载参数

支持：

- 数据目录
- 轨道目录
- 跳过产品
- 跳过轨道
- 并发数
- 忽略轨道失败
- Earthdata 凭据保存 / 清除

### 任务区

支持：

- 刷新任务
- 刷新详情
- 删除选中任务
- 清空当前项目的非运行任务

## 输出结构

典型输出目录如下：

```text
.local-data\mudanjiang\
  data\        # Sentinel-1 原始产品
  orbits\      # AUX_POEORB / AUX_RESORB EOF 文件
  manifest.csv
```

数据库中还会保存：

- 项目信息
- 搜索任务
- 场景清单
- 下载记录
- 任务事件日志

## 命令行用法

### 同步环境

```powershell
uv sync
```

### 导入行政区

```powershell
uv run s1-dl regions import
```

### 搜索行政区

```powershell
uv run s1-dl regions search 牡丹江
```

### 创建项目

```powershell
uv run s1-dl projects create `
  --name "牡丹江 Sentinel-1 数据" `
  --data-root ".local-data\mudanjiang" `
  --description "Mudanjiang Sentinel-1 scenes and orbits"
```

### 按行政区检索

牡丹江市 `adcode`：

- `231000`

```powershell
uv run s1-dl search `
  --project-id 1 `
  --region-adcode 231000 `
  --start 2024-01-01 `
  --end 2024-03-01 `
  --processing-level SLC `
  --max-results 20 `
  --manifest ".local-data\mudanjiang\manifest.csv"
```

### 直接下载

```powershell
uv run s1-dl download `
  --project-id 1 `
  --region-adcode 231000 `
  --start 2024-01-01 `
  --end 2024-03-01 `
  --processing-level SLC `
  --out ".local-data\mudanjiang-run" `
  --processes 2
```

### 只补轨道

```powershell
uv run s1-dl orbits `
  --data-dir ".local-data\mudanjiang\data" `
  --out ".local-data\mudanjiang\orbits"
```

## 常见问题

### 1. 页面里任务全是 failed

先看任务事件日志。

常见原因有两个：

#### 原因 A：没填 Earthdata 用户名和密码

如果下载原始 Sentinel-1 产品，必须提供 Earthdata 凭据。

解决：

- 页面填写用户名密码
- 或保存到本地配置
- 或设置环境变量 `EARTHDATA_USER` / `EARTHDATA_PASS`

#### 原因 B：Earthdata 没授权 ASF

如果日志里有：

```text
Pre authorization required for this application
```

按前文的授权链接先批准 ASF 应用。

### 2. 为什么检索成功，但下载失败

因为检索 ASF 元数据不一定要求完整的下载授权；真正下载原始产品时才会触发 Earthdata 登录和授权校验。

### 3. 只想下载轨道，不想下载原始产品

页面里把：

- `跳过产品`

设成：

- `是`

### 4. 保存 Earthdata 凭据是否明文

不是。

当前实现：

- 用户名保存在本地 SQLite
- 密码经过 Windows DPAPI 加密后保存

### 5. 为什么不支持 `.tif`

当前项目只管原始 Sentinel-1 产品和轨道文件。

还没有做：

- 解压
- 预处理
- GeoTIFF 导出

## 开发与维护

### 主要入口

- Web API: `src/sentinel_orbit_downloader/api/app.py`
- Web 页面: `src/sentinel_orbit_downloader/web/`
- 下载管理: `src/sentinel_orbit_downloader/services/download_manager.py`
- 项目/任务存储: `src/sentinel_orbit_downloader/services/project_store.py`
- Earthdata 本地设置: `src/sentinel_orbit_downloader/services/settings_store.py`

### 本地脚本

- `Start-SentinelUI.cmd`
- `Start-SentinelUI.ps1`
- `Stop-SentinelUI.cmd`
- `Stop-SentinelUI.ps1`

## 说明

这个项目当前阶段的目标很明确：

- 把“按区域检索 Sentinel-1”
- “下载原始数据”
- “下载精密轨道”
- “管理任务记录”

这四件事先稳定做好。
