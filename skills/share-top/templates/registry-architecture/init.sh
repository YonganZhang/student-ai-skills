#!/bin/bash
# 一键装注册架构到任意新项目 (跨项目复用入口)
# 跑法: bash $HOME/.claude/skills/share-top/templates/registry-architecture/init.sh <project_dir>
# 装啥: schema + 3 CLI + pre-commit hook + AGENTS.md hint, 全自动

set -e

PROJECT="${1:-$PWD}"
PROJECT=$(realpath "$PROJECT")
SKILL_DIR="$(dirname "$(realpath "$0")")"

if [ ! -d "$PROJECT/.git" ]; then
  echo "🔴 $PROJECT 不是 git 项目, 先 git init"
  exit 1
fi

echo "📦 装注册架构到 $PROJECT"

# 1. 建 _meta + _code 目录
mkdir -p "$PROJECT/_meta/_schema" "$PROJECT/_code/_hooks"

# 2. 复制 schema + CLI + hook
cp "$SKILL_DIR/_registry_entry_v2_schema.yml" "$PROJECT/_meta/_schema/_registry_entry.yml"
cp "$SKILL_DIR/query_registry.py" "$PROJECT/_code/_query_registry.py"
cp "$SKILL_DIR/register.py" "$PROJECT/_code/register.py"  # v8.11 R16 修: 跨项目带 register.py, hook 才能跑 scan
cp "$SKILL_DIR/pre_commit_auto_register.py" "$PROJECT/_code/_hooks/"
cp "$SKILL_DIR/scan_reachability.py" "$PROJECT/_meta/scan_reachability.py"   # 三阶段死代码守护
cp "$SKILL_DIR/run_pipeline.py" "$PROJECT/_code/run_pipeline.py"             # 线执行器 (扣子与线)
mkdir -p "$PROJECT/_pipelines"
cp "$SKILL_DIR/_pipeline.yml.template" "$PROJECT/_pipelines/_pipeline.yml.template"  # manifest 模板
chmod +x "$PROJECT/_code/_query_registry.py" "$PROJECT/_code/_hooks/pre_commit_auto_register.py" "$PROJECT/_meta/scan_reachability.py" "$PROJECT/_code/run_pipeline.py"

# 3. 初始化空 _registry.yml (如果没有)
if [ ! -f "$PROJECT/_meta/_registry.yml" ]; then
  cat > "$PROJECT/_meta/_registry.yml" <<EOF
# 函数注册账本 (单一真源)
# Schema: _meta/_schema/_registry_entry.yml
# 自动维护: pre-commit hook (装在 .git/hooks/)
# 查询: python3 _code/_query_registry.py --report

schema_version: v8.10

# 三阶段入口 — 死代码守护 (_meta/scan_reachability.py) 真源, 每类可多个。
# 不在三阶段调用闭包里的 _code/_pipelines *.py = 死代码 (pre-commit 阻断)。
pre_processing: []
pipeline: []
post_processing: []

functions: []
EOF
fi

# 4. 装 pre-commit hook (自动注册 + 三阶段死代码可达性阻断)
cat > "$PROJECT/.git/hooks/pre-commit" <<'EOF'
#!/bin/bash
ROOT="$(git rev-parse --show-toplevel)"
python3 "$ROOT/_code/_hooks/pre_commit_auto_register.py" 2>&1 || true
# 死代码守护: 有死代码则**真阻断** commit (scan 不存在时跳过, 不挡老项目)。
# 之前这里挂了 `|| true` 等于永不阻断 → DoD 沦为口号; 现改成存在即让退出码生效。
if [ -f "$ROOT/_meta/scan_reachability.py" ]; then
  python3 "$ROOT/_meta/scan_reachability.py" || { echo "🔴 死代码守护阻断 commit (见上)"; exit 1; }
fi
EOF
chmod +x "$PROJECT/.git/hooks/pre-commit"

# 5. 加项目入口 hint: 只写 Claude/Codex 共读的 AGENTS.md
ENTRY_MD="$PROJECT/AGENTS.md"
if [ ! -f "$ENTRY_MD" ]; then
  echo "🟡 未发现 AGENTS.md;请在项目唯一入口就绪后登记 registry 查询命令，现有说明文件未改动。"
fi
if [ -f "$ENTRY_MD" ] && ! grep -q "query_registry.py --report" "$ENTRY_MD"; then
  cat >> "$ENTRY_MD" <<EOF

🔴 cc 进项目第一动作 (强约束)

\`\`\`bash
python3 _code/_query_registry.py --report
\`\`\`

30 秒看完函数总览, 不读 yaml. 详细见 share-top skill \`registry-architecture\`.

## 注册架构 (v8.16 beta)
- cc 进项目第一动作: \`python3 _code/_query_registry.py --report\` 30s 浏览
- 加新 public 函数 commit 时 hook 自动填 why + wired_up_in (无需手填)
EOF
fi

echo "✅ 装好 v9.1. 3 件事自动跑:"
echo "   1. python3 _code/_query_registry.py --report   # cc 进项目用"
echo "   2. .git/hooks/pre-commit                       # 自动补 + git add + rm 检测 (v9.1)"
echo "   3. _meta/_registry.yml                          # 真源, cc 看不写"
echo ""
echo "新加函数 commit 时自动:"
echo "   why=commit message · wired_up_in=commit hash · status: stub → active (有 @consumed_by)"
echo ""
echo "🔴 v9.1 红线 1: 删文件不许 rm, 用 mv _legacy/<date>_<name>/ — pre-commit 真挡"
