# 沙盒先行规范

## 何时触发
- 任何**主 pipeline 改动**（loader / model / evaluator / split）
- 实验性方法（新架构 / 新特征 / 新损失）
- 用户怀疑或质疑当前做法

## 沙盒目录约定

```
项目根/
├── code/                       # 主 pipeline（不随便动）
├── data/frozen_splits/         # v1 splits（生产用）
├── data/frozen_splits_v2/      # ← 新方案沙盒（与 v1 并存）
└── _sandbox/                   # ← 沙盒实验目录（全局 artifact-lifecycle 约定；项目已有自己的沙盒目录名时沿用项目的）
    ├── exp_<round>_<topic>/    # 每个实验独立目录
    │   ├── README.md           # 实验背景 + 入口命令
    │   ├── run.py              # 实测代码
    │   ├── results.json        # 数字证据
    │   └── *.parquet           # 中间产物
    └── ...
```

## 沙盒 → 主 pipeline 升级 5 步

1. 沙盒跑通有数字（apple-to-apple vs 现 baseline）
2. 跨多 metric / horizon / dataset 验证一致性
3. 写 README 记入口 + 已知 caveat
4. 跑 leakage checklist 7 类
5. 用户拍板 → 才合到主 pipeline

## 沙盒命名

`exp_<round_id>_<topic>/`
- `<round_id>`: r10 / r11 / p10 等
- `<topic>`: 简短描述如 arch_ablation / skippd_image / guowang_8sites

## 反模式

🔴 直接改主 pipeline 看效果 → 不可逆 / 与 v1 难比较
🔴 沙盒里自己跑通就喊"验证完成"，没 leakage check
🔴 用户 review 不及格直接合并

## 实战例（多站光伏预测项目 P10）

- 沙盒 1: `exp_p10_guowang_8sites/` → 8 站独立 LGB → +0.103
- 沙盒 2: `exp_r11_skippd_image/` → ResNet50 + LGB → +0.011
- v2 split: `data/frozen_splits_v2/guowang_8stations/` 与 v1 并存
- 主 pipeline `code/` 完全没动 → 用户随时可对比 v1 vs v2
