#!/usr/bin/env bash
# lint-claude-md.sh — 检查项目 agent 入口文件是否符合 v4 六合一规范
# 规则源: $HOME/.claude/skills/share-top/references/claude-md-spec.md
# 用法: lint-claude-md.sh [<project-root>]
# 退出码: 0=PASS, 1=ERROR, 2=找不到入口文件

set -euo pipefail
PROJECT="${1:-$PWD}"
ENTRY_MD="${AGENT_ENTRY_FILE:-}"

if [[ -z "$ENTRY_MD" ]]; then
    if [[ -f "$PROJECT/AGENTS.md" ]]; then
        ENTRY_MD="$PROJECT/AGENTS.md"
    else
        echo "❌ 缺少项目入口: $PROJECT/AGENTS.md"
        if [[ -f "$PROJECT/CLAUDE.md" ]]; then
            echo "迁移旧 CLAUDE.md 的有效指令到 AGENTS.md，再退役旧入口。"
        fi
        exit 2
    fi
fi

errors=0
warnings=0
total=$(wc -l < "$ENTRY_MD")

# L0 — AGENTS.md 是唯一项目入口;旧 CLAUDE.md 会优先于 Claude 的 AGENTS.md fallback。
if [[ -z "${AGENT_ENTRY_FILE:-}" && ( -e "$PROJECT/CLAUDE.md" || -L "$PROJECT/CLAUDE.md" ) ]]; then
    echo "🔴 L0 ERROR: 仍有 CLAUDE.md;合并其中有效指令到 AGENTS.md，再退役旧入口。"
    errors=$((errors+1))
fi

# 剥离 lint 白名单注释块以便检测
content=$(sed '/<!-- lint:allow-version-history -->/,/<!-- \/lint -->/d' "$ENTRY_MD")

# L1 — 总行数提示。入口应短,但不因生成式 AGENTS 稍长而阻断。
if (( total > 60 )); then
    echo "🟡 L1 WARN: $total 行 > 60(检查是否混入 current/知识正文)"
    warnings=$((warnings+1))
fi

# L2 — 状态型版本断言
l2_hits=$(echo "$content" | grep -nE "(当前|active|默认|目前|active)[^.]{0,20}[Vv][0-9]" || true)
if [[ -n "$l2_hits" ]]; then
    echo "🔴 L2 ERROR: 状态型版本断言(应放 task_plan, 不放 agent 入口或 codemap):"
    echo "$l2_hits" | sed 's/^/    /'
    errors=$((errors+1))
fi

# L3 — 硬编码版本路径
l3_hits=$(echo "$content" | grep -nE "代码/\w*pipeline_?[Vv][0-9]|src/v[0-9]|apps/v[0-9]|/[a-z]+_v[0-9]+/" || true)
if [[ -n "$l3_hits" ]]; then
    echo "🔴 L3 ERROR: 硬编码版本路径(应放 _codemap.md / _meta/_registry.yml):"
    echo "$l3_hits" | sed 's/^/    /'
    errors=$((errors+1))
fi

# L4 — 必须含入口段(引用 v4 真源; legacy manifest 也允许兼容)
if ! grep -qE "_codemap\.md|_wiki-methodology/_top/_task_plan\.md|wiki-methodology/top/task_plan\.md|TOP files|Source of truth for project progress|项目.*TOP" "$ENTRY_MD"; then
    echo "🔴 L4 ERROR: 缺入口段(必须指向 _codemap.md 或 task_plan)"
    errors=$((errors+1))
fi

# L5 — 反面教材若展开
fanmain_start=$(grep -nE "^(##|\-)\s*反面教材" "$ENTRY_MD" | head -1 | cut -d: -f1 || true)
if [[ -n "$fanmain_start" ]]; then
    fanmain_lines=$(sed -n "${fanmain_start},\$p" "$ENTRY_MD" | wc -l)
    if (( fanmain_lines > 5 )); then
        echo "🟡 L5 WARN: 反面教材段 $fanmain_lines 行(应只索引,>5 行视为展开;具体内容放 _wiki-methodology/_top/_findings/)"
        warnings=$((warnings+1))
    fi
fi

# L6 — 代码规范细节
l6_hits=$(echo "$content" | grep -nE "Python\s*[0-9]+\.[0-9]+|pandas/geopandas|matplotlib|parquet|node\s*[0-9]+" || true)
if [[ -n "$l6_hits" ]]; then
    echo "🟡 L6 WARN: 代码规范细节(应放 pyproject.toml / _codemap.md / _meta/):"
    echo "$l6_hits" | sed 's/^/    /'
    warnings=$((warnings+1))
fi

# L7 — 流水线步骤展开
l7_hits=$(echo "$content" | grep -nE "Step\s*[0-9]+.*→.*Step\s*[0-9]+|步骤[0-9]+→步骤[0-9]+" || true)
if [[ -n "$l7_hits" ]]; then
    echo "🟡 L7 WARN: 流水线步骤展开(应放 _codemap.md / _pipelines/):"
    echo "$l7_hits" | sed 's/^/    /'
    warnings=$((warnings+1))
fi

# 汇总
echo
if (( errors == 0 && warnings == 0 )); then
    echo "✅ PASS — $(basename "$ENTRY_MD") $total 行,符合 v4 六合一入口规范"
    exit 0
elif (( errors == 0 )); then
    echo "🟡 PASS with $warnings warnings — $total 行"
    exit 0
else
    echo "🔴 FAIL: $errors errors / $warnings warnings — $total 行"
    echo "规范详情: $HOME/.claude/skills/share-top/references/claude-md-spec.md"
    exit 1
fi
