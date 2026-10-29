#!/usr/bin/env bash
# 扫描 $HOME/.claude/skills/（可用 SKILLS_DIR 覆盖，如 ~/.agents/skills 或 <项目>/.claude/skills）下所有 skill，验证入口文件命名合规：
#   - 必须存在大写 SKILL.md
#   - 禁止存在小写 skill.md / 大小写混合 Skill.md 作为唯一入口
#   - 报告 README.md 作为辅助文件（不强制）
#
# Claude Code skill loader 只扫描大写 SKILL.md，小写或混合命名会导致整个 skill
# 从所有会话里消失，而且不会报错。
#
# Usage:
#   bash check_skill_filenames.sh            # 扫描并报错退出
#   bash check_skill_filenames.sh --fix      # 自动改名修复（在 Git 仓库内用 git mv）
#
# Exit codes:
#   0 = 全部合规
#   1 = 发现违规（--fix 未加时）

set -eu
SKILLS_DIR="${SKILLS_DIR:-$HOME/.claude/skills}"
FIX_MODE=0
[[ "${1:-}" == "--fix" ]] && FIX_MODE=1

[[ ! -d "$SKILLS_DIR" ]] && { echo "[ERROR] $SKILLS_DIR not found"; exit 2; }

bad=()
missing=()
total=0

for dir in "$SKILLS_DIR"/*/; do
  [[ -d "$dir" ]] || continue
  name=$(basename "$dir")
  # 跳过 _ 前缀的归档目录（约定：_legacy / _archive / _old 等非活跃归档）
  [[ "$name" == _* ]] && continue
  total=$((total + 1))

  # 正确：大写 SKILL.md 存在
  if [[ -f "$dir/SKILL.md" ]]; then
    # 同时警告：如果还存在小写 skill.md（极罕见），也要指出
    if [[ -f "$dir/skill.md" && ! "$dir/SKILL.md" -ef "$dir/skill.md" ]]; then
      echo "⚠️  $name 目录同时存在 SKILL.md 和 skill.md（文件系统大小写敏感）"
    fi
    continue
  fi

  # 缺大写但有其他变体
  alt=""
  for variant in "$dir/skill.md" "$dir/Skill.md" "$dir/SKILL.MD" "$dir/skill.MD"; do
    if [[ -f "$variant" ]]; then
      alt="$variant"
      break
    fi
  done

  if [[ -n "$alt" ]]; then
    bad+=("$name|$alt")
  elif [[ -f "$dir/README.md" || -f "$dir/readme.md" ]]; then
    missing+=("$name (只有 README.md, 缺 SKILL.md)")
  else
    missing+=("$name (完全无入口文件)")
  fi
done

echo ""
echo "=== Skill 入口文件扫描报告（共 $total 个 skill 目录）==="

if [[ ${#bad[@]} -eq 0 && ${#missing[@]} -eq 0 ]]; then
  echo "✅ 全部合规（每个技能目录都有大写 SKILL.md）"
  exit 0
fi

if [[ ${#bad[@]} -gt 0 ]]; then
  echo ""
  echo "🔴 命名违规（SKILL.md 大小写错）：${#bad[@]} 个"
  for entry in "${bad[@]}"; do
    name="${entry%%|*}"
    path="${entry##*|}"
    echo "  - $name: 现为 $(basename "$path")"
  done
fi

if [[ ${#missing[@]} -gt 0 ]]; then
  echo ""
  echo "⚠️  缺入口文件：${#missing[@]} 个"
  for entry in "${missing[@]}"; do
    echo "  - $entry"
  done
fi

if [[ $FIX_MODE -eq 1 && ${#bad[@]} -gt 0 ]]; then
  echo ""
  echo "=== --fix 模式：改名为 SKILL.md ==="
  fixfail=0
  for entry in "${bad[@]}"; do
    name="${entry%%|*}"
    path="${entry##*|}"
    dir="$(dirname "$path")"
    # two-step rename so case-insensitive file systems (macOS) also pick up the new case
    tmp="$(basename "$path").rename-tmp"
    echo "  $path → $dir/SKILL.md"
    if git -C "$dir" rev-parse --is-inside-work-tree >/dev/null 2>&1 && git -C "$dir" ls-files --error-unmatch "$(basename "$path")" >/dev/null 2>&1; then
      { git -C "$dir" mv "$(basename "$path")" "$tmp" && git -C "$dir" mv "$tmp" SKILL.md; } 2>&1 || { echo "[FAIL] $name"; fixfail=1; }
    else
      { mv "$path" "$dir/$tmp" && mv "$dir/$tmp" "$dir/SKILL.md"; } 2>&1 || { echo "[FAIL] $name"; fixfail=1; }
    fi
  done
  echo ""
  echo "修复完成，请检查 git status 后提交"
  exit $fixfail
fi

if [[ ${#bad[@]} -gt 0 ]]; then
  echo ""
  echo "执行 'bash $0 --fix' 自动修复命名违规"
fi

exit 1
