# 废弃目录迁移

## 何时需要迁移到 _legacy/

- 某个资产目录（如早期 `paper/main_subplots/`）被新目录（`paper/figures/`）取代
- 旧版实现（如 `src/old_pipeline/`）被新版替代但想保留参考
- 整个子项目阶段性结束（`exploration-phase1/`）

## 迁移三步

```bash
# 1. 整个目录 mv 到 _legacy/，带描述性新名
mv paper/main_subplots _legacy/paper-figures-pre-governance-20260419/

# 2. 写一行 README 说明为什么废弃、被谁取代
cat > _legacy/paper-figures-pre-governance-20260419/README.md <<EOF
# Pre-governance paper figures archive (2026-04-19)

废弃原因：三件套架构上线前的散乱图目录。
被取代：paper/figures/{current,archive,_scratch}/
保留原因：历史版本追溯、reviewer 可能问"某图最初版"。
EOF

# 3. 如项目保留 legacy directory-map，更新对应记录；v4 新项目通常只需 README
```

## 硬规则

- **禁止**原地搁置废弃目录。看到旧目录 = 立即决定 "留 (mv _legacy/) 或 删"
- **禁止**只改目录名不 mv（例如 `paper/figures_old/`）。要么进 `_legacy/`，要么彻底删
- `_legacy/` 目录本身**不进三件套**，不需要 current/archive/

## _legacy/ 目录布局

```
_legacy/
├── README.md                           总说明：_legacy/ 是废弃目录仓库，不活跃
├── paper-figures-pre-governance-20260419/
│   ├── README.md                       单个迁移的说明（为什么废弃）
│   └── <原有文件保留>
└── old-pipeline-v1/
    ├── README.md
    └── ...
```

## 保质期

_legacy/ 里的东西默认**永久保留**（成本低，可能救命）。
只有当某个归档长期无人访问、且确实占用了紧张的磁盘余量时，才评估压缩外置（`.tar.gz` 入对象存储 / 网盘）；
判断依据是磁盘压力、恢复需求和是否仍有冻结引用，外置后在原位留 README 写明位置与恢复方式。
