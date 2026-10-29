#!/usr/bin/env bash
# TOP global git hooks (installed via `git config --global core.hooksPath <this dir>`).
#
# Every hook name in this directory is a symlink to this script (name = hook).
# 1. Run the repository's own hook first: <git-common-dir>/hooks/<name>, same
#    arguments, same stdin, same exit code. A failing local pre-commit still blocks.
# 2. Then TOP extras, fail-open (never block, never change the exit code):
#    pre-commit          block staged files over 50 MB or live-looking credentials (the only
#                        extra that can block; its own failures fail open)
#    prepare-commit-msg  add `Task: <ID>` for the in-progress TOP task and `Session:` for the
#                        AI conversation (top_githook.py)
#    commit-msg          drop a Task-only message so an emptied editor still aborts
#    post-commit         background `codegraph sync` when the worktree has .codegraph/
# TOP_GIT_HOOKS=off skips step 2. Hooks without extras just `exec` the local hook.

hook="${0##*/}"
if [ "$hook" = "_chain.sh" ]; then  # called as `_chain.sh <hook> args...`
    hook="$1"
    shift
fi

# Fast path without spawning git: git runs hooks from the worktree root (non-bare)
# or from $GIT_DIR (bare). `.git` is a directory (main worktree) or a `gitdir:` file
# (linked worktree / submodule) whose git dir names the shared one in `commondir`.
common=""
if [ -n "${GIT_COMMON_DIR:-}" ]; then
    common="$GIT_COMMON_DIR"
elif [ -d .git ]; then
    common=".git"
elif [ -f .git ]; then
    gitdir="$(sed -n 's/^gitdir: //p' .git 2>/dev/null)"
    if [ -n "$gitdir" ]; then
        case "$gitdir" in /*) ;; *) gitdir="$PWD/$gitdir" ;; esac
        if [ -f "$gitdir/commondir" ]; then
            cd_rel="$(cat "$gitdir/commondir")"
            case "$cd_rel" in /*) common="$cd_rel" ;; *) common="$gitdir/$cd_rel" ;; esac
        else
            common="$gitdir"
        fi
    fi
fi
if [ -z "$common" ] || [ ! -d "$common/objects" ]; then
    common="$(git rev-parse --git-common-dir 2>/dev/null)" || common=""
fi

local_hook=""
if [ -n "$common" ] && [ -f "$common/hooks/$hook" ] && [ -x "$common/hooks/$hook" ]; then
    # never re-enter ourselves if a repository points its hooks dir back here
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
    if [ "$(cd "$common/hooks" 2>/dev/null && pwd -P)" != "$here" ]; then
        local_hook="$common/hooks/$hook"
    fi
fi
here="${here:-$(dirname "${BASH_SOURCE[0]}")}"

case "$hook" in
    pre-commit|prepare-commit-msg|commit-msg|post-commit) ;;
    *)
        if [ -n "$local_hook" ]; then
            exec "$local_hook" "$@"
        fi
        exit 0
        ;;
esac

rc=0
if [ -n "$local_hook" ]; then
    "$local_hook" "$@"
    rc=$?
fi
if [ "$rc" -ne 0 ] && [ "$hook" != "post-commit" ]; then
    exit "$rc"
fi
[ "${TOP_GIT_HOOKS:-on}" = "off" ] && exit "$rc"

limit() {  # run with a time limit when coreutils timeout exists
    if command -v timeout >/dev/null 2>&1; then timeout "$@"; else shift; "$@"; fi
}

run_py() {
    if command -v python3 >/dev/null 2>&1; then
        limit 10 python3 -s "$here/top_githook.py" "$hook" "$@" </dev/null || true
    fi
}

case "$hook" in
    pre-commit)
        if command -v python3 >/dev/null 2>&1; then
            limit 60 python3 -s "$here/top_githook.py" pre-commit </dev/null
            check=$?
            # 3 = something found; crashes (1), timeouts (124) and anything else fail open
            [ "$check" -eq 3 ] && exit 1
        fi
        ;;
    prepare-commit-msg)
        # cheap pre-checks keep non-TOP repos and skipped sources free of a Python start
        case "${2:-}" in merge|squash|commit) exit "$rc" ;; esac
        if [ -f _wiki-methodology/_top/_task_plan.md ] || [ -f wiki-methodology/top/task_plan.md ] \
           || [ "$(git config --bool top.sessionTrailer 2>/dev/null)" = "true" ]; then
            run_py "$@"
        fi
        ;;
    commit-msg)
        # only a message whose sole content is Task: lines needs the guard
        if grep -qi '^task[[:space:]]*:' "$1" 2>/dev/null \
           && ! awk '/^# -+ >8 -+$/{exit} !/^#/ && NF' "$1" | grep -qvi '^task[[:space:]]*:'; then
            run_py "$@"
        fi
        ;;
    post-commit)
        top="$(git rev-parse --show-toplevel 2>/dev/null)" || top=""
        if [ -n "$top" ] && [ -d "$top/.codegraph" ] && command -v codegraph >/dev/null 2>&1; then
            state="${TOP_HOOK_STATE:-$HOME/.cache/top-hooks}"
            mkdir -p "$state" 2>/dev/null || true
            lock="$state/codegraph-$(printf '%s' "$top" | cksum | cut -d' ' -f1).lock"
            (
                # a stale temp index from `git commit <paths>` must not leak into the sync
                unset GIT_INDEX_FILE GIT_DIR GIT_WORK_TREE GIT_PREFIX GIT_COMMON_DIR
                if command -v flock >/dev/null 2>&1; then
                    nohup nice -n 10 flock -n "$lock" timeout 300 codegraph sync -q "$top" >/dev/null 2>&1 &
                else
                    nohup nice -n 10 timeout 300 codegraph sync -q "$top" >/dev/null 2>&1 &
                fi
            ) || true
        fi
        ;;
esac
exit "$rc"
