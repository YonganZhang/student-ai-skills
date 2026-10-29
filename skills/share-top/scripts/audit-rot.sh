#!/usr/bin/env bash
# audit-rot.sh · 项目级死代码审计 · 六合一 COL 4 健康账本生成器
#
# 输出报告：
#   - $PROJECT/_wiki-methodology/_top/_reports/_dead_code/dead-code-report.md （v4）
#   - $PROJECT/top/dead-code-report.md       （legacy）
#   - $PROJECT/.audit-rot/report.md          （fallback）
#
# 设计原则（三方审计 2026-05-06 修正后）：
# - 候选模式（不自动删，永远人审）
# - 工具用 npx/uvx 按需拉，缺工具 → 显式 _skip: missing_，不阻塞
# - 退出码语义：vulture / ruff / knip / cargo-machete 找到问题都会非零退出，
#   所以一律 `|| true` + 看输出文件是否非空判定

set -euo pipefail
shopt -s globstar 2>/dev/null || true

# --- 入参 / 路径校验 ---
PROJECT="${1:-$PWD}"
if ! PROJECT="$(cd "$PROJECT" 2>/dev/null && pwd)"; then
  echo "audit-rot: ERROR: 项目路径 '${1:-$PWD}' 不存在或无权限" >&2
  exit 2
fi
cd "$PROJECT"

# 输出位置：v4 优先，legacy/fallback 只为旧项目兼容
if [[ -d "_wiki-methodology/_top" ]]; then
  OUT_DIR="$PROJECT/_wiki-methodology/_top/_reports/_dead_code"
  OUT="$OUT_DIR/dead-code-report.md"
elif [[ -d "top" ]]; then
  OUT_DIR="$PROJECT/top"
  OUT="$OUT_DIR/dead-code-report.md"
else
  OUT_DIR="$PROJECT/.audit-rot"
  mkdir -p "$OUT_DIR"
  OUT="$OUT_DIR/report.md"
fi
DETAIL_DIR="$OUT_DIR/.dead-code-raw"
mkdir -p "$DETAIL_DIR"

ts_now() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
have() { command -v "$1" >/dev/null 2>&1; }

# `timeout` 在 macOS 默认没有（要 brew install coreutils → gtimeout）
# 缺失时降级为直接执行（不挂 timeout），避免静默 skip 全部工具
if have timeout; then
  TO() { timeout "$@"; }
elif have gtimeout; then
  TO() { gtimeout "$@"; }
else
  TO() { shift; "$@"; }     # 吞掉首参（秒数），直接跑
fi

# --- 工具可用性（提前检测，报告里说清楚）---
HAS_JQ=0;  have jq  && HAS_JQ=1
HAS_NPX=0; have npx && HAS_NPX=1
HAS_UVX=0; have uvx && HAS_UVX=1
HAS_CARGO=0; have cargo && HAS_CARGO=1

# --- 语言检测（globstar 已开 + maxdepth 兜底，避免大 repo 全扫）---
HAS_TS=0; HAS_PY=0; HAS_RS=0
[[ -f "package.json" ]] && HAS_TS=1
{ [[ -f "pyproject.toml" ]] || [[ -f "setup.py" ]] || \
  find . -maxdepth 4 -name '*.py' \
    -not -path '*/.git/*' -not -path '*/node_modules/*' \
    -not -path '*/.venv/*' -not -path '*/venv/*' \
    -print -quit 2>/dev/null | grep -q .; } && HAS_PY=1
[[ -f "Cargo.toml" ]] && HAS_RS=1

# 主体放进函数，末尾用管道送 tee — 比 process substitution 更稳，无 wait/race
generate_report() {

echo "# Dead-Code Report"
echo "_generated: $(ts_now)_  _project: \`$PROJECT\`_"
echo
echo "> 候选清单 — **未经人工确认禁止删除**。动态 import / 反射 / 插件注册 / CLI 入口都会触发误报。"
echo

# --- TS/JS: knip ---
if [[ $HAS_TS -eq 1 ]]; then
  echo "## TypeScript / JavaScript (knip)"
  if [[ $HAS_NPX -eq 0 ]]; then
    echo "- _skip: \`npx\` not in PATH_"
  elif [[ $HAS_JQ -eq 0 ]]; then
    echo "- _skip: \`jq\` not in PATH（knip 输出无法解析）_"
  else
    RAW="$DETAIL_DIR/knip.json"
    # knip 找到问题时退出 1；只看是否产出了合法 JSON
    TO 90 npx --yes knip --reporter json > "$RAW" 2>"$DETAIL_DIR/knip.err" || true
    if [[ -s "$RAW" ]] && jq -e . "$RAW" >/dev/null 2>&1; then
      ISSUE_FILES=$(jq '.issues | length' "$RAW")
      EXPORTS=$(jq '[.issues[]?.exports     | length] | add // 0' "$RAW")
      DEPS=$(   jq '[.issues[]?.dependencies | length] | add // 0' "$RAW")
      DEVDEPS=$(jq '[.issues[]?.devDependencies | length] | add // 0' "$RAW")
      TYPES=$(  jq '[.issues[]?.types        | length] | add // 0' "$RAW")
      UNLISTED=$(jq '[.issues[]?.unlisted    | length] | add // 0' "$RAW")
      DUPES=$(  jq '[.issues[]?.duplicates   | length] | add // 0' "$RAW")
      echo "- files with issues: **$ISSUE_FILES**"
      echo "- unused exports: **$EXPORTS** · types: **$TYPES** · duplicates: **$DUPES**"
      echo "- unused deps: **$DEPS** · devDeps: **$DEVDEPS** · unlisted (imported but not declared): **$UNLISTED**"
      echo "- raw: \`${RAW#$PROJECT/}\`"
    else
      echo "- _skip: knip 未产出合法 JSON（看 \`${DETAIL_DIR#$PROJECT/}/knip.err\`）_"
    fi
  fi
  echo
fi

# --- Python: vulture + ruff ---
if [[ $HAS_PY -eq 1 ]]; then
  echo "## Python (vulture + ruff F401/F841)"
  if [[ $HAS_UVX -eq 0 ]]; then
    echo "- _skip: \`uvx\` not in PATH（装 uv: \`curl -LsSf https://astral.sh/uv/install.sh | sh\`）_"
  else
    V_RAW="$DETAIL_DIR/vulture.txt"
    R_RAW="$DETAIL_DIR/ruff.json"
    V_COUNT=0; R_COUNT=0

    # vulture：unused funcs/classes/vars (启发式，conf≥80)
    # 找到死代码 exit 3，所以 || true
    TO 60 uvx vulture . --min-confidence 80 \
        --exclude '.venv,venv,node_modules,.git,build,dist' \
        > "$V_RAW" 2>"$DETAIL_DIR/vulture.err" || true
    [[ -s "$V_RAW" ]] && V_COUNT=$(grep -c '' "$V_RAW")

    # ruff：unused imports (F401) + unused vars (F841) — 精确
    # ruff 也是 exit 1 当有 issue
    TO 30 uvx ruff check . --select F401,F841 --output-format json \
        --exclude '.venv,venv,node_modules,build,dist' \
        > "$R_RAW" 2>"$DETAIL_DIR/ruff.err" || true
    if [[ -s "$R_RAW" ]] && [[ $HAS_JQ -eq 1 ]]; then
      R_COUNT=$(jq 'length' "$R_RAW" 2>/dev/null || echo 0)
    fi

    echo "- vulture (functions/classes/vars, conf≥80): **$V_COUNT** 候选"
    if [[ $HAS_JQ -eq 1 ]]; then
      echo "- ruff (unused imports/vars, 精确): **$R_COUNT** 候选"
    else
      echo "- ruff: raw 已生成（\`${R_RAW#$PROJECT/}\`），但 \`jq\` 缺失无法计数"
    fi
    echo "- raw: \`${V_RAW#$PROJECT/}\`, \`${R_RAW#$PROJECT/}\`"
  fi
  echo
fi

# --- Rust: cargo-machete ---
if [[ $HAS_RS -eq 1 ]]; then
  echo "## Rust (cargo-machete)"
  RAW="$DETAIL_DIR/cargo-machete.txt"
  if [[ $HAS_CARGO -eq 0 ]]; then
    echo "- _skip: \`cargo\` not in PATH_"
  else
    TO 60 cargo machete > "$RAW" 2>&1 || true
    if [[ -s "$RAW" ]]; then
      # cargo-machete 列 unused crate 时会有缩进行；用 ERE 兼容性更好
      COUNT=$(grep -cE '^[[:space:]]+' "$RAW" 2>/dev/null || echo 0)
      if grep -qiE 'not found|unrecognized|cannot' "$RAW"; then
        echo "- _skip: cargo-machete 未装（\`cargo install cargo-machete\`）_"
      else
        echo "- unused deps: **$COUNT** 候选"
        echo "- raw: \`${RAW#$PROJECT/}\`"
      fi
    else
      echo "- _skip: cargo-machete 输出为空_"
    fi
  fi
  echo
fi

if [[ $HAS_TS -eq 0 && $HAS_PY -eq 0 && $HAS_RS -eq 0 ]]; then
  echo "## 未识别语言"
  echo "- 项目根没找到 \`package.json\` / \`pyproject.toml\` / \`Cargo.toml\` / \`*.py\`"
  echo
fi

echo "---"
echo "_工具可用性_: jq=$HAS_JQ npx=$HAS_NPX uvx=$HAS_UVX cargo=$HAS_CARGO"
echo "_命令记录_:"
echo
echo "\`\`\`"
[[ $HAS_TS -eq 1 ]] && echo "knip:    npx knip --reporter json"
[[ $HAS_PY -eq 1 ]] && echo "vulture: uvx vulture . --min-confidence 80"
[[ $HAS_PY -eq 1 ]] && echo "ruff:    uvx ruff check . --select F401,F841"
[[ $HAS_RS -eq 1 ]] && echo "machete: cargo machete"
echo "\`\`\`"

}  # end generate_report

# 主体走管道一次性写入 → 脚本退出时 tee 自然收尾
generate_report 2>&1 | tee "$OUT"
