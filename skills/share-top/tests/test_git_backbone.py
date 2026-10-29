"""Git as the backbone of TOP: global chain hooks, Decision/Handoff trailers, for-file recall,
edit hints, milestones, and CodeBook retirement."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from test_plan_git_link import GIT_ENV, cli, env_for, git, repo_project
from test_sixone_plan_cli import make_project, payload, plan_log, run_cli

SKILL = Path(__file__).resolve().parents[1]
HOOKS = SKILL / "git-hooks"
EDIT_HINT = SKILL / "scripts" / "top-edit-hint.py"
INIT = SKILL / "scripts" / "init-research.sh"


# ---------- helpers ----------

def hook_env(tmp_path: Path, **extra: str) -> dict[str, str]:
    """Git env whose *global* config is a throwaway file with core.hooksPath = our hooks."""
    gitconfig = tmp_path / "gitconfig"
    if not gitconfig.exists():
        gitconfig.write_text(f"[core]\n\thooksPath = {HOOKS}\n[commit]\n\tgpgsign = false\n")
    env = dict(os.environ, GIT_CEILING_DIRECTORIES=str(tmp_path), GIT_CONFIG_NOSYSTEM="1",
               GIT_CONFIG_GLOBAL=str(gitconfig), TOP_HOOK_STATE=str(tmp_path / "state"), **extra)
    for key, value in GIT_ENV.items():
        if key != "GIT_CONFIG_GLOBAL":
            env[key] = value
    return env


def hgit(tmp_path: Path, root: Path, *args: str, check: bool = True, **extra: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", "-C", str(root), *args], text=True, capture_output=True, timeout=30,
                            env=hook_env(tmp_path, **extra))
    if check:
        assert result.returncode == 0, result.stderr
    return result


def last_message(tmp_path: Path, root: Path) -> str:
    return hgit(tmp_path, root, "log", "-1", "--format=%B").stdout.strip()


def local_hook(root: Path, name: str, body: str) -> None:
    path = root / ".git" / "hooks" / name
    path.write_text("#!/usr/bin/env bash\n" + body)
    path.chmod(0o755)


# ---------- global chain hooks ----------

def test_install_refuses_foreign_setting_and_restores_it(tmp_path: Path) -> None:
    env = dict(os.environ, GIT_CONFIG_GLOBAL=str(tmp_path / "g"), TOP_HOOK_STATE=str(tmp_path / "state"))
    (tmp_path / "g").write_text("[core]\n\thooksPath = /opt/other-hooks\n")
    run = lambda *a: subprocess.run(["bash", str(HOOKS / "install.sh"), *a], text=True,  # noqa: E731
                                    capture_output=True, env=env, timeout=30)
    refused = run("install")
    assert refused.returncode == 1 and "/opt/other-hooks" in refused.stderr
    assert run("install", "--force").returncode == 0
    get = lambda: subprocess.run(["git", "config", "--global", "core.hooksPath"], text=True,  # noqa: E731
                                 capture_output=True, env=env).stdout.strip()
    assert get() == str(HOOKS)
    assert "已安装" in run("status").stdout
    assert run("uninstall").returncode == 0 and get() == "/opt/other-hooks"
    assert run("uninstall").returncode == 1                       # not ours any more: untouched
    (tmp_path / "g").write_text("")
    assert run("install").returncode == 0 and run("uninstall").returncode == 0 and get() == ""
    repos = tmp_path / "repos"
    for name, hook in (("chained", "pre-commit"), ("unwrapped", "reference-transaction")):
        subprocess.run(["git", "init", "-q", str(repos / name)], check=True, env=env)
        local_hook(repos / name, hook, "exit 0\n")
    scan = run("status", "--scan", str(repos)).stdout
    assert "本地 hook 会先照常执行: pre-commit" in scan and "reference-transaction 没有包装" in scan


def test_task_trailer_added_and_local_pre_commit_still_runs_and_blocks(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    marker = tmp_path / "pre-commit-ran"
    local_hook(root, "pre-commit", f'echo ran >> "{marker}"\n[ -e "$(git rev-parse --show-toplevel)/BLOCK" ] && exit 3\nexit 0\n')
    (root / "src" / "a.py").write_text("a = 2\n")
    hgit(tmp_path, root, "commit", "-qam", "work on a")
    assert marker.read_text().count("ran") == 1
    assert last_message(tmp_path, root).endswith("Task: P1.0.E1")
    (root / "BLOCK").write_text("x")
    (root / "src" / "a.py").write_text("a = 3\n")
    blocked = hgit(tmp_path, root, "commit", "-qam", "should be blocked", check=False)
    assert blocked.returncode != 0 and marker.read_text().count("ran") == 2
    assert last_message(tmp_path, root).startswith("work on a")
    (root / "BLOCK").unlink()
    hgit(tmp_path, root, "commit", "-qam", "explicit\n\nTask: P1.0.E0")
    assert last_message(tmp_path, root).count("Task:") == 1          # existing trailer kept, no second one
    off = root / "src" / "b.py"
    off.write_text("b = 5\n")
    hgit(tmp_path, root, "commit", "-qam", "hooks off", TOP_GIT_HOOKS="off")
    assert "Task:" not in last_message(tmp_path, root)
    hgit(tmp_path, root, "commit", "-q", "--amend", "--no-edit")
    assert last_message(tmp_path, root) == "hooks off"                 # amend (source=commit) skipped


def test_merge_commit_is_skipped_and_args_stdin_pass_through(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    seen = tmp_path / "post-rewrite.txt"
    local_hook(root, "post-rewrite", f'echo "args=$*" > "{seen}"\ncat >> "{seen}"\n')
    hgit(tmp_path, root, "checkout", "-qb", "side")
    (root / "side.txt").write_text("s\n")
    hgit(tmp_path, root, "add", "side.txt")
    hgit(tmp_path, root, "commit", "-qm", "side work")
    hgit(tmp_path, root, "checkout", "-q", "main")
    (root / "main.txt").write_text("m\n")
    hgit(tmp_path, root, "add", "main.txt")
    hgit(tmp_path, root, "commit", "-qm", "main work")
    hgit(tmp_path, root, "merge", "-q", "--no-edit", "side")
    assert "Task:" not in last_message(tmp_path, root)
    old = hgit(tmp_path, root, "rev-parse", "HEAD").stdout.strip()
    hgit(tmp_path, root, "commit", "-q", "--amend", "--no-edit")
    new = hgit(tmp_path, root, "rev-parse", "HEAD").stdout.strip()
    text = seen.read_text()
    assert "args=amend" in text and f"{old} {new}" in text


def test_editor_flow_keeps_subject_line_and_empty_message_still_aborts(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    editor = tmp_path / "editor.sh"
    editor.write_text('#!/usr/bin/env bash\nprintf "typed subject%s" "$(cat "$1")" > "$1.new" && mv "$1.new" "$1"\n')
    editor.chmod(0o755)
    (root / "src" / "a.py").write_text("a = 7\n")
    hgit(tmp_path, root, "commit", "-qa", GIT_EDITOR=str(editor))
    lines = last_message(tmp_path, root).splitlines()
    assert lines[0] == "typed subject" and lines[1] == "" and lines[-1] == "Task: P1.0.E1"
    (root / "src" / "a.py").write_text("a = 8\n")
    aborted = hgit(tmp_path, root, "commit", "-qa", check=False, GIT_EDITOR="true")
    assert aborted.returncode != 0 and "empty" in (aborted.stderr + aborted.stdout).lower()


def test_worktrees_use_task_branch_and_repos_without_top_are_untouched(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    hgit(tmp_path, root, "worktree", "add", "-q", "-b", "task/P1.0.E2", str(tmp_path / "wt"), "HEAD")
    (tmp_path / "wt" / "src" / "b.py").write_text("b = 9\n")
    hgit(tmp_path, tmp_path / "wt", "commit", "-qam", "in task worktree")
    assert last_message(tmp_path, tmp_path / "wt").endswith("Task: P1.0.E2")
    hgit(tmp_path, root, "worktree", "add", "-q", "-b", "feature-x", str(tmp_path / "wt2"), "HEAD")
    (tmp_path / "wt2" / "src" / "b.py").write_text("b = 10\n")
    hgit(tmp_path, tmp_path / "wt2", "commit", "-qam", "unrelated worktree")
    assert "Task:" not in last_message(tmp_path, tmp_path / "wt2")   # plan task not guessed in other worktrees

    plain = tmp_path / "plain"
    plain.mkdir()
    hgit(tmp_path, plain, "init", "-q", "-b", "main")
    marker = tmp_path / "plain-hook"
    local_hook(plain, "commit-msg", f'cp "$1" "{marker}"\n')
    (plain / "x.txt").write_text("x\n")
    hgit(tmp_path, plain, "add", "x.txt")
    hgit(tmp_path, plain, "commit", "-qm", "plain commit")
    assert last_message(tmp_path, plain) == "plain commit"
    assert marker.read_text().strip() == "plain commit"               # local commit-msg ran with the message
    assert not (plain / ".codegraph").exists() and sorted(p.name for p in plain.iterdir()) == [".git", "x.txt"]


def test_post_commit_syncs_codegraph_in_background(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    (root / ".codegraph").mkdir()
    (root / ".git" / "info" / "exclude").write_text(".codegraph/\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    called = tmp_path / "codegraph-called"
    fake = bin_dir / "codegraph"
    fake.write_text(f'#!/usr/bin/env bash\necho "$* index=${{GIT_INDEX_FILE:-unset}}" > "{called}"\n')
    fake.chmod(0o755)
    (root / "src" / "a.py").write_text("a = 11\n")
    hgit(tmp_path, root, "commit", "-qm", "partial", "--", "src/a.py",
         PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    for _ in range(50):
        if called.exists():
            break
        time.sleep(0.1)
    assert called.read_text().strip() == f"sync -q {root} index=unset"
    failing = bin_dir / "codegraph"
    failing.write_text("#!/usr/bin/env bash\nexit 1\n")
    (root / "src" / "a.py").write_text("a = 12\n")
    assert hgit(tmp_path, root, "commit", "-qam", "sync fails", check=False,
                PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}").returncode == 0


# ---------- plan complete --decision, record for-file ----------

def add_decision(tmp_path: Path, root: Path, title: str, *extra: str) -> str:
    created = run_cli("record", "add", "decision", str(root), "--title", title, "--summary", "keep it",
                      *extra, env=env_for(tmp_path))
    assert created.returncode == 0, created.stderr
    return payload(created)["path"]


def test_complete_with_decision_commits_trailer_evidence_and_stamps_sha(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    decision = add_decision(tmp_path, root, "Loader keeps float32")    # mentions no file at all
    (root / "src" / "a.py").write_text("a = 20\n")
    (root / "report.txt").write_text("12 passed\n")                    # evidence without a slash
    done = cli(tmp_path, "plan", "complete", str(root), "P1.0.E1", "--evidence", "report.txt",
               "--decision", decision, "--commit")
    commit = done["git"]["commits"][0]
    assert "error" not in commit, commit
    files = set(git(root, "show", "--name-only", "--format=", "HEAD").splitlines())
    assert {"src/a.py", "report.txt", decision} <= files
    message = git(root, "log", "-1", "--format=%B")
    assert "Task: P1.0.E1" in message and f"Decision: {decision}" in message
    log_text = plan_log(root).read_text()
    assert f"dec={decision}" in log_text and f"commit={commit['commit']}" in log_text
    missing = run_cli("plan", "complete", str(root), "P1.0.E2", "--evidence", "x", "--decision", "nope.md",
                      env=env_for(tmp_path))
    assert payload(missing)["verdict"] == "block" and "decision file not found" in payload(missing)["errors"][0]

    found = cli(tmp_path, "record", "for-file", str(root), "src/a.py")
    assert [r["path"] for r in found["records"]] == [decision]
    assert found["records"][0]["commits"] == [commit["commit"]]
    assert "git Decision trailer" in found["records"][0]["matched"] and found["git_checked"] is True


def test_for_file_ranks_code_mentions_symbols_and_reports_supersedes(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    old = add_decision(tmp_path, root, "Average fusion", "--file", "src/b.py::fuse")
    new = add_decision(tmp_path, root, "Masked fusion", "--file", "src/b.py::masked_fuse", "--supersedes", old)
    add_decision(tmp_path, root, "Unrelated export")
    assert "## 涉及代码" in (root / new).read_text()
    result = cli(tmp_path, "record", "for-file", str(root), str(root / "src" / "b.py"), "--symbol", "masked_fuse")
    paths = [r["path"] for r in result["records"]]
    assert paths[0] == new and old in paths and len(paths) == 2
    by_path = {r["path"]: r for r in result["records"]}
    assert by_path[old]["superseded_by"] == [new] and by_path[new]["superseded_by"] is None
    assert "symbol" in by_path[new]["matched"] and "symbol" not in by_path[old]["matched"]
    none = cli(tmp_path, "record", "for-file", str(root), "src/zzz.py")
    assert none["records"] == [] and "不代表没有历史" in none["next_hint"]
    outside = run_cli("record", "for-file", str(root), "/etc/hostname", env=env_for(tmp_path))
    assert outside.returncode == 2


# ---------- edit hint hook ----------

def run_edit_hint(tmp_path: Path, data: dict | str) -> subprocess.CompletedProcess[str]:
    text = data if isinstance(data, str) else json.dumps(data)
    return subprocess.run([sys.executable, str(EDIT_HINT)], input=text, text=True, capture_output=True,
                          timeout=20, env=dict(os.environ, TOP_HOOK_STATE=str(tmp_path / "state"),
                                               GIT_CEILING_DIRECTORIES=str(tmp_path)))


def test_edit_hint_for_claude_and_codex_payloads(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    decision = add_decision(tmp_path, root, "Masked fusion", "--file", "src/b.py::masked_fuse")
    claude = {"session_id": "c1", "cwd": str(root), "hook_event_name": "PreToolUse", "tool_name": "Edit",
              "tool_input": {"file_path": str(root / "src" / "b.py"), "old_string": "b", "new_string": "c"}}
    first = run_edit_hint(tmp_path, claude)
    out = json.loads(first.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse" and "permissionDecision" not in out
    assert "Masked fusion" in out["additionalContext"] and decision in out["additionalContext"]
    assert run_edit_hint(tmp_path, claude).stdout == ""                 # once per file per session
    patch = ("*** Begin Patch\n*** Update File: src/b.py\n@@\n-b = 1\n+b = 2\n"
             "*** Add File: src/new.py\n+x = 1\n*** End Patch\n")
    codex = {"session_id": "x1", "cwd": str(root), "hook_event_name": "PreToolUse", "tool_name": "apply_patch",
             "tool_use_id": "t", "turn_id": "u", "tool_input": {"command": patch}}
    context = json.loads(run_edit_hint(tmp_path, codex).stdout)["hookSpecificOutput"]["additionalContext"]
    assert "src/b.py" in context and "Masked fusion" in context and "new.py" not in context
    for silent in ({**claude, "session_id": "c2", "tool_input": {"file_path": str(root / "src" / "a.py")}},
                   {**claude, "session_id": "c3", "tool_input": {"file_path": str(tmp_path / "elsewhere.py")}},
                   {**claude, "session_id": "c4",
                    "tool_input": {"file_path": str(root / "_wiki-methodology/_top/_task_plan.md")}},
                   {**claude, "session_id": "c5", "tool_name": "Bash", "tool_input": {"command": "ls"}},
                   "not json", ""):
        result = run_edit_hint(tmp_path, silent)
        assert result.returncode == 0 and result.stdout == "", silent


# ---------- plan show from git, handoff, milestone, compact, unrecorded ----------

def test_show_activity_and_handoff_come_from_git(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    cli(tmp_path, "plan", "note", str(root), "halfway there")
    (root / "src" / "a.py").write_text("a = 30\n")
    git(root, "commit", "-qm", "progress on a\n\nTask: P1.0.E1", "--", "src/a.py")
    shown = cli(tmp_path, "plan", "show", str(root))
    assert any(" commit " in row and "progress on a" in row for row in shown["activity"])
    assert any("note:progress P1.0.E1 halfway there" in row for row in shown["activity"])
    assert shown["unrecorded"]["commits"] == 0 and shown["unrecorded"]["task_commits"] == 1
    assert shown["last_handoff"] is None
    doc = root / "_wiki-methodology" / "_top" / "_handoff-20260924-loader.md"
    doc.write_text("# Handoff\n\nNext: finish a.py\n")
    handed = cli(tmp_path, "plan", "handoff", str(root), str(doc.relative_to(root)))
    assert "error" not in handed["git"], handed
    message = git(root, "log", "-1", "--format=%B")
    assert "Handoff: _wiki-methodology/_top/_handoff-20260924-loader.md" in message and "Task: P1.0.E1" in message
    last = cli(tmp_path, "plan", "show", str(root))["last_handoff"]
    assert last["path"].endswith("_handoff-20260924-loader.md") and last["commit"] == handed["git"]["commit"]


def test_milestone_tags_phase_summary_and_never_moves_tags(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    refused = run_cli("plan", "milestone", str(root), "P1.0", env=env_for(tmp_path))
    assert payload(refused)["verdict"] == "block" and "open tasks" in payload(refused)["errors"][0]
    for item in ("P1.0.E1", "P1.0.E2"):
        cli(tmp_path, "plan", "complete", str(root), item, "--evidence", f"ev-{item}", "--commit")
    cli(tmp_path, "plan", "cancel", str(root), "P1.0.M1", "--reason", "not needed")
    cli(tmp_path, "plan", "cancel", str(root), "P1.0.L1", "--reason", "not needed")
    tagged = cli(tmp_path, "plan", "milestone", str(root), "P1.0")
    assert tagged["git"]["tag"] == "top/P1.0" and tagged["done"] == 3 and tagged["cancelled"] == 2
    assert git(root, "cat-file", "-t", "top/P1.0") == "tag"            # annotated
    body = git(root, "tag", "-l", "--format=%(contents)", "top/P1.0")
    assert "P1.0.E1 First active task (ev-P1.0.E1)" in body and "Cancelled (2)" in body
    again = cli(tmp_path, "plan", "milestone", str(root), "P1.0")
    assert again["verdict"] == "warn" and "already exists" in again["git"]["error"]


def test_compact_records_the_commit_holding_the_original(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    plan = root / "_wiki-methodology" / "_top" / "_task_plan.md"
    plan.write_text(plan.read_text() + "\n## 2026-01-01 journal\n\n" + "old notes\n" * 50)
    git(root, "commit", "-qam", "plan with journal")
    head = git(root, "rev-parse", "--short", "HEAD")
    result = cli(tmp_path, "plan", "compact", str(root), "--apply")
    assert result["original_commit"] == head
    assert f"git show {head}:_wiki-methodology/_top/_task_plan.md" in plan.read_text()


# ---------- CodeBook retirement ----------

def test_deposit_is_retired_and_init_no_longer_creates_codebook(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    (root / "_codebook").mkdir()
    node = root / "_codebook" / "a.md"
    node.write_text("---\ntitle: a\n---\n# a\n")
    before = node.read_text()
    result = run_cli("deposit", str(root), "_codebook/a.md")
    assert result.returncode == 0
    body = payload(result)
    assert body["retired"] is True and body["stamped"] is False and "CodeGraph" in body["next_hint"]
    assert node.read_text() == before
    target = tmp_path / "fresh"
    made = subprocess.run(["bash", str(INIT), str(target), "--with", "codemap,codebook"],
                          capture_output=True, text=True, timeout=60)
    assert made.returncode == 0, made.stderr
    assert (target / "_codemap.md").is_file() and not (target / "_codebook").exists()
    assert "已退役" in made.stderr


# ---------- session trailer and staged-content guard ----------

def _plain_repo(tmp_path: Path) -> Path:
    root = tmp_path / "plain"
    root.mkdir()
    hgit(tmp_path, root, "init", "-q")
    (root / "a.txt").write_text("a\n")
    hgit(tmp_path, root, "add", "a.txt")
    hgit(tmp_path, root, "commit", "-qm", "init")
    return root


def test_session_trailer_follows_the_repo_setting(tmp_path: Path) -> None:
    root = _plain_repo(tmp_path)
    sid = "11111111-2222-4333-8444-555555555555"
    (root / "b.txt").write_text("b\n")
    hgit(tmp_path, root, "add", "b.txt")
    hgit(tmp_path, root, "commit", "-qm", "default", CLAUDE_CODE_SESSION_ID=sid)
    assert "Session:" not in last_message(tmp_path, root)  # non-TOP repo, no opt-in
    hgit(tmp_path, root, "config", "top.sessionTrailer", "true")
    (root / "c.txt").write_text("c\n")
    hgit(tmp_path, root, "add", "c.txt")
    hgit(tmp_path, root, "commit", "-qm", "opted in", CLAUDE_CODE_SESSION_ID=sid)
    assert f"Session: claude:{sid}" in last_message(tmp_path, root)
    hgit(tmp_path, root, "config", "top.sessionTrailer", "false")  # public repositories
    (root / "d.txt").write_text("d\n")
    hgit(tmp_path, root, "add", "d.txt")
    hgit(tmp_path, root, "commit", "-qm", "public", CODEX_THREAD_ID=sid)
    assert "Session:" not in last_message(tmp_path, root)


def test_guard_blocks_live_looking_credentials_unless_allowed(tmp_path: Path) -> None:
    root = _plain_repo(tmp_path)
    (root / "cfg.py").write_text('token = "ghp_' + "A" * 36 + '"\n')
    hgit(tmp_path, root, "add", "cfg.py")
    blocked = hgit(tmp_path, root, "commit", "-qm", "leak", check=False)
    assert blocked.returncode != 0 and "GitHub token" in blocked.stderr
    hgit(tmp_path, root, "commit", "-qm", "allowed", TOP_ALLOW_SECRETS="1")
    (root / "placeholder.py").write_text('key = "sk-test-placeholder"\n')  # short placeholders pass
    hgit(tmp_path, root, "add", "placeholder.py")
    hgit(tmp_path, root, "commit", "-qm", "placeholder")


def test_guard_blocks_files_over_the_size_limit(tmp_path: Path) -> None:
    root = _plain_repo(tmp_path)
    hgit(tmp_path, root, "config", "top.maxFileMB", "1")
    (root / "big.bin").write_bytes(b"\0" * (2 * 1024 * 1024))
    hgit(tmp_path, root, "add", "big.bin")
    blocked = hgit(tmp_path, root, "commit", "-qm", "big", check=False)
    assert blocked.returncode != 0 and "big.bin" in blocked.stderr
    hgit(tmp_path, root, "commit", "-qm", "allowed", TOP_ALLOW_LARGE="1")
