---
name: share-top-upgrade-old
description: "旧 TOP / 五合一 / 自定义 TOP 升级到当前 v4 的子技能。触发：升级旧六合一、旧五合一迁移、legacy TOP 迁移、TOP.md 迁移到 v4。"
---

# share-top-upgrade-old

目标：把旧项目升级到当前 v4。默认只读检测，不自动搬目录。

## 原则

- v4 是目标标准；旧结构只作为迁移输入。
- 先识别 profile，再决定是否值得迁移。
- legacy / mini / admin / collection / upstream-wrapper / archive 不默认强迁完整 v4。
- 迁移前必须给用户一个短报告：现有入口、风险、建议 profile、会移动/新建什么。
- 未经用户确认，不移动、不删除、不重命名项目文件。

## 步骤

1. 跑只读诊断：

```bash
python3 ~/.claude/skills/share-top/scripts/topic-brief.py <project>
python3 ~/.claude/skills/share-top/scripts/topic-doctor.py <project>
```

详细迁移经验见 `references/upgrade-old-to-v4-flow.md`。这是旧项目升级参考，不是主 skill 日常规则。

2. 判断项目类型：

- active software / active research / active data：可建议升级 v4。
- legacy-compatible：优先做兼容读取和小步升级。
- mini / admin / collection / public-contrib / upstream-wrapper / archive：通常只补 mini TOP 或 wrapper，不完整迁移。

3. 用户确认后才执行迁移或手工收口。

4. 迁移完成后验证：

```bash
python3 ~/.claude/skills/share-top/scripts/topic-brief.py <project>
python3 ~/.claude/skills/share-top/scripts/topic-doctor.py <project>
python3 ~/.claude/skills/share-top/scripts/top-status.py <project>
```

## 输出

迁移报告只写三件事：

- 旧入口在哪里。
- 新 v4 真源放哪里。
- 还有哪些债务不能自动处理。
