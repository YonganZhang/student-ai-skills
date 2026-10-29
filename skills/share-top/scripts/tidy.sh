#!/usr/bin/env bash
# tidy.sh — v4/legacy 一键体检 + 行动清单
#
# 用法: tidy.sh [<project>]
#
# 输出格式 (TSV,5+ 列,首行 # 注释 + 字段名):
#   verb<TAB>severity<TAB>arg1<TAB>arg2<TAB>reason<TAB>meta
#   verb     ∈ {MOVE, LEDGER_MISSING, LEDGER_DRIFT, LINK, RENAME_SUGGEST, DECIDE, CONFLICT}
#   severity ∈ {block, warn, info}
#   meta     k=v;k=v 格式,可含: size_mb, git, dst_exists
#
# 设计:
# - block = AI 应当主动执行 (用户简单确认后)
# - warn  = AI 展示给用户决策,默认不动
# - info  = 仅信息,不需动作
# - 路径用 TAB 分隔 (避免空格歧义);字段缺省用 "-"
# - 全量统计后只展示 top N (默认 N=20),overflow 给汇总数字

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="${1:-$PWD}"
TOP_N="${TIDY_TOP_N:-20}"
SIZE_BLOCK_MB="${TIDY_SIZE_BLOCK_MB:-50}"

cd "$PROJECT" 2>/dev/null || { echo "🔴 无法 cd $PROJECT" >&2; exit 2; }
PROJECT="$PWD"
V4_WIKI="$PROJECT/_wiki-methodology"
LEGACY_WIKI="$PROJECT/wiki-methodology"

if [[ -d "$V4_WIKI" ]]; then
    WIKI="$V4_WIKI"
    PROJECT_LAYOUT="v4"
elif [[ -d "$LEGACY_WIKI" ]]; then
    WIKI="$LEGACY_WIKI"
    PROJECT_LAYOUT="legacy"
else
    echo "⚠️  未检测到 _wiki-methodology/ 或 legacy wiki-methodology/ — 先跑 init-research.sh 或 topic-brief.py 诊断旧布局" >&2
    exit 2
fi

# git 状态
HAS_GIT=0; GIT_DIRTY=""
if git -C "$PROJECT" rev-parse --git-dir >/dev/null 2>&1; then
    HAS_GIT=1
    GIT_DIRTY=$(git -C "$PROJECT" status --porcelain 2>/dev/null)
fi

git_status_for() {
    local f="$1"
    (( HAS_GIT == 0 )) && { echo "no_git"; return; }
    if git -C "$PROJECT" ls-files --error-unmatch "$f" >/dev/null 2>&1; then
        echo "tracked"
    else
        echo "untracked"
    fi
}

size_mb() {
    local f="$1"
    [[ ! -f "$f" ]] && { echo "0"; return; }
    local b=$(stat -c%s "$f" 2>/dev/null || echo 0)
    awk -v b="$b" 'BEGIN{printf "%.1f", b/1024/1024}'
}

# 累计器
declare -a LINES
b_count=0; w_count=0; i_count=0
declare -A category_total category_shown

emit() {
    local verb="$1" sev="$2" a1="$3" a2="$4" reason="$5" meta="${6:--}"
    LINES+=("$verb	$sev	$a1	$a2	$reason	$meta")
}

count_and_emit() {
    # 用法: count_and_emit <category> <verb> <sev> <a1> <a2> <reason> <meta>
    # 计数永远生效 (覆盖 overflow);emit 只在 shown < TOP_N 时
    local cat="$1"; local sev="$3"
    category_total[$cat]=$((${category_total[$cat]:-0}+1))
    case "$sev" in block) b_count=$((b_count+1));; warn) w_count=$((w_count+1));; info) i_count=$((i_count+1));; esac
    shift
    if (( ${category_shown[$cat]:-0} < TOP_N )); then
        emit "$@"
        category_shown[$cat]=$((${category_shown[$cat]:-0}+1))
    fi
}

echo "# tidy-share-top layout=$PROJECT_LAYOUT  project=$(basename "$PROJECT")  date=$(date +%F)  git=$HAS_GIT"
echo "# columns: verb  severity  arg1  arg2  reason  meta"
echo

# ─── 1. 项目根散落代码/笔记本 ───
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    base="${f#./}"
    file_name="$(basename "$f")"
    stem="${file_name%.*}"
    case "$base" in setup.py|conftest.py|noxfile.py|tasks.py|main.py|run.py|app.py) continue;; esac
    if [[ -d "_code" ]]; then dst="_sandbox/$(date +%Y-%m-%d)_${stem}/${file_name}"
    elif [[ -d "src" ]]; then dst="src/$(basename "$f")"
    elif [[ -d "代码" ]]; then dst="代码/$(basename "$f")"
    else dst="_sandbox/$(date +%Y-%m-%d)_${stem}/${file_name}"
    fi
    sz=$(size_mb "$f"); gs=$(git_status_for "$f")
    dst_exists=0; [[ -e "$dst" ]] && dst_exists=1
    meta="size_mb=$sz;git=$gs;dst_exists=$dst_exists"
    # 决策: tracked → warn (用户可能在主动维护); dst 存在 → CONFLICT; size>阈值 → warn
    if (( dst_exists == 1 )); then
        count_and_emit "conflict" CONFLICT warn "$base" "$dst" "dst_already_exists" "$meta"
    elif [[ "$gs" == "tracked" ]]; then
        count_and_emit "root_orphan" DECIDE warn "$base" "$dst" "root_script_tracked_in_git" "$meta"
    elif (( $(echo "$sz > $SIZE_BLOCK_MB" | bc -l 2>/dev/null || echo 0) )); then
        count_and_emit "root_orphan" DECIDE warn "$base" "$dst" "large_file" "$meta"
    else
        count_and_emit "root_orphan" MOVE block "$base" "$dst" "root_orphan_script" "$meta"
    fi
done < <(find . -maxdepth 1 -type f \( -iname "*.py" -o -iname "*.ipynb" \) 2>/dev/null)

# ─── 2. 项目根散落图/PDF ───
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    base="${f#./}"
    dst="_refs/$(basename "$f")"
    sz=$(size_mb "$f"); gs=$(git_status_for "$f")
    dst_exists=0; [[ -e "$dst" ]] && dst_exists=1
    meta="size_mb=$sz;git=$gs;dst_exists=$dst_exists"
    if (( dst_exists == 1 )); then
        count_and_emit "conflict" CONFLICT warn "$base" "$dst" "dst_already_exists" "$meta"
    elif [[ "$gs" == "tracked" ]]; then
        count_and_emit "root_fig" DECIDE warn "$base" "$dst" "tracked_figure" "$meta"
    else
        count_and_emit "root_fig" MOVE block "$base" "$dst" "root_orphan_figure" "$meta"
    fi
done < <(find . -maxdepth 1 -type f \( -iname "*.png" -o -iname "*.pdf" -o -iname "*.svg" -o -iname "*.jpg" -o -iname "*.jpeg" \) 2>/dev/null)

# ─── 2b. 项目根散落数据 ───
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    base="${f#./}"
    dst="_data/$(basename "$f")"
    sz=$(size_mb "$f"); gs=$(git_status_for "$f")
    dst_exists=0; [[ -e "$dst" ]] && dst_exists=1
    meta="size_mb=$sz;git=$gs;dst_exists=$dst_exists"
    if (( dst_exists == 1 )); then
        count_and_emit "conflict" CONFLICT warn "$base" "$dst" "dst_already_exists" "$meta"
    elif [[ "$gs" == "tracked" ]]; then
        count_and_emit "root_data" DECIDE warn "$base" "$dst" "tracked_data" "$meta"
    else
        count_and_emit "root_data" MOVE block "$base" "$dst" "root_orphan_data" "$meta"
    fi
done < <(find . -maxdepth 1 -type f \( -iname "*.csv" -o -iname "*.tsv" -o -iname "*.xlsx" -o -iname "*.parquet" -o -iname "*.jsonl" \) 2>/dev/null)

# ─── 3. 三件套缺 LEDGER ───
while IFS= read -r asset; do
    [[ -z "$asset" ]] && continue
    if [[ -d "$asset/archive" && ! -f "$asset/LEDGER.md" ]]; then
        count_and_emit "ledger_missing" LEDGER_MISSING block "$asset/LEDGER.md" "create" "missing" "-"
    fi
done < <(find . -maxdepth 5 -type d -name current 2>/dev/null \
    | grep -vE "/(legacy|历史文件|node_modules|\.git)/" \
    | sed 's|/current$||')

# ─── 4. current 软链失效 ───
while IFS= read -r link; do
    [[ -z "$link" ]] && continue
    if [[ -L "$link" && ! -e "$link" ]]; then
        target=$(readlink "$link")
        count_and_emit "link_broken" LINK block "$link" "broken" "dangling" "target=$target"
    fi
done < <(find . -maxdepth 6 -path '*/current/*' -type l 2>/dev/null)

# ─── 5. archive 命名违规 (全量计数,展示前 N) ───
bad_total=0
while IFS= read -r f; do
    [[ -z "$f" ]] && continue
    base=$(basename "$f")
    if [[ ! "$base" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}_ ]]; then
        bad_total=$((bad_total+1))
        count_and_emit "bad_name" RENAME_SUGGEST warn "$f" "add_date_prefix" "naming_R1" "-"
    fi
done < <(find . -maxdepth 6 -path '*/archive/*' -type f 2>/dev/null)

# ─── 6. 同名兄弟散落 (同 parent 下 ≥2 个带版本后缀才报,避免单 v1 误报) ───
while IFS=$'\t' read -r parent fam cnt; do
    [[ -z "$parent" || -z "$fam" ]] && continue
    count_and_emit "sibling" DECIDE warn "$parent/${fam}*" "consolidate_to:$parent/${fam}s/" "sibling_sprawl(n=$cnt)" "-"
done < <(find . -maxdepth 3 -type d 2>/dev/null \
    | grep -vE "/(\.git|node_modules|\.venv|legacy|历史文件|raw|archive|current)/" \
    | awk -F/ 'NF>=2 {
        leaf=$NF; parent=""
        for(i=1;i<NF;i++){ parent=(parent=="")?$i:parent"/"$i }
        base=leaf; sub(/_?[Vv][0-9]+$/, "", base)
        if (base != leaf && base != "") print parent "\t" base "\t" leaf
    }' \
    | sort -u \
    | awk -F'\t' '{ k=$1 SUBSEP $2; cnt[k]++; pa[k]=$1; ba[k]=$2 } END { for (k in cnt) if (cnt[k] >= 2) print pa[k] "\t" ba[k] "\t" cnt[k] }')

# ─── 7. LEDGER 反链漂移 (走 lint-fs.py --format tsv,字段: rule\tpath\tdetail) ───
while IFS=$'\t' read -r rule path _; do
    [[ -z "$rule" || "$rule" != "R-b" ]] && continue
    count_and_emit "ledger_drift" LEDGER_DRIFT warn "$path" "add_wiki_backlink" "R-b" "-"
done < <(/usr/bin/python3 "$SCRIPT_DIR/lint-fs.py" --check --project "$PROJECT" --format tsv 2>/dev/null)

# ─── 输出已收集行 ───
for ln in "${LINES[@]}"; do echo "$ln"; done

# ─── overflow 摘要 ───
overflow_lines=()
for cat in "${!category_total[@]}"; do
    total=${category_total[$cat]}
    shown=${category_shown[$cat]:-0}
    if (( total > shown )); then
        overflow_lines+=("$cat: 还有 $((total-shown)) 条未展示 (共 $total)")
    fi
done

if (( ${#overflow_lines[@]} > 0 )); then
    echo
    echo "# overflow:"
    for o in "${overflow_lines[@]}"; do echo "#   $o"; done
fi

# git dirty 提示
if (( HAS_GIT == 1 )) && [[ -n "$GIT_DIRTY" ]]; then
    dirty_count=$(echo "$GIT_DIRTY" | wc -l)
    echo
    echo "# git_dirty: $dirty_count 个未提交变更 — 应用 MOVE 前建议先 commit / stash"
fi

echo
echo "SUMMARY: block=$b_count warn=$w_count info=$i_count"

(( b_count == 0 )) && exit 0 || exit 1
