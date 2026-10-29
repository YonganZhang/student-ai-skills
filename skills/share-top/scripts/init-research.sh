#!/usr/bin/env bash
# init-research.sh — 初始化 TOP 项目(必需部分 + 按 --kind 的常用目录)
#
# 用法:
#   bash ~/.claude/skills/share-top/scripts/init-research.sh <project_dir> [--kind research|dev] [--with <模块,...>]
#
# 必需部分:
#   AGENTS.md(≤60 行,不写当前状态;Claude/Codex 共读)
#   _wiki-methodology/_top/_task_plan.md(坐标 + 当前任务) + _wiki-methodology/_top/_logs/
# 常用目录(--kind,默认 research;每个带 _readme.md,来自 templates/v4-architecture/<目录>/_readme.md,
#   按五问写:放什么/不放什么/入口/文件角色/改动原因去哪查):
#   research:_code _data _outputs _figures _paper _refs _sandbox _tmp _legacy _meta
#   dev:     _meta _sandbox _tmp _legacy;模块目录(frontend/ backend/ …)按需自建,
#            每个放一份 README(模板 templates/dir-readme.md)
# 已有的目录/文件一律不覆盖(cp -n);目录里已有任意 README 时不再补 _readme.md。
#
# .gitignore 基线(--kind;模板在 templates/gitignore/<kind>.gitignore):
#   目标没有 .gitignore → 复制模板;已有 → 只把模板里缺的规则追加到标记块
#   "# >>> top baseline (<kind>) >>>" … "# <<< top baseline <<<"(幂等,不改块外内容)。
#   research:公共段 + /_data、/_outputs 下的大体量二进制 + /_sandbox 实验输出
#   dev:     公共段 + dist/build/coverage/.next 等构建产物(fixtures 不忽略)
#   已初始化的项目:显式给 --kind 即只补缺的常用目录与 .gitignore 基线(计划已存在也不会跳过);
#   只给 --with 时不补常用目录。
#
# 可选模块(--with 逗号分隔,可重复;对已初始化项目也可单独补模块):
#   codemap        _codemap.md(L0 路由,≤5KB)
#   registry       _meta/_registry.yml(代码/工具登记)
#   data-registry  _meta/_data_registry.yml(数据资产登记)
#   decisions      _wiki-methodology/_top/_decisions/(可复用理由与教训)
#   wiki           _wiki-methodology/_wiki/(领域知识)
#   tests          _wiki-methodology/_tests/(gate 清单与覆盖)
#   pipelines      _pipelines/
#   codebook       已退役(2026-09-24):不再创建;代码用 CodeGraph + _codemap.md + 决策记忆
#   dirs           research 的全部常用目录(research 默认已建;dev 项目需要科研目录时用)
#   full           旧版整套 v4 骨架(兼容用;含 phases/external_reviews/six_dim_contract/naming 等)
# whole picture 不在初始化里生成,只在用户明确要网页时按需生成。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SHARE_TOP="$(cd "$SCRIPT_DIR/.." && pwd)"
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
AI_SHARED_HOME="${AI_SHARED_HOME:-$HOME/.agents}"
MINIMAL="$SHARE_TOP/templates/minimal"
FULL="$SHARE_TOP/templates/v4-architecture"
RESEARCH_DIRS=(_code _data _outputs _figures _paper _refs _sandbox _tmp _legacy _meta)
DEV_DIRS=(_meta _sandbox _tmp _legacy)

usage() { echo "用法: $0 <project_dir> [--kind research|dev] [--with codemap,registry,data-registry,decisions,wiki,tests,pipelines,dirs,full]" >&2; }

TARGET=""
MODULES=()
KIND="research"
KIND_EXPLICIT=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --with) [[ $# -ge 2 ]] || { usage; exit 1; }; IFS=',' read -r -a more <<< "$2"; MODULES+=("${more[@]}"); shift 2 ;;
        --with=*) IFS=',' read -r -a more <<< "${1#--with=}"; MODULES+=("${more[@]}"); shift ;;
        --kind) [[ $# -ge 2 ]] || { usage; exit 1; }; KIND="$2"; KIND_EXPLICIT=1; shift 2 ;;
        --kind=*) KIND="${1#--kind=}"; KIND_EXPLICIT=1; shift ;;
        -h|--help) usage; exit 0 ;;
        -*) echo "ERROR: 未知参数 $1" >&2; usage; exit 1 ;;
        *) [[ -z "$TARGET" ]] || { usage; exit 1; }; TARGET="$1"; shift ;;
    esac
done
[[ -n "$TARGET" ]] || { usage; exit 1; }

case "$KIND" in
    research|dev) ;;
    *) echo "ERROR: 未知 --kind '$KIND'(只支持 research|dev)" >&2; usage; exit 1 ;;
esac
GITIGNORE_TEMPLATE="$SHARE_TOP/templates/gitignore/$KIND.gitignore"
[[ -f "$GITIGNORE_TEMPLATE" ]] || { echo "ERROR: 模板不存在: $GITIGNORE_TEMPLATE(share-top 未装完整)" >&2; exit 1; }

for module in "${MODULES[@]}"; do
    case "$module" in
        codemap|registry|data-registry|decisions|wiki|tests|pipelines|codebook|dirs|full) ;;
        *) echo "ERROR: 未知模块 '$module'" >&2; usage; exit 1 ;;
    esac
done

TARGET_ABS="$(readlink -f "$TARGET" 2>/dev/null || python3 -c 'import pathlib,sys; print(pathlib.Path(sys.argv[1]).expanduser().resolve())' "$TARGET")"
HOME_ABS="$(readlink -f "$HOME" 2>/dev/null || printf '%s' "$HOME")"
CODEX_HOME_ABS="$(readlink -f "$CODEX_HOME" 2>/dev/null || printf '%s' "$CODEX_HOME")"
CLAUDE_HOME_ABS="$(readlink -f "$CLAUDE_HOME" 2>/dev/null || printf '%s' "$CLAUDE_HOME")"
AI_SHARED_HOME_ABS="$(readlink -f "$AI_SHARED_HOME" 2>/dev/null || printf '%s' "$AI_SHARED_HOME")"

if [[ "$TARGET_ABS" == "/" || "$TARGET_ABS" == "$HOME_ABS" || "$TARGET_ABS" == "$CODEX_HOME_ABS" || "$TARGET_ABS" == "$CODEX_HOME_ABS"/* || "$TARGET_ABS" == "$CLAUDE_HOME_ABS" || "$TARGET_ABS" == "$CLAUDE_HOME_ABS"/* || "$TARGET_ABS" == "$AI_SHARED_HOME_ABS" || "$TARGET_ABS" == "$AI_SHARED_HOME_ABS"/* || "$TARGET_ABS" == "$SHARE_TOP" ]]; then
    echo "ERROR: 拒绝在敏感目录初始化: $TARGET_ABS" >&2
    exit 2
fi

for template in "$MINIMAL" "$FULL"; do
    [[ -d "$template" ]] || { echo "ERROR: 模板目录不存在: $template(share-top 未装完整)" >&2; exit 1; }
done

if [[ -f "$TARGET/CLAUDE.md" && ! -f "$TARGET/AGENTS.md" ]]; then
    echo "ERROR: 项目只有旧 CLAUDE.md;先将有效指令迁入 AGENTS.md，再初始化。未修改现有入口。" >&2
    exit 2
fi

PLAN_REL="_wiki-methodology/_top/_task_plan.md"
PLAN_EXISTED=0
[[ -f "$TARGET/$PLAN_REL" ]] && PLAN_EXISTED=1
if [[ $PLAN_EXISTED -eq 1 && ${#MODULES[@]} -eq 0 && $KIND_EXPLICIT -eq 0 ]]; then
    echo "⚠️  $TARGET 已有 $PLAN_REL,跳过;要补可选模块用 --with,只补 .gitignore 基线用 --kind research|dev" >&2
    exit 1
fi

mkdir -p "$TARGET"
cd "$TARGET"

copy_rel() {  # copy one template path without overwriting anything that exists
    local rel="$1"
    local src="$FULL/$rel"
    [[ -e "$src" ]] || { echo "ERROR: 模板缺 $rel" >&2; exit 1; }
    mkdir -p "$(dirname "$rel")"
    cp -rn "$src" "$(dirname "$rel")/"
}

echo "📁 $TARGET_ABS"
cp -rn "$MINIMAL"/. .
echo "✅ 必需部分: AGENTS.md $PLAN_REL _wiki-methodology/_top/_logs/"

apply_gitignore_baseline() {  # new file = template copy; existing file = missing rules into a marked block
    if [[ ! -e .gitignore ]]; then
        cp "$GITIGNORE_TEMPLATE" .gitignore
        echo "✅ .gitignore: 复制 $KIND 模板"
        return
    fi
    python3 - "$GITIGNORE_TEMPLATE" .gitignore "$KIND" <<'PY'
import sys
from pathlib import Path

template, target, kind = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
begin, end = f"# >>> top baseline ({kind}) >>>", "# <<< top baseline <<<"
raw = target.read_bytes().decode("utf-8")
newline = "\r\n" if "\r\n" in raw else "\n"
lines = raw.splitlines()
start = lines.index(begin) if begin in lines else None
stop = None
if start is not None:
    stop = next((i for i in range(start + 1, len(lines)) if lines[i] == end), None)
    if stop is None:
        sys.exit(f"ERROR: {target} 有 '{begin}' 却缺结束标记 '{end}',请手工修好再跑")
have = {line.strip() for line in lines}
rules = [line.strip() for line in template.read_text(encoding="utf-8").splitlines()]
missing = [r for r in dict.fromkeys(rules) if r and not r.startswith("#") and r not in have]
if not missing:
    print(f"✅ .gitignore: 已含 {kind} 基线的全部规则,未改动")
    sys.exit(0)
if start is None:
    out = lines + ([""] if lines and lines[-1].strip() else []) + [begin, *missing, end]
else:
    out = lines[:stop] + missing + lines[stop:]
with target.open("w", encoding="utf-8", newline="") as handle:
    handle.write(newline.join(out) + newline)
print(f"✅ .gitignore: 追加 {len(missing)} 条 {kind} 基线规则到标记块")
PY
}
apply_gitignore_baseline

ensure_dirs() {  # <label> <dir...>: create each dir with its template _readme.md; never overwrite, skip when any README exists
    local label="$1" d made=()
    shift
    for d in "$@"; do
        [[ -f "$FULL/$d/_readme.md" ]] || { echo "ERROR: 模板缺 $d/_readme.md" >&2; exit 1; }
        mkdir -p "$d"
        if [[ -z "$(find "$d" -maxdepth 1 -type f \( -iname '_readme.md' -o -iname 'readme.md' -o -iname 'readme' \))" ]]; then
            cp -n "$FULL/$d/_readme.md" "$d/_readme.md"
            made+=("$d")
        fi
    done
    if [[ ${#made[@]} -gt 0 ]]; then
        echo "✅ 常用目录($label,补了 _readme.md): ${made[*]}"
    else
        echo "✅ 常用目录($label): 都已存在且有 README,未改动"
    fi
}
# New project, or an explicit --kind on an existing one; a bare --with on an old project leaves its layout alone.
if [[ $PLAN_EXISTED -eq 1 && $KIND_EXPLICIT -eq 0 ]]; then
    :
elif [[ "$KIND" == "research" ]]; then
    ensure_dirs research "${RESEARCH_DIRS[@]}"
else
    ensure_dirs dev "${DEV_DIRS[@]}"
    echo "ℹ️  模块目录(如 frontend/ backend/)按需创建,每个放一份 README(模板 templates/dir-readme.md,即 $SHARE_TOP/templates/dir-readme.md)"
fi

for module in "${MODULES[@]}"; do
    case "$module" in
        codemap) copy_rel _codemap.md ;;
        registry) copy_rel _meta/_registry.yml ;;
        data-registry) copy_rel _meta/_data_registry.yml ;;
        decisions) copy_rel _wiki-methodology/_top/_decisions ;;
        wiki) copy_rel _wiki-methodology/_wiki ;;
        tests) copy_rel _wiki-methodology/_tests ;;
        pipelines) copy_rel _pipelines ;;
        codebook)
            echo "⚠️  CodeBook 已退役:不创建 _codebook/。代码结构用 CodeGraph,入口写 _codemap.md(--with codemap),理由用 --with decisions" >&2
            continue ;;
        dirs) ensure_dirs "--with dirs" "${RESEARCH_DIRS[@]}" ;;
        full) cp -rn "$FULL"/. . ;;
    esac
    echo "➕ 可选模块: $module"
done

echo ""
echo "🔍 plan validate:"
python3 "$SCRIPT_DIR/sixone-cli.py" plan validate . | python3 -c 'import json,sys; r=json.load(sys.stdin); print("verdict=%s errors=%d" % (r.get("verdict"), len(r.get("errors") or [])))'

echo ""
echo "下一步:"
echo "  1. 填 AGENTS.md 的项目名/不变量/验证命令(≤60 行,不写当前状态)"
echo "  2. 用 plan edit / plan add --gate \"<验收标准>\" 写清首个任务,再 plan start"
echo "  3. 真需要时再用 --with 补可选模块,并在 AGENTS.md 真源入口加一行指针"
