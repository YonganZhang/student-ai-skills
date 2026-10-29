#!/usr/bin/env bash
# Install / remove the TOP global git hooks (git config --global core.hooksPath).
#
#   bash install.sh status [--scan <dir>]   # current setting; optionally list repos under <dir>
#                                           #   that have local hooks (kept, chained) or a local
#                                           #   core.hooksPath (overrides the global one: no TOP extras)
#   bash install.sh install [--force]       # refuses when another global hooksPath is set (unless --force;
#                                           #   the previous value is saved and restored by uninstall)
#   bash install.sh uninstall               # only removes the setting if it points here
#
# Respects GIT_CONFIG_GLOBAL (tests use a throwaway file). Never edits any repository.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
state="${TOP_HOOK_STATE:-$HOME/.cache/top-hooks}"
saved="$state/previous-core-hooksPath"
cmd="${1:-status}"
shift || true

current() { git config --global --get core.hooksPath 2>/dev/null || true; }

check_wrappers() {
    local missing=0
    for f in pre-commit prepare-commit-msg commit-msg post-commit pre-push post-merge post-checkout \
             pre-rebase post-rewrite pre-merge-commit _chain.sh; do
        if [ ! -x "$here/$f" ]; then echo "  缺少或不可执行: $here/$f"; missing=1; fi
    done
    return "$missing"
}

scan() {
    local root="$1"
    echo "扫描 $root 下的仓库(深度 3):"
    find "$root" -maxdepth 3 -name .git \( -type d -o -type f \) 2>/dev/null | sort | while read -r gitpath; do
        repo="$(dirname "$gitpath")"
        local_path="$(git -C "$repo" config --local --get core.hooksPath 2>/dev/null || true)"
        common="$(git -C "$repo" rev-parse --git-common-dir 2>/dev/null || true)"
        [ -n "$common" ] && [ "${common#/}" = "$common" ] && common="$repo/$common"
        hooks=""
        if [ -n "$common" ] && [ -d "$common/hooks" ]; then
            hooks="$(find "$common/hooks" -maxdepth 1 -type f -perm -u+x ! -name '*.sample' -printf '%f ' 2>/dev/null || true)"
        fi
        unwrapped=""
        for h in $hooks; do [ -e "$here/$h" ] || unwrapped="$unwrapped $h"; done
        if [ -n "$local_path" ]; then
            echo "  [本地 hooksPath=$local_path,全局 TOP hooks 不生效] $repo"
        elif [ -n "$unwrapped" ]; then
            echo "  [警告: 本地 hook${unwrapped} 没有包装,装全局 hooksPath 后不会再运行] $repo"
        elif [ -n "$hooks" ]; then
            echo "  [本地 hook 会先照常执行: ${hooks% }] $repo"
        fi
    done
}

case "$cmd" in
    status)
        value="$(current)"
        echo "TOP hooks 目录: $here"
        echo "全局 core.hooksPath: ${value:-<未设置>}"
        if [ "$value" = "$here" ]; then echo "状态: 已安装"; else echo "状态: 未安装"; fi
        check_wrappers && echo "包装脚本: 齐全"
        if [ "${1:-}" = "--scan" ] && [ -n "${2:-}" ]; then scan "$2"; fi
        ;;
    install)
        check_wrappers || { echo "包装脚本不完整,拒绝安装" >&2; exit 1; }
        value="$(current)"
        if [ "$value" = "$here" ]; then
            echo "已安装: core.hooksPath=$here(未改动)"
            exit 0
        fi
        if [ -n "$value" ]; then
            if [ "${1:-}" != "--force" ]; then
                echo "拒绝安装: 全局 core.hooksPath 已设为 $value" >&2
                echo "确认要替换(卸载时恢复原值)请加 --force" >&2
                exit 1
            fi
            mkdir -p "$state"
            printf '%s\n' "$value" > "$saved"
            echo "已记录原值 $value → $saved"
        fi
        git config --global core.hooksPath "$here"
        echo "已安装: git config --global core.hooksPath $here"
        echo "复核: $(current)"
        ;;
    uninstall)
        value="$(current)"
        if [ "$value" != "$here" ]; then
            echo "未改动: 全局 core.hooksPath=${value:-<未设置>},不是 TOP hooks 目录" >&2
            exit 1
        fi
        if [ -s "$saved" ]; then
            previous="$(cat "$saved")"
            git config --global core.hooksPath "$previous"
            rm -f "$saved"
            echo "已恢复原值: core.hooksPath=$previous"
        else
            git config --global --unset core.hooksPath
            echo "已卸载: 全局 core.hooksPath 已取消"
        fi
        echo "复核: $(current || true)"
        ;;
    *)
        echo "用法: $0 status [--scan <dir>] | install [--force] | uninstall" >&2
        exit 2
        ;;
esac
