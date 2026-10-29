# 六合一升级阶梯(版本判定 + 逐级 delta 清单 + 扩展协议)

> 用户在任何对话说"**把六合一升级到最新**"→ 走本文件:① 判定当前版本 ② 沿阶梯逐级跑 delta 清单 ③ doctor 验收。
> 每级清单**幂等可重跑**;只补缺口不搬家。

## ① 当前版本怎么知道(派生,不手写)

**版本 = 盘上特征,不是手写戳**(手写戳必漂移)。权威探测 = `topic-brief.py` 的 `detect_sixone_version()`;
每次 brief(`sixone-cli.py brief`)都报 `standard: 六合一 <版本>` —— AI 不用问,握手时自动知道。

| 版本 | 盘上特征(探测依据) |
|---|---|
| `none` | 无任何 TOP 计划文件 |
| `pre-v4` | 只有旧布局(TOP.md / 五合一 / 旧 wiki-methodology/) |
| `v4` | 有 `_wiki-methodology/_top/_task_plan.md`(v4 骨架) |
| `v4.5-partial` | v4 + 只有 `_codebook/` 节点**或**只有 `_tests/_gates.yml`(升级做了一半) |
| `v4.5` | v4 + `_codebook/` 有节点 **且** `_wiki-methodology/_tests/_gates.yml` 存在 |

## ② 升级阶梯(逐级走,不跳级)

| 从 → 到 | 清单 | 性质 |
|---|---|---|
| `none` → `v4` | [share-top-upgrade-old](../sub-skills/share-top-upgrade-old/REFERENCE.md) 或新项目直接按 v4 模板 init | 大迁移(需用户确认搬家) |
| `pre-v4` → `v4` | [share-top-upgrade-old](../sub-skills/share-top-upgrade-old/REFERENCE.md) | 大迁移(需用户确认搬家) |
| `v4` / `v4.5-partial` → `v4.5` | [v4-to-v4.5.md](v4-to-v4.5.md) | 增量(幂等,可自主跑) |

**协议**:探测版本 → 找到阶梯里自己那行 → 跑该级清单 → 重新探测 → 还不是最新就走下一级 → `topic_doctor` verdict ∈ {ok, warn} 且 brief 不再提示升级 = 完成。

## ③ 以后怎么加 v5(扩展协议 — 加新版本只动三处)

1. **特征探测**:`topic-brief.py::detect_sixone_version()` 加 v5 的盘上特征判定 + `SIXONE_LATEST = "v5"`。
2. **delta 清单**:本目录加 `v4.5-to-v5.md`(格式照 v4-to-v4.5.md:幂等步骤 + 每步验收 + "明确不做"段)。
3. **阶梯表**:本 README ① ② 两表各加一行。

加完后**全网自动生效**:所有项目的 brief 立刻开始报"版本=v4.5, 最新=v5",任何对话说"升级到最新"就会走新清单 —— 不需要逐个通知。

清单写作铁律:步骤幂等(重跑无害)/ 每步带验收(实测通过才算)/ 有"明确不做"段(不动 raw/LOCK/论文正本;轻量 profile 不强制)/ 升级 = 跑诊断按 next_hint 清零,不即兴发挥。
