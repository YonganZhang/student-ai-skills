#!/usr/bin/env bash
# v4-cleanup.sh — 扫项目根, 报告不合 v4 规则的顶级文件/目录
#
# 用法:
#   bash $HOME/.claude/skills/share-top/scripts/v4-cleanup.sh [<project_dir>]
#
# 输出处置建议清单, 不实际执行(用户确认后再批量 mv/rm).
#
# 规则:
#   ✅ 通过: _ 开头 / 白名单 / 隐藏文件
#   ❌ 不通过: 非 _ 开头 + 非白名单 + 非 . 开头

set -euo pipefail

PROJECT="${1:-$(pwd)}"
cd "$PROJECT"

# 白名单 (跟 _code/lint.py 的 ROOT_WHITELIST 保持一致)
WHITELIST=(
    "AGENTS.md"
    "CLAUDE.md"
    "README.md"
    ".git"
    ".gitignore"
    ".gitattributes"
    ".obsidian"
    ".claude"
    ".codex"
    ".vscode"
    "wiki-methodology"  # v4 兼容期保留
)

is_whitelisted() {
    local name="$1"
    for w in "${WHITELIST[@]}"; do
        [[ "$name" == "$w" ]] && return 0
    done
    return 1
}

guess_destination() {
    local name="$1"
    local is_dir="$2"  # "1" if dir, "0" if file
    local lower
    lower="$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]')"

    # 启发式规则
    if [[ "$lower" == *.pdf || "$lower" == *.docx || "$lower" == *.pptx ]]; then
        echo "_refs/ (参考资料)"
        return
    fi
    if [[ "$lower" == *.png || "$lower" == *.jpg || "$lower" == *.jpeg ]]; then
        echo "_refs/ 或 _figures/(看是论文图还是参考资料)"
        return
    fi
    if [[ "$lower" == *.py || "$lower" == *.ipynb ]]; then
        if [[ "$is_dir" == "1" ]]; then
            echo "_code/ 或 _pipelines/(代码目录, 看是工具还是 pipeline)"
        else
            echo "_sandbox/<date>_<topic>/ (单文件代码/Notebook 建议进 sandbox 探索区, 或 _code/ 工具)"
        fi
        return
    fi
    if [[ "$lower" == *.csv || "$lower" == *.tsv || "$lower" == *.xlsx || "$lower" == *.parquet || "$lower" == *.jsonl ]]; then
        echo "_data/ (数据) 或 _tmp/ (临时)"
        return
    fi
    if [[ "$lower" == *.tex || "$lower" == *.bib ]]; then
        echo "_paper/"
        return
    fi
    # 目录名包含特征词
    if [[ "$is_dir" == "1" ]]; then
        case "$lower" in
            *legacy*|*old*|*archive*|*backup*|历史*) echo "_legacy/" ;;
            *temp*|*tmp*|*scratch*|*download*|*下载*) echo "_tmp/" ;;
            *data*|*dataset*|*input*|*数据*) echo "_data/" ;;
            *output*|*result*|*report*|*结果*|*报告*) echo "_outputs/" ;;
            *paper*|*manuscript*|*论文*) echo "_paper/" ;;
            *figure*|*plot*|*viz*|*image*|*图*|*图表*) echo "_figures/" ;;
            *ref*|*literature*|*pdf*|*paper-ref*|*文献*) echo "_refs/" ;;
            *code*|*src*|*lib*|*代码*) echo "_code/ + _pipelines/(看是工具还是 pipeline)" ;;
            *) echo "_legacy/<name>-$(date +%Y-%m-%d)/ 或 _tmp/(待用户决定)" ;;
        esac
        return
    fi
    echo "_tmp/ (临时存放) → 整理后归档"
}

echo "🔍 v4 _ 前缀扫描: $PROJECT"
echo ""

V4_INITIALIZED=0
if [[ -f "_codemap.md" ]]; then
    V4_INITIALIZED=1
    echo "✓ v4 已初始化 (_codemap.md 存在)"
else
    echo "⚠️  v4 未初始化 (_codemap.md 不存在)"
    echo "  → 建议先跑 init-research.sh 初始化 v4 骨架"
fi
echo ""

VIOLATIONS=0
PROPOSALS=()

for entry in *; do
    name="$entry"
    [[ ! -e "$entry" ]] && continue

    # _ 开头 → 通过
    if [[ "$name" == _* ]]; then
        continue
    fi
    # 隐藏文件 → 通过
    if [[ "$name" == .* ]]; then
        continue
    fi
    # 白名单 → 通过
    if is_whitelisted "$name"; then
        continue
    fi

    # 违规
    VIOLATIONS=$((VIOLATIONS + 1))
    if [[ -d "$entry" ]]; then
        is_dir=1
        kind="目录"
    else
        is_dir=0
        kind="文件"
    fi
    dest=$(guess_destination "$name" "$is_dir")
    PROPOSALS+=("  ❌ $kind $name → $dest")
done

if [[ $VIOLATIONS -eq 0 ]]; then
    echo "✅ 全部顶级 entry 都合 v4 _ 前缀规则 (或在白名单)"
else
    echo "❌ 发现 $VIOLATIONS 个不合规 entry:"
    printf '%s\n' "${PROPOSALS[@]}"
fi

echo ""
echo "📋 处置建议(用户确认后执行,不自动跑):"
echo "  1. 老代码/数据 → mv 到 _legacy/<原名>-$(date +%Y-%m-%d)/"
echo "  2. 临时/混乱 → mv 到 _tmp/"
echo "  3. 参考资料 → mv 到 _refs/"
echo "  4. 真无用 → rm (用户明确同意才删)"
echo "  5. 应进 v4 主目录的代码 → migrate 到 _code/ / _pipelines/"
echo ""
echo "💡 跑 init-research.sh 初始化新项目:"
echo "  bash $HOME/.claude/skills/share-top/scripts/init-research.sh <project>"

[[ $VIOLATIONS -eq 0 ]] && exit 0 || exit 1
