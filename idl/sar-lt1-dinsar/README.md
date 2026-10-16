# ENVI + IDL D-InSAR 批处理流水线

本仓库是一套基于 ENVI / IDL / SARscape 的 D-InSAR 自动化处理脚本，面向陆探一号等 SAR 数据的批量导入与差分干涉处理。代码包含两个主要阶段：

1. 批量导入原始数据，将 `*.meta.xml` 导入为 SARscape 可继续处理的产品。
2. 对已经完成导入的主辅影像执行完整 D-InSAR 流程，直到位移反演与地理编码输出。

仓库当前核心脚本只有 3 个：

- `Run_Batch_Task_Import.pro`：批量导入 `Task_*` 目录中的原始数据。
- `batch_dinsarworkflow_all.pro`：批量执行 D-InSAR 流程。
- `DinsarWorkflow_ALL.pro`：单景测试版 / 调试版完整流程。

## 1. 依赖环境

运行本项目需要以下软件环境已经正确安装并可在 IDL 中调用：

- ENVI
- IDL
- SARscape
- 对应 SARscape Batch 模块与 ENVI Task 环境

脚本中直接使用了以下对象 / 任务：

- `ENVI(/HEADLESS)`
- `SARscape_Batch_Init`
- `SARscapeBatch`
- `ENVITask('SARsImportLuTan1')`
- `IDLffShape`

因此该仓库不是纯 IDL 通用脚本，必须在装有 ENVI + SARscape 的环境中运行。

## 2. 仓库结构

```text
ENVI_IDL_DInSAR/
├─ Run_Batch_Task_Import.pro
├─ batch_dinsarworkflow_all.pro
├─ DinsarWorkflow_ALL.pro
└─ README.md
```

各脚本职责如下。

### 2.1 `Run_Batch_Task_Import.pro`

用途：批量扫描根目录下的 `Task_*` 文件夹，并分别处理其中的 `master` 与 `slave` 子目录。

处理逻辑：

- 在 `master` / `slave` 目录中查找 `*.meta.xml`
- 使用 `ENVITask('SARsImportLuTan1')` 执行导入
- 输出直接写回当前 `master` 或 `slave` 目录
- 如果目录中已经存在 `*.sml`，则认为该目录已导入，自动跳过

适合放在整个流程的第一步，用来把原始数据准备成后续 D-InSAR 可识别的输入。

### 2.2 `batch_dinsarworkflow_all.pro`

用途：批量执行完整 D-InSAR 流程。

处理逻辑：

- 扫描根目录下所有 `Task_*` 文件夹
- 检查每个任务目录下是否存在 `master` / `slave`
- 在 `master`、`slave` 中各取第一个 `*.sml`
- 去掉 `.sml` 后缀，得到 SARscape 输入基名
- 在任务目录内创建 `dinsar_results` 输出目录
- 调用 `Execute_Single_Dinsar_Workflow` 执行完整处理

这是生产使用时最重要的脚本。

### 2.3 `DinsarWorkflow_ALL.pro`

用途：单组主辅影像的完整 D-InSAR 处理脚本。

特点：

- 直接在脚本内手工指定 `master_base_file`、`slave_base_file`、`dem_base_file`
- 更适合单景调试、流程验证、参数试验
- 逻辑上与批处理版本一致，但不是批量入口

## 3. 建议的数据组织方式

根据代码，批处理脚本假定数据目录组织如下：

```text
<rootDir>/
├─ Task_20250504_20250601_1/
│  ├─ master/
│  │  ├─ *.meta.xml
│  │  ├─ ... 导入后生成的 *.sml、影像及配套文件
│  ├─ slave/
│  │  ├─ *.meta.xml
│  │  ├─ ... 导入后生成的 *.sml、影像及配套文件
│  └─ dinsar_results/
│     └─ workflow*
├─ Task_xxx/
└─ ...
```

处理顺序通常是：

1. 先运行 `Run_Batch_Task_Import.pro`
2. 确认每个 `master` / `slave` 目录中已经生成 `*.sml`
3. 再运行 `batch_dinsarworkflow_all.pro`

## 4. D-InSAR 主流程说明

`batch_dinsarworkflow_all.pro` 中的 `Execute_Single_Dinsar_Workflow` 实现了完整 6 步流程：

### Step 1. 干涉图生成

- 从主影像和辅影像的 `.sml` 中读取：
  - `PixelSpacingRg`
  - `PixelSpacingAz`
  - `IncidenceAngle`
- 根据目标地面分辨率自动计算多视数：
  - `RG_LOOKS_NBR`
  - `AZ_LOOKS_NBR`
- 调用 `InSARInterferogramGeneration`

### Step 2. 滤波与相干图生成

- 调用 `InSARFilterAndCoherence`
- 使用设定的滤波方法，例如 `GOLDSTEIN`
- 生成滤波干涉图与相干图

### Step 3. 轨道残余相位频率去除

- 调用 `InSARRemoveResidualPhaseFrequency`
- 输入为上一步生成的滤波干涉图和相干图

### Step 4. 相位解缠

- 调用 `InSARPhaseUnwrapping`
- 使用相干阈值 `UPHA_COH_THRESHOLD`

### Step 5. 精化与再平地

分为两步：

1. 自动 GCP 生成
2. Refinement and Reflattening

自动 GCP 生成的逻辑为：

- 打开相干图
- 按网格均匀划分影像
- 在每个网格中选取相干系数最大的像元
- 当该像元相干值高于阈值时，将其写入 shapefile
- 最终生成 `*_auto_gcp.shp`

随后调用 `InSARRefinementAndReflattening`，并将自动生成的 GCP 文件作为输入。

### Step 6. 相位转位移与地理编码

- 调用 `InSARPhaseToDisplacement`
- 使用最终解缠结果生成 LOS 位移产品
- 执行地理编码
- 当前脚本仅开启 LOS 输出：
  - `GENERATE_LOS_FLAG = OK`
  - `GENERATE_VERTICAL_FLAG = NotOK`
  - `GENERATE_MAX_SLOPE_FLAG = NotOK`

## 5. 关键输入参数

以下参数需要在脚本中按实际工程修改。

### 5.1 导入脚本参数

文件：`Run_Batch_Task_Import.pro`

- `temporary_directory`：SARscape 临时目录
- `rootDir`：待扫描的任务根目录
- `numToProcess`：最多处理多少个任务，`0` 表示全部处理

### 5.2 批处理 D-InSAR 参数

文件：`batch_dinsarworkflow_all.pro`

- `temporary_directory`：SARscape 临时目录
- `rootDir`：包含多个 `Task_*` 目录的根目录
- `dem_base_file`：DEM 基础文件路径
- `target_ground_resolution_m`：目标地面分辨率，控制自动多视
- `filter_method`：滤波方法，默认 `GOLDSTEIN`
- `unwrapping_coh_threshold`：解缠相干阈值
- `gcp_coh_threshold`：自动 GCP 相干阈值
- `gcp_number`：目标 GCP 数量
- `geocoding_coh_threshold`：地理编码时使用的相干阈值
- `geocoding_pixel_size_m`：地理编码输出像元大小
- `numToProcess`：最多处理多少个任务，`0` 表示全部处理

### 5.3 单景调试参数

文件：`DinsarWorkflow_ALL.pro`

- `master_base_file`
- `slave_base_file`
- `dem_base_file`
- `workflow_root_name`
- 其余处理参数与批处理版本基本一致

注意：`master_base_file` 和 `slave_base_file` 填写的是“基名”，不是 `.sml` 文件全名。脚本内部会自动拼接 `.sml` 去读取参数。

## 6. 输出结果说明

批处理脚本默认在每个任务目录下创建：

```text
Task_xxx/
└─ dinsar_results/
   ├─ workflow_dint
   ├─ workflow_reference_pwr
   ├─ workflow_secondary_pwr
   ├─ workflow_fint
   ├─ workflow_cc
   ├─ workflow_rrpf_fint
   ├─ workflow_upha
   ├─ workflow_auto_gcp.shp
   ├─ workflow_reflat_upha
   ├─ workflow_geo*
   └─ ...
```

其中常见关键中间结果包括：

- `*_dint`：初始干涉图
- `*_fint`：滤波后干涉图
- `*_cc`：相干图
- `*_upha`：解缠结果
- `*_auto_gcp.shp`：自动生成的 GCP 矢量文件
- `*_geo*`：地理编码后的位移产品

实际生成的附属文件数量和后缀会受 SARscape 版本及模块设置影响。

## 7. 典型使用方式

### 7.1 第一步：批量导入

在 `Run_Batch_Task_Import.pro` 中修改：

- `temporary_directory`
- `rootDir`
- `numToProcess`

然后在 IDL 命令行或脚本环境中运行：

```idl
.compile Run_Batch_Task_Import.pro
Run_Batch_Task_Import
```

### 7.2 第二步：批量执行 D-InSAR

在 `batch_dinsarworkflow_all.pro` 中修改：

- `temporary_directory`
- `rootDir`
- `dem_base_file`
- 各处理参数

然后运行：

```idl
.compile batch_dinsarworkflow_all.pro
Batch_DinsarWorkflow_ALL
```

### 7.3 单景测试

在 `DinsarWorkflow_ALL.pro` 中直接修改主影像、辅影像、DEM 和输出路径，然后运行：

```idl
.compile DinsarWorkflow_ALL.pro
DinsarWorkflow_ALL
```

## 8. 代码实现要点

### 8.1 自动读取 SML 参数

`Read_SML_Parameter` 会直接从 `.sml` 文件中读取指定 XML 标签内容，用于自动计算多视参数。这意味着：

- 输入数据必须已经正确导入并生成 `.sml`
- `.sml` 内部需要包含 `PixelSpacingRg`、`PixelSpacingAz`、`IncidenceAngle` 等字段

### 8.2 自动 GCP 生成策略

`CREATE_GCPS_FROM_COHERENCE` 不是随机取点，而是“规则网格 + 每格取最大相干值”的策略。这样做的优点是：

- GCP 空间分布更均匀
- 能避免点位过度集中
- 能通过相干阈值控制稳定区域

### 8.3 批处理脚本的选择策略

当前批处理版本在每个 `master` / `slave` 目录中只取“第一个找到的 `.sml`”作为输入，因此建议：

- 每个 `master` 目录内只保留一组待处理主影像
- 每个 `slave` 目录内只保留一组待处理辅影像
- 若目录中存在多份 `.sml`，需要先确认 `FILE_SEARCH` 返回顺序是否符合预期

## 9. 注意事项

1. 路径需要按本机环境手动修改，仓库中的路径示例均为作者本地路径。
2. 脚本默认使用 `ENVI(/HEADLESS)`，适合批处理环境。
3. `temporary_directory` 需要保证有足够磁盘空间。
4. `gcp_coh_threshold` 过高时，可能导致无法生成足够 GCP，流程会在 Step 5A 失败。
5. `unwrapping_coh_threshold`、`geocoding_coh_threshold` 需要结合研究区相干性调整。
6. 本仓库目前没有统一的日志输出、配置文件和异常恢复机制，失败后通常需要根据控制台信息排查。





