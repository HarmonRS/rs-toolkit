# rs-toolkit

遥感（SAR/InSAR）常用小工具与脚本合集。规范见 [CONVENTIONS.md](CONVENTIONS.md)。

| 工具 | 语言 | 说明 | 原仓库 |
|---|---|---|---|
| [idl/sar-lt1-dinsar](idl/sar-lt1-dinsar) | IDL | 陆探1号 ENVI/SARscape D-InSAR 批处理流水线 | lutan1-envi-idl-dinsar-pipeline |
| [python/sar-gf3-l1a2l2](python/sar-gf3-l1a2l2) | Python | 高分3号 L1A → L2 处理流水线（含 SARscape Go 封装） | GF3_L1A_To_L2_pipeline |
| [python/s1-orbit-downloader](python/s1-orbit-downloader) | Python | Sentinel-1 影像与精密轨道查询下载（CLI + Web UI） | sentinel-orbit-downloader |

## 安装 Python 工具

```bash
pip install "git+https://git.rsharmon.cn/Harmon/rs-toolkit.git#subdirectory=python/sar-gf3-l1a2l2"
pip install "git+https://git.rsharmon.cn/Harmon/rs-toolkit.git#subdirectory=python/s1-orbit-downloader"
```

IDL 工具直接在 ENVI/IDL 中打开对应目录下的 `.pro`，用法见各目录 README。

各工具的提交历史均已保留（`git log -- <目录>`）。
