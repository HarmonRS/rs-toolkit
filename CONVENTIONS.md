# Harmon 代码协定

适用于 git.rsharmon.cn/Harmon 下的所有仓库（GitHub HarmonRS 为镜像）。新代码必须遵守，旧代码在修改时逐步对齐。

## 1. 仓库命名
- 全小写，短横线连接：`领域-数据源-功能`，如 `sar-lt1-dinsar`、`sar-gf3-l1a2l2`、`s1-orbit-downloader`。
- 常用前缀：`sar`（雷达通用）、`lt1`（陆探1号）、`gf3`（高分3号）、`s1`（Sentinel-1）、`opt`（光学）。
- 禁止下划线、大写、`-v2`/`-new`/`-final` 之类的版本后缀（版本靠 tag）。
- 主力项目（系统/服务）独立成仓库；小工具、脚本统一放进 `rs-toolkit`。

## 2. rs-toolkit 目录结构
```
rs-toolkit/
  idl/<工具名>/       # IDL/ENVI 脚本
  python/<工具名>/    # 每个工具是独立的 Python 包
  go/<工具名>/        # 如有
  README.md           # 工具索引：一行说明 + 安装/运行方式
  CONVENTIONS.md
```
- 工具目录名同样遵守第 1 条命名规则。
- 工具之间不互相 import；共用代码再考虑抽成 `python/rs-common/`。
- 新增工具时同步更新根 README 索引。

## 3. 分支与提交
- 默认分支 `main`，始终保持可用；功能在 `feat/xxx`、`fix/xxx` 分支上开发，通过 PR 合并。
- 提交信息采用 Conventional Commits：`<type>(<scope>): <说明>`
  - type：`feat` `fix` `refactor` `docs` `test` `chore` `perf`
  - scope：rs-toolkit 中写工具名，如 `fix(sar-gf3-l1a2l2): 跳过损坏的压缩包`
- 一个提交只做一件事；不提交生成物、数据、密钥。
- 发布打 tag：主项目 `vX.Y.Z`；toolkit 内工具 `<工具名>-vX.Y.Z`。

## 4. Python
- 一律 `pyproject.toml` + `src/` 布局：`src/<包名>/`，包名为目录名的下划线形式。
- 声明 `requires-python`、依赖下限，命令行入口写在 `[project.scripts]`。
- 安装方式（无需拷脚本）：
  `pip install "git+https://git.rsharmon.cn/Harmon/rs-toolkit.git#subdirectory=python/<工具名>"`
- 代码用 `ruff` 检查与格式化；测试放 `tests/`，用 `pytest`。
- 路径、账号等配置不写死在代码里，走命令行参数/配置文件/环境变量。

## 5. IDL / ENVI
- 文件名小写下划线（IDL 惯例），一个 `.pro` 一个主过程，过程名与文件名一致。
- 文件头注释写明：用途、输入输出、依赖的 ENVI/SARscape 版本、作者与日期。
- 输入输出路径作为参数传入，不写死；批处理入口统一命名 `batch_*.pro`。
- `.sav` 等编译产物如必须入库，标记为 binary（.gitattributes）。

## 6. README 要求
每个仓库/工具目录必须有 README，至少包含：
1. 一句话说明做什么；2. 环境与依赖；3. 安装；4. 最小运行示例；5. 输入/输出说明；6. 已知限制。

## 7. 其他
- 文本统一 UTF-8、LF（Windows `.cmd/.bat` 除外）。
- 大于 10MB 的二进制/数据不入库，放 release 或 NAS。
