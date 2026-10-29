---
name: zarr (archived under share-autoresearch-engine)
description: "Zarr 分块 N 维数组存储：ERA5/CMIP6/遥感大栅格的 cloud-native 读写、压缩、Dask/Xarray 并行。触发：zarr、chunk、大栅格、S3 数组。"
license: MIT license
tags: [sci, storage, climate, array]
metadata:
  skill-author: K-Dense Inc.
  upstream: https://github.com/K-Dense-AI/scientific-agent-skills
---

# Zarr 大数组存储

## 定位

Zarr 用于存储超大 N 维数组：分块（chunking）+ 压缩 + 并行 I/O，可直接挂 S3 / GCS。气候、遥感、显微成像首选后端。

## 用户常见场景

- ERA5 / CMIP6 气候再分析 / 模式数据落盘（GB ~ TB 级）
- FPV 辐照时空序列按 tile 查询
- 与 xarray 配合做多维气候分析
- 中间特征 cache（Dask 并行训练管线）

## 安装

```bash
uv pip install zarr xarray dask
# 可选：pip install s3fs gcsfs  # 云端
```

## 核心概念（30 秒）

| 概念 | 要点 |
|---|---|
| chunk | 默认 ~1MB/块；按访问模式对齐（按时间切 vs 按经纬度切） |
| 压缩 | 默认 Blosc+Zstd；科学浮点推荐 Blosc-LZ4 或 Zstd level=3 |
| group | 分层命名空间，类似 HDF5 group，可存多变量 |
| consolidated metadata | 云端访问前 `zarr.consolidate_metadata(store)` 大幅加速 |
| sharding (v3) | 大规模下把多个 chunk 打包成 shard，减少文件数量 |

## 最小模板

```python
import zarr, numpy as np
z = zarr.create(shape=(1000, 1000), chunks=(100, 100), dtype='f4')
z[:] = np.random.randn(1000, 1000)
# 读取
z2 = zarr.open('array.zarr', mode='r')
```

## 路由

| 想知道 | 读 |
|---|---|
| 完整 API（array/group/open/resize/append/compression/sharding/consolidate） | `references/api_reference.md` |

## 与其他 skill 关系

- 时序预测前取子集 → `share-autoresearch-engine/references/timesfm`
- 空间矢量叠加 → `share-sci-plot/references/geopandas`（可选，本包未包含）（用 xarray→rasterio→gpd 桥接）
- 气候统计 → `share-sci-write/tools/statistical-analysis`（可选，本包未包含）

## 环境注意

- 内存决定 chunk 上限：笔记本 16GB → chunk ≤ 2GB；1TB 内存服务器 → chunk 可 ~32GB；都要留余量避免 Dask worker OOM
- 路径：Windows 用正斜杠 `zarr.open("E:/data/x.zarr")`，Linux 用 `~/data/x.zarr` 或 `pathlib.Path`
- 小数据（<100MB）直接用 numpy / netCDF，不必上 Zarr
