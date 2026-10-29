#!/usr/bin/env bash
# _scripts/_install_hooks.sh — 一键装 lint armor pre-commit hook
#
# 新节点 clone repo 后跑一次:
#   bash _scripts/_install_hooks.sh
#
# 做的事:
#   1. git config core.hooksPath _scripts/_git_hooks
#      → 让 git 用版控版的 hooks (跨 worktree 生效, 跟代码同步)
#   2. 创 _scripts/_git_hooks/pre-commit → ../_pre_commit_lint.sh symlink
#
# 验证:
#   bash _scripts/_install_hooks.sh
#   git commit --allow-empty -m "test"    # 应跑 lint, errors 时阻 commit

set -e
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

git config core.hooksPath _scripts/_git_hooks
mkdir -p _scripts/_git_hooks

if [ ! -e _scripts/_git_hooks/pre-commit ]; then
    ln -s ../_pre_commit_lint.sh _scripts/_git_hooks/pre-commit
fi

chmod +x _scripts/_pre_commit_lint.sh

echo "✓ Pre-commit hook 已装"
echo "  core.hooksPath = $(git config --get core.hooksPath)"
echo "  pre-commit → $(readlink _scripts/_git_hooks/pre-commit)"
echo ""
echo "下次 git commit 自动跑 _code/lint.py --pre-commit, errors 时 block."
echo "临时跳过 (紧急 fix 用): git commit --no-verify"
