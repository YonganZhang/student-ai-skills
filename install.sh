#!/usr/bin/env bash
# Install the student AI skill pack into Claude Code and/or Codex.
# Run `bash install.sh --help` for usage. Safe by default: copies, never
# overwrites an existing same-name directory unless --force.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$REPO/skills"
SP_SRC="$REPO/third_party/superpowers"
CLAUDE_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
CODEX_DIR="${CODEX_SKILLS_DIR:-$HOME/.agents/skills}"
BIN_DIR="${PLAN_BIN_DIR:-$HOME/.local/bin}"

TARGET="both"; ONLY=""; MODE="copy"; FORCE=0; DRY=0
WITH_PLAN=1; SP_MODE="official"   # official (fallback vendored) | vendored | skip
REQUIRED_SKILLS=(dev-pr-self-check)   # 必装：任何 --only 选择都会带上
WITH_PW=0; PW_PKG="@playwright/cli"   # npm package that provides the playwright-cli command

usage() {
  cat <<'EOF'
用法: bash install.sh [选项]

把本仓库 skills/ 下的技能装到 Claude Code（~/.claude/skills/）和/或 Codex（~/.agents/skills/），
安装 plan 命令（project-top 的计划 CLI），并安装 Superpowers。
playwright-cli 技能需要的 playwright-cli 命令（npm 包 @playwright/cli）默认只检查并提示，不自动全局安装。

选项:
  --target claude|codex|both   安装到哪个宿主（默认 both）
  --only a,b,c                 只装这些技能（用 --list 看名字）；必装技能 dev-pr-self-check 不在其中时也会一并安装；不影响 plan / Superpowers 开关
  --link                       用软链接代替复制（适合 git pull 后自动生效；仓库不能删除或移动）
  --force                      目标已有同名目录/文件时先删除再安装（默认跳过并提示）
  --no-plan                    不安装 plan 命令
  --bin-dir DIR                plan 命令的安装目录（默认 ~/.local/bin）
  --superpowers MODE           official（默认：先官方插件，失败再复制随附 skills）| vendored | skip
  --no-superpowers             等同 --superpowers skip
  --with-playwright            缺 playwright-cli 命令时执行 npm install -g @playwright/cli（需要 Node.js 18+ 与 npm）
  --dry-run                    只打印将要执行的动作，不改任何文件
  --list                       列出可安装的技能（必装的标“必装”）后退出
  -h, --help                   显示本帮助

环境变量: CLAUDE_SKILLS_DIR、CODEX_SKILLS_DIR、PLAN_BIN_DIR 可覆盖默认目录。

例子:
  bash install.sh --dry-run
  bash install.sh
  bash install.sh --target claude --only share-top,grill-to-spec --no-superpowers
  bash install.sh --link --force
  bash install.sh --only playwright-cli --with-playwright --no-superpowers --no-plan

退出码: 0 成功（含按规则跳过的项）；1 安装或校验失败；2 参数错误。
EOF
}

die_usage() { echo "install.sh: $*" >&2; echo "运行 bash install.sh --help 查看用法" >&2; exit 2; }

list_skills() { for d in "$SKILLS_SRC"/*/; do [[ -f "$d/SKILL.md" ]] && basename "$d"; done; }
is_required() { local r; for r in "${REQUIRED_SKILLS[@]}"; do [[ "$r" == "$1" ]] && return 0; done; return 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) [[ $# -ge 2 ]] || die_usage "--target 需要参数"; TARGET="$2"; shift 2 ;;
    --target=*) TARGET="${1#*=}"; shift ;;
    --only) [[ $# -ge 2 ]] || die_usage "--only 需要参数"; ONLY="$2"; shift 2 ;;
    --only=*) ONLY="${1#*=}"; shift ;;
    --link) MODE="link"; shift ;;
    --force) FORCE=1; shift ;;
    --no-plan) WITH_PLAN=0; shift ;;
    --bin-dir) [[ $# -ge 2 ]] || die_usage "--bin-dir 需要参数"; BIN_DIR="$2"; shift 2 ;;
    --bin-dir=*) BIN_DIR="${1#*=}"; shift ;;
    --superpowers) [[ $# -ge 2 ]] || die_usage "--superpowers 需要参数"; SP_MODE="$2"; shift 2 ;;
    --superpowers=*) SP_MODE="${1#*=}"; shift ;;
    --no-superpowers) SP_MODE="skip"; shift ;;
    --with-playwright) WITH_PW=1; shift ;;
    --dry-run) DRY=1; shift ;;
    --list) while IFS= read -r s; do if is_required "$s"; then echo "$s（必装）"; else echo "$s"; fi; done < <(list_skills); exit 0 ;;
    -h|--help) usage; exit 0 ;;
    *) die_usage "未知参数: $1" ;;
  esac
done

case "$TARGET" in claude|codex|both) ;; *) die_usage "--target 只能是 claude、codex 或 both" ;; esac
case "$SP_MODE" in official|vendored|skip) ;; *) die_usage "--superpowers 只能是 official、vendored 或 skip" ;; esac

ALL_SKILLS=()
while IFS= read -r s; do ALL_SKILLS+=("$s"); done < <(list_skills)
SELECTED=()
if [[ -n "$ONLY" ]]; then
  IFS=',' read -r -a want <<< "$ONLY"
  for w in "${want[@]}"; do
    w="${w// /}"; [[ -n "$w" ]] || continue
    found=0; for s in "${ALL_SKILLS[@]}"; do [[ "$s" == "$w" ]] && found=1; done
    [[ $found -eq 1 ]] || die_usage "未知技能: $w（用 --list 查看）"
    SELECTED+=("$w")
  done
else
  SELECTED=("${ALL_SKILLS[@]}")
fi
for req in "${REQUIRED_SKILLS[@]}"; do
  [[ -f "$SKILLS_SRC/$req/SKILL.md" ]] || die_usage "必装技能缺失: $SKILLS_SRC/$req"
  found=0; for s in "${SELECTED[@]}"; do [[ "$s" == "$req" ]] && found=1; done
  if [[ $found -eq 0 ]]; then SELECTED+=("$req"); echo "$req 为必装，已一并安装"; fi
done

HOSTS=()
[[ "$TARGET" == claude || "$TARGET" == both ]] && HOSTS+=("claude")
[[ "$TARGET" == codex || "$TARGET" == both ]] && HOSTS+=("codex")
host_dir() { [[ "$1" == claude ]] && echo "$CLAUDE_DIR" || echo "$CODEX_DIR"; }

INSTALLED=0; SKIPPED=0; FAILED=0
say() { echo "$*"; }
run() { if [[ $DRY -eq 1 ]]; then echo "  [dry-run] $*"; else "$@"; fi; }

# install_dir <src_dir> <dest_dir>
install_dir() {
  local src="$1" dest="$2"
  if [[ -e "$dest" || -L "$dest" ]]; then
    if [[ $FORCE -eq 0 ]]; then
      say "  跳过 $dest（已存在；加 --force 覆盖）"; SKIPPED=$((SKIPPED + 1)); return 0
    fi
    run rm -rf -- "$dest"
  fi
  run mkdir -p "$(dirname "$dest")"
  if [[ "$MODE" == link ]]; then
    run ln -s "$src" "$dest"
  else
    if [[ $DRY -eq 1 ]]; then echo "  [dry-run] cp -R $src $dest（排除 __pycache__）"
    else
      cp -R "$src" "$dest"
      find "$dest" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
    fi
  fi
  say "  $([[ $DRY -eq 1 ]] && echo 将装 || echo 已装) $dest"; INSTALLED=$((INSTALLED + 1))
}

# check_skill <dir>: SKILL.md must start with a frontmatter block containing name and description.
check_skill() {
  local f="$1/SKILL.md"
  [[ -f "$f" ]] || { echo "  校验失败: 缺 $f" >&2; return 1; }
  [[ "$(head -n 1 "$f")" == "---" ]] || { echo "  校验失败: $f 首行不是 ---" >&2; return 1; }
  local fm; fm="$(awk 'NR==1{next} /^---$/{exit} {print}' "$f")"
  grep -q '^name:' <<< "$fm" || { echo "  校验失败: $f 缺 name" >&2; return 1; }
  grep -q '^description:' <<< "$fm" || { echo "  校验失败: $f 缺 description" >&2; return 1; }
}

echo "技能包: $REPO"
echo "宿主: ${HOSTS[*]}  方式: $MODE  覆盖: $([[ $FORCE -eq 1 ]] && echo 是 || echo 否)  dry-run: $([[ $DRY -eq 1 ]] && echo 是 || echo 否)"

# 1. skills
for h in "${HOSTS[@]}"; do
  dir="$(host_dir "$h")"
  echo "== 技能 → $h ($dir)"
  for s in "${SELECTED[@]}"; do install_dir "$SKILLS_SRC/$s" "$dir/$s"; done
done

# 2. plan CLI (points at the installed share-top copy so copy mode survives deleting the repo)
if [[ $WITH_PLAN -eq 1 ]]; then
  echo "== plan 命令 → $BIN_DIR/plan"
  plan_src=""
  for h in "${HOSTS[@]}"; do
    cand="$(host_dir "$h")/share-top/scripts/plan"
    if [[ -f "$cand" || $DRY -eq 1 ]]; then plan_src="$cand"; break; fi
  done
  [[ -n "$plan_src" ]] || plan_src="$SKILLS_SRC/share-top/scripts/plan"
  dest="$BIN_DIR/plan"
  if [[ ( -e "$dest" || -L "$dest" ) && $FORCE -eq 0 ]]; then
    say "  跳过 $dest（已存在；加 --force 覆盖）"; SKIPPED=$((SKIPPED + 1))
  else
    [[ -e "$dest" || -L "$dest" ]] && run rm -f -- "$dest"
    run mkdir -p "$BIN_DIR"
    run ln -s "$plan_src" "$dest"
    say "  $([[ $DRY -eq 1 ]] && echo 将链接 || echo 已链接) $dest -> $plan_src"; INSTALLED=$((INSTALLED + 1))
    case ":$PATH:" in *":$BIN_DIR:"*) ;; *) say "  提示: $BIN_DIR 不在 PATH 中，请把 export PATH=\"$BIN_DIR:\$PATH\" 加入 shell 配置";; esac
  fi
  command -v python3 >/dev/null 2>&1 || say "  提示: 未找到 python3，plan 需要 Python 3.10+"
fi

# 2b. playwright-cli command for the playwright-cli skill: check and hint; global npm install only with --with-playwright
want_pw=$WITH_PW
for s in "${SELECTED[@]}"; do [[ "$s" == playwright-cli ]] && want_pw=1; done
if [[ $want_pw -eq 1 ]]; then
  echo "== playwright-cli 命令（npm 包 $PW_PKG）"
  if command -v playwright-cli >/dev/null 2>&1; then
    say "  已有 $(command -v playwright-cli)（版本 $(playwright-cli --version 2>/dev/null || echo 未知)）"
  elif [[ $WITH_PW -eq 1 ]]; then
    if ! command -v npm >/dev/null 2>&1; then
      echo "  未找到 npm：先安装 Node.js 18+，再运行 npm install -g $PW_PKG" >&2; FAILED=$((FAILED + 1))
    elif run npm install -g "$PW_PKG"; then
      say "  $([[ $DRY -eq 1 ]] && echo 将安装 || echo 已安装) $PW_PKG"; INSTALLED=$((INSTALLED + 1))
    else
      echo "  npm install -g $PW_PKG 失败；没有全局写权限时先 npm config set prefix ~/.npm-global 并把 ~/.npm-global/bin 加入 PATH（见 README）" >&2
      FAILED=$((FAILED + 1))
    fi
  else
    say "  提示: 未找到 playwright-cli 命令。需要浏览器自动化时运行 npm install -g $PW_PKG，或重跑本脚本并加 --with-playwright"
  fi
fi

# 3. Superpowers (official plugin first, vendored skills as fallback)
sp_vendored() {
  local h="$1" dir; dir="$(host_dir "$h")"
  echo "  使用随附 Superpowers $(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' "$SP_SRC/.claude-plugin/plugin.json" | head -n 1) skills → $dir"
  for d in "$SP_SRC"/skills/*/; do
    [[ -f "$d/SKILL.md" ]] && install_dir "${d%/}" "$dir/$(basename "$d")"
  done
}
with_timeout() { if command -v timeout >/dev/null 2>&1; then timeout 300 "$@"; else "$@"; fi; }
sp_official() {
  local h="$1"
  if [[ "$h" == claude ]]; then
    command -v claude >/dev/null 2>&1 || { echo "  未找到 claude 命令"; return 1; }
    if [[ $DRY -eq 1 ]]; then
      echo "  [dry-run] claude plugin install superpowers@claude-plugins-official（失败再试 claude plugin install superpowers）"; return 0
    fi
    # Official marketplace first; a fresh Claude Code may only have the built-in
    # Anthropic directory, whose Superpowers version can lag behind.
    with_timeout claude plugin install superpowers@claude-plugins-official </dev/null && return 0
    echo "  未在 claude-plugins-official 找到，改试内置插件目录（版本可能较旧，可用 claude plugin list 查看）"
    with_timeout claude plugin install superpowers </dev/null
  else
    command -v codex >/dev/null 2>&1 || { echo "  未找到 codex 命令"; return 1; }
    if [[ $DRY -eq 1 ]]; then echo "  [dry-run] codex plugin add superpowers@openai-curated-remote"; return 0; fi
    with_timeout codex plugin add superpowers@openai-curated-remote </dev/null
  fi
}
if [[ "$SP_MODE" != skip ]]; then
  for h in "${HOSTS[@]}"; do
    echo "== Superpowers → $h"
    if [[ "$SP_MODE" == official ]]; then
      if sp_official "$h"; then say "  $([[ $DRY -eq 1 ]] && echo 将用官方插件安装 || echo 官方插件安装完成)"; INSTALLED=$((INSTALLED + 1)); continue; fi
      echo "  官方安装未成功，改用随附副本"
    fi
    sp_vendored "$h"
  done
fi

# 4. verify installed skills
if [[ $DRY -eq 0 ]]; then
  echo "== 校验"
  for h in "${HOSTS[@]}"; do
    dir="$(host_dir "$h")"
    for s in "${SELECTED[@]}"; do check_skill "$dir/$s" || FAILED=$((FAILED + 1)); done
  done
  if [[ $WITH_PLAN -eq 1 && -L "$BIN_DIR/plan" ]]; then
    if "$BIN_DIR/plan" help >/dev/null 2>&1; then echo "  plan help 正常"; else echo "  plan help 运行失败" >&2; FAILED=$((FAILED + 1)); fi
  fi
fi

echo "$([[ $DRY -eq 1 ]] && echo 'dry-run 结束（未改动文件）: 计划' || echo '完成:') 安装 $INSTALLED 项，跳过 $SKIPPED 项，失败 $FAILED 项。新会话中技能才会被发现；Claude Code 可用 /skills 查看。"
[[ $FAILED -eq 0 ]] || exit 1
