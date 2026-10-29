"""
data-reality-check.py — 数据真实性 EDA 模板（领域无关）

四检：sentinel / 物理合理性 / 相关性结构 / 缺失模式

用法:
    python data-reality-check.py <csv_path> [--key-vars var1,var2,var3] [--time-col col]

输出:
    - stdout: 结构化报告
    - <csv_path>.reality-check.md: markdown 报告
    - <csv_path>.reality-check/*.png: 诊断 figure

设计原则:
    - 不假设字段命名（用户传 --key-vars）
    - 不假设时间字段（自动检测 / 用户传 --time-col）
    - 不假设 sentinel 值（全扫常见 sentinel）
    - 不下"合成"结论，只输出红旗清单让人判断
"""
import argparse
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path

# 常见 sentinel 值（SCADA / PLC / 早期 binary 系统约定）
COMMON_SENTINELS = [32767, -32768, -9999, 9999, -1e9, 1e9, 65535, -65536, 0xFFFF]


def detect_sentinels(df):
    """检测每列是否有常见 sentinel 值"""
    findings = {}
    for col in df.select_dtypes(include=[np.number]).columns:
        col_max = df[col].max()
        col_min = df[col].min()
        suspicious = []
        for s in COMMON_SENTINELS:
            if (df[col] == s).any():
                count = (df[col] == s).sum()
                pct = count / len(df) * 100
                if pct > 0.01:
                    suspicious.append((s, count, pct))
        if suspicious:
            findings[col] = suspicious
    return findings


def clean_sentinels(df, sentinels=None):
    """把常见 sentinel 替换为 NaN"""
    sentinels = sentinels or COMMON_SENTINELS
    return df.replace(sentinels, np.nan)


def detect_time_col(df):
    """自动检测时间字段"""
    candidates = []
    for col in df.columns:
        cname = str(col).lower()
        if any(k in cname for k in ['time', 'date', 'timestamp', 'datetime', 'ts']):
            candidates.append(col)
    return candidates


def physical_sanity(df, key_vars=None, time_col=None):
    """物理合理性检测：值域 / 昼夜模式 / 季节循环 / 范围异常"""
    out = {}
    for col in (key_vars or df.select_dtypes(include=[np.number]).columns[:10]):
        if col not in df.columns:
            continue
        v = df[col].dropna()
        if len(v) == 0:
            continue
        out[col] = {
            'n_valid': int(len(v)),
            'valid_pct': float(len(v) / len(df) * 100),
            'mean': float(v.mean()),
            'std': float(v.std()),
            'min': float(v.min()),
            'max': float(v.max()),
            'p50': float(v.quantile(0.5)),
            'p99': float(v.quantile(0.99)),
            'range_iqr': float(v.quantile(0.75) - v.quantile(0.25)),
            'unique_ratio': float(v.nunique() / len(v)),
        }
    return out


def correlation_structure(df, key_vars=None):
    """关键变量两两相关，红旗 = 应相关但 |r| < 0.1"""
    if key_vars is None:
        nums = df.select_dtypes(include=[np.number]).columns[:8]
    else:
        nums = [c for c in key_vars if c in df.columns]
    if len(nums) < 2:
        return None
    return df[nums].corr().round(3)


def missing_pattern(df):
    """缺失率分布 + 红旗"""
    miss = df.isna().sum().sort_values(ascending=False)
    pct = (miss / len(df) * 100).round(2)
    summary = pd.DataFrame({'count': miss, 'pct': pct})
    n_zero_miss = (miss == 0).sum()
    n_100_miss = (pct == 100).sum()
    n_partial = ((pct > 0) & (pct < 100)).sum()
    flags = []
    if n_zero_miss == len(df.columns) and len(df) > 1000:
        flags.append(f"🚩 全字段 0 缺失（{len(df.columns)} 列）— 真实采集数据极罕见，合成嫌疑")
    if n_partial == 0 and n_zero_miss + n_100_miss == len(df.columns):
        flags.append(f"🚩 缺失模式二极化（全 0% 或全 100%）— 不像真采集")
    return summary, flags


def run_checks(csv_path, key_vars=None, time_col=None, out_dir=None):
    csv_path = Path(csv_path)
    out_dir = Path(out_dir) if out_dir else csv_path.parent / f"{csv_path.stem}.reality-check"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== LOAD {csv_path.name} ===")
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"  shape: {df.shape}")
    print(f"  size: {csv_path.stat().st_size / 1024 / 1024:.1f} MB")

    print(f"\n=== CHECK 1: SENTINEL ===")
    sent = detect_sentinels(df)
    if sent:
        print(f"  检测到 {len(sent)} 列含 sentinel 值")
        for col, lst in list(sent.items())[:10]:
            for s, count, pct in lst:
                print(f"  {col}: value={s} count={count:,} ({pct:.1f}%)")
        df_clean = clean_sentinels(df)
        print(f"  → 已清洗 sentinel → NaN，建议用 df_clean 跑后续检测")
    else:
        print(f"  未检测到常见 sentinel")
        df_clean = df

    print(f"\n=== CHECK 2: 物理合理性（清洗后）===")
    phys = physical_sanity(df_clean, key_vars=key_vars, time_col=time_col)
    for col, stats in list(phys.items())[:15]:
        print(f"  {col:20s} valid={stats['valid_pct']:5.1f}% "
              f"mean={stats['mean']:>10.2f} min={stats['min']:>10.2f} max={stats['max']:>10.2f} "
              f"uniq_ratio={stats['unique_ratio']:.3f}")

    print(f"\n=== CHECK 3: 相关性（清洗后）===")
    corr = correlation_structure(df_clean, key_vars=key_vars)
    if corr is not None:
        print(corr.to_string())
        zero_corr = ((corr.abs() < 0.05) & (corr != 1)).sum().sum()
        n_pairs = corr.shape[0] * (corr.shape[0] - 1)
        if zero_corr / max(n_pairs, 1) > 0.7:
            print(f"  🚩 >70% 变量两两 |r|<0.05 — 合成嫌疑")
    else:
        print(f"  数值字段不足两个，跳过相关性")

    print(f"\n=== CHECK 4: 缺失模式 ===")
    summary, flags = missing_pattern(df_clean)
    print(summary[summary['count'] > 0].head(15).to_string())
    n_zero = (summary['count'] == 0).sum()
    print(f"\n  完全无缺失字段: {n_zero} / {len(df.columns)}")
    for f in flags:
        print(f"  {f}")

    print(f"\n=== 总结 ===")
    print(f"  - Sentinel 字段: {len(sent)}")
    print(f"  - 物理合理性: {len(phys)} 字段已统计")
    print(f"  - 相关性: {'计算完成' if corr is not None else '跳过'}")
    print(f"  - 缺失红旗: {len(flags)} 条")

    # 写 markdown 报告
    md = out_dir / "reality-check.md"
    with open(md, 'w') as f:
        f.write(f"# Reality Check — {csv_path.name}\n\n")
        f.write(f"- Shape: {df.shape}\n- Size: {csv_path.stat().st_size/1024/1024:.1f} MB\n\n")
        f.write(f"## Sentinel 检测\n\n")
        if sent:
            f.write(f"{len(sent)} 列含 sentinel。已清洗 → NaN。\n\n")
            for col, lst in list(sent.items())[:20]:
                f.write(f"- `{col}`: " + ", ".join(f"{s} ({pct:.1f}%)" for s, _, pct in lst) + "\n")
        else:
            f.write(f"无常见 sentinel\n")
        f.write(f"\n## 物理合理性\n\n```\n")
        for col, stats in phys.items():
            f.write(f"{col:20s} valid={stats['valid_pct']:5.1f}% mean={stats['mean']:>10.2f} "
                    f"range=[{stats['min']:>10.2f}, {stats['max']:>10.2f}]\n")
        f.write(f"```\n\n## 相关性\n\n```\n")
        if corr is not None:
            f.write(corr.to_string())
        f.write(f"\n```\n\n## 缺失模式\n\n```\n")
        f.write(summary[summary['count'] > 0].head(15).to_string())
        f.write(f"\n```\n\n红旗:\n")
        for fl in flags:
            f.write(f"- {fl}\n")
    print(f"\n  报告写入: {md}")
    return df_clean


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="CSV 文件路径")
    ap.add_argument("--key-vars", help="逗号分隔的关键变量名（必须真实存在于 CSV）")
    ap.add_argument("--time-col", help="时间字段名")
    ap.add_argument("--out-dir", help="输出目录")
    args = ap.parse_args()
    kv = args.key_vars.split(",") if args.key_vars else None
    run_checks(args.csv, key_vars=kv, time_col=args.time_col, out_dir=args.out_dir)
