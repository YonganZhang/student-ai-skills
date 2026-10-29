#!/usr/bin/env bash
# gen-upstream-codemap.sh · 通用 upstream codemap 生成器
# 任何 downstream 接 upstream 任务的第一动作 · 跑这个脚本生成 8 章节 codemap 骨架
# 详见 $HOME/.claude/skills/share-top/references/upstream-sync-codemap-first.md
set -e

if [ "$#" -lt 3 ]; then
  cat <<EOF
Usage: gen-upstream-codemap.sh <upstream-root> <downstream-root> <upstream-name>

参数:
  upstream-root    upstream 项目根目录(老师/客户/官方源 mirror 路径)
  downstream-root  我们项目根目录(写入 _wiki-methodology/_top/_codemaps/)
  upstream-name    upstream 短名(用于文件名 + 标题 · 如 'teacher-pipelines')

示例:
  ./gen-upstream-codemap.sh \\
    ~/projects/foo/upstream \\
    ~/projects/foo/our-app \\
    teacher-pipelines

输出: <downstream-root>/_wiki-methodology/_top/_codemaps/<upstream-name>-codemap.md
EOF
  exit 1
fi

UP="$1"
DN="$2"
NAME="$3"
OUT="$DN/_wiki-methodology/_top/_codemaps/${NAME}-codemap.md"

[ ! -d "$UP" ] && { echo "🔴 upstream 不存在: $UP"; exit 1; }
[ ! -d "$DN" ] && { echo "🔴 downstream 不存在: $DN"; exit 1; }
mkdir -p "$(dirname "$OUT")"

DATE=$(date +%Y-%m-%d)

cat > "$OUT" <<HEADER
# $NAME · upstream codemap + 我们差距地图

> **一份顶 N 次扫描** · 任何未来会话/Codex/cc 只读这一份就秒懂全貌
> 真扫日期:$DATE
> upstream 路径:$UP
> downstream 路径:$DN
> 维护规则:每次接入新模块必更新 § 3 已接列 · upstream 升级 → 跑 § 8 重扫命令更新

## 1 · upstream 顶层目录全图

\`\`\`
HEADER

ls -d "$UP"/*/ 2>/dev/null | xargs -I{} basename {} | sed 's/^/  /' >> "$OUT"

cat >> "$OUT" <<EOF
\`\`\`

(每个目录用途待 cc Read 后补 · 不要省略任何目录 · 不知道用途的也要列出来标 ❓)

## 2 · downstream 项目结构对照

(cc 填:downstream 项目主目录 / 已接 upstream 的 vendor / mirror 位置)

## 3 · 子模块差距矩阵(核心)

| upstream 子模块 | 文件数 | upstream 真有 | downstream 已接 | 接入度 | 优先级 |
|---|---|---|---|---|---|
EOF

# 自动扫 upstream 子模块文件数
if [ -d "$UP/scripts" ] || [ -d "$UP/src" ]; then
  ROOT_FOR_SUB="$UP"
  [ -d "$UP/scripts" ] && ROOT_FOR_SUB="$UP/scripts"
  [ -d "$UP/src" ] && ROOT_FOR_SUB="$UP/src"
  for sub in "$ROOT_FOR_SUB"/*/; do
    [ ! -d "$sub" ] && continue
    name=$(basename "$sub")
    [[ "$name" == "__pycache__" ]] && continue
    pycount=$(find "$sub" -name "*.py" 2>/dev/null | wc -l)
    sample=$(ls "$sub" 2>/dev/null | grep -v __ | head -2 | tr '\n' ' ')
    echo "| $name/ | $pycount py | (待 cc 填用途 · 例:$sample) | (待填 · grep downstream 已接) | (%)| (高/中/低)|" >> "$OUT"
  done
fi

cat >> "$OUT" <<EOF

## 4 · upstream 升级时间线(看 CLAUDE.md / README 日期标记)

EOF

if [ -f "$UP/CLAUDE.md" ]; then
  echo "(从 $UP/CLAUDE.md 提日期标记)" >> "$OUT"
  echo "" >> "$OUT"
  grep -nE "20[0-9]{2}-[0-9]{2}-[0-9]{2}" "$UP/CLAUDE.md" 2>/dev/null | tail -10 | sed 's/^/- /' >> "$OUT" || true
elif [ -f "$UP/README.md" ]; then
  echo "(从 $UP/README.md 提日期标记)" >> "$OUT"
  echo "" >> "$OUT"
  grep -nE "20[0-9]{2}-[0-9]{2}-[0-9]{2}" "$UP/README.md" 2>/dev/null | tail -10 | sed 's/^/- /' >> "$OUT" || true
fi

cat >> "$OUT" <<EOF

## 5 · 顶层目录差距(逐个目录 · downstream 应否接)

| upstream 目录 | 内容 | downstream 应做 |
|---|---|---|
EOF

ls -d "$UP"/*/ 2>/dev/null | xargs -I{} basename {} | while read d; do
  count=$(find "$UP/$d" -type f 2>/dev/null | wc -l)
  size=$(du -sh "$UP/$d" 2>/dev/null | cut -f1)
  echo "| $d/ | $count files · $size | (待 cc 填:接 / 不接 / 部分 · 理由)|" >> "$OUT"
done

cat >> "$OUT" <<EOF

## 6 · 工具链 / CLI 差距(若 upstream 含 N+ 工具)

(cc 填 · 例:upstream 30 个 CLI 工具 · 我们已接 X 个)

## 7 · 优先级建议(立即 / 中期 / 可选)

### 立即(高优先 · 阻塞下游)

(cc 填)

### 中优先

(cc 填)

### 可选

(cc 填)

## 8 · 重扫命令(upstream 升级时一行重跑)

\`\`\`bash
UP="$UP"
DN="$DN"
NAME="$NAME"

# 8.1 upstream 顶层目录变化
ls -d "\$UP"/*/

# 8.2 upstream 子模块脚本数变化
find "\$UP" -name "*.py" 2>/dev/null | awk -F/ '{print \$(NF-1)}' | sort | uniq -c | sort -rn | head -20

# 8.3 downstream 已接清单(grep 模式 · 按实际项目调)
grep -rohE "(playbook|src|scripts|vendor)/[a-z_-]+/[a-z_-]+\.py" "\$DN/" 2>/dev/null | sort -u

# 8.4 upstream CLAUDE.md / README 最新章节
grep -nE "20[0-9]{2}-[0-9]{2}-[0-9]{2}" "\$UP/CLAUDE.md" 2>/dev/null | tail -5

# 8.5 重生成 codemap(本脚本)
$HOME/.claude/skills/share-top/scripts/gen-upstream-codemap.sh "\$UP" "\$DN" "\$NAME"
\`\`\`

## 9 · Origin 记录(本 codemap 锁定的 upstream 状态)

- upstream repo / path: $UP
- snapshot date: $DATE
- snapshot commit: (cc 填 · git -C "$UP" rev-parse HEAD 若是 git repo)
- sync mode: copied / symlink / submodule / lazy-read / adapted (cc 填)
- do-not-edit policy: upstream 来源文件视为权威 · 本地修改需在本 codemap § 3 记录

## 10 · 相关协议

- 工作流总纲:\`$HOME/.claude/skills/share-top/references/upstream-sync-codemap-first.md\`
- 六合一架构:\`$HOME/.claude/skills/share-top/SKILL.md\`
- COL 4 生命周期:\`$HOME/.claude/skills/share-top/references/col4-lifecycle.md\`
EOF

echo "✅ codemap 骨架已生成: $OUT"
echo
echo "下一步(cc 必做):"
echo "  1. Read 它 · 按 § 1-7 各节 cc 实际 Read upstream 目录后补内容(不能留 '待 cc 填')"
echo "  2. 项目 AGENTS.md 顶部加指针 · 让未来会话第一时间 Read 这份"
echo "  3. 走 references/upstream-sync-codemap-first.md § 1.4 决策"
echo "  4. 完成时过 § 10 自检 6 条"
