#!/usr/bin/env bash
# _scripts/_pre_commit_lint.sh — pre-commit hook 跑 lint armor
#
# 安装 (项目根跑一次):
#   ln -sf ../../_scripts/_pre_commit_lint.sh .git/hooks/pre-commit
#
# 行为:
#   - 跑 _code/lint.py --pre-commit
#   - 退出码 2 (有 error) → block commit
#   - 退出码 1 (有 warning) → 不 block 但提醒
#   - 退出码 0 → 静默通过
#
# 跳过 (临时, 紧急 fix 用; 长期违反 = lint 失效):
#   git commit --no-verify

set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

if ! command -v python3 >/dev/null 2>&1; then
    echo "⚠️  python3 不存在, 跳过 lint (装 python3 后生效)"
    exit 0
fi

python3 _code/lint.py --pre-commit
rc=$?

if [ $rc -eq 2 ]; then
    echo ""
    echo "🔴 lint 有 error, commit 被阻止."
    echo "   修后重试, 或临时跳过: git commit --no-verify"
    exit 1
fi

exit 0
