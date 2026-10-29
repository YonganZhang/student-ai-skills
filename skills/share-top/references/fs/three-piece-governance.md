# 三件套归档治理（research profile 专用）

## 目的

对"人工消费的最终产物"（论文主图、关键公式、引文快照等）建立**单一真相源**，保证"现役版在哪"永远有明确答案。

## 骨架

每个启用三件套的资产目录（如 `paper/figures/`）布局：

```
paper/figures/
├── current/                    软链指向 archive/ 现役版（真身不在这里）
│   ├── Fig1_global_map.png -> ../archive/2026-04-13_Fig1_global_map_v3.png
│   └── ...
├── archive/                    所有历史版本，时间戳+版本号
│   ├── 2026-04-10_Fig1_global_map_v1.png
│   ├── 2026-04-12_Fig1_global_map_v2.png
│   └── 2026-04-13_Fig1_global_map_v3.png
├── _scratch/                   一次性探索，随时可清
│   └── 调色尝试_废.png
└── LEDGER.md                   单一登记表 + 反链 wiki
```

## 三条硬规则

### R1 — archive 命名强制格式

`YYYY-MM-DD_<名>_v<N>.<ext>`

**禁止**：
- 裸名（`Fig1.png` 不带日期）
- 用下划线空格混用（`Fig 1_v3.png`）
- 用中文"最终版""final2"等无序号标记

**允许**：
- `2026-04-13_Fig1_global_map_v3.png`
- `2026-04-13_Fig1_global_map_v3_highres.png`（加后缀表示变体）

### R2 — current/ 只放软链

current/ 里**禁止**放真身文件。软链必须指向 `archive/` 下某一版。
这样保证："真身 = archive 里的某版" 是唯一真相，current/ 只是"当前选定哪版"的指针。

Windows 兼容性差时，可以降级用副本+hash校验（见 `scripts/lint-fs.py --fix` 的副本模式）。

### R3 — _scratch/ 不进 git / 不进 LEDGER

探索性产物放 `_scratch/`，任何时候都可以 `rm -rf _scratch/*` 而不需要迁移。

## LEDGER.md 条目模板

每个 current/ 软链对应 LEDGER 一条：

```markdown
- `Fig1_global_map.png` → `archive/2026-04-13_Fig1_global_map_v3.png`
  - 脚本：`src/analysis/plot_fig1.py`
  - 方法论：[[wiki/figures/choropleth]]
  - 数据源：[[wiki/data/reservoir-merged]]
  - 最后更新：2026-04-13
  - 变更记录：v3 改用 PlateCarree 投影（来自 reviewer 建议）
```

**必选字段**：文件名、archive 软链目标、方法论 wiki 反链。其他字段可选。

## 画图特化:中间版本不要丢

绘图任务一图常画 5-10 版,默认走 `_scratch/` 暂存,**确认满意才 promote 到 archive**:

```python
# 画图脚本统一输出到 _scratch/,文件名带时间戳避免覆盖
out = f"_scratch/{Path(__file__).stem}_{datetime.now():%Y%m%d_%H%M%S}.png"
plt.savefig(out)
```

用户确认 vN 后,一行 promote:
```bash
mv _scratch/<temp>.png archive/$(date +%F)_<名>_v<N+1>.png
ln -sf ../archive/$(date +%F)_<名>_v<N+1>.png current/<名>.png
```

**好处**:中间版本全留 `_scratch/`,任何时候 `ls _scratch/` 一眼看历史;promote 才进 archive (单一真相源不被噪音污染)。`_scratch/` 进 .gitignore,但用户本地能查回去。

## 升级工作流

修改一张图时：

1. 新版存为 `_scratch/<临时名>.png`
2. 确认满意 → `mv _scratch/... archive/YYYY-MM-DD_<名>_v<N+1>.ext`
3. 更新软链：`ln -sf archive/YYYY-MM-DD_<名>_v<N+1>.ext current/<名>.ext`
4. 更新 LEDGER 对应条目（日期 + 变更记录一行）
5. 老版本留在 archive 不删

## 废弃工作流

一张图不再用：

1. LEDGER 条目移到文件末尾 "## 已废弃" 段
2. 删 current/ 软链（真身留在 archive/ 作历史）
3. 不要 `rm archive/ 下的真身`

整个目录废弃 → 见 `legacy-migration.md`。
