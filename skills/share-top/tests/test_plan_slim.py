"""2026-09-24 slimming: budgets, compact, next, depends_on, gate reminders, lightweight mode, core doctor."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from test_sixone_plan_cli import make_project, no_git_env, plan_log, run_cli

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
sys.path.insert(0, str(SKILL / "core"))   # sixone_core, also importable when this file runs alone
import top_plan  # noqa: E402
from top_common import PlanConflict, parse_plan  # noqa: E402

HINT = SKILL / "scripts" / "top-session-hint.py"
INIT = SKILL / "scripts" / "init-research.sh"


def plan_path(root: Path) -> Path:
    return root / "_wiki-methodology" / "_top" / "_task_plan.md"


def cli_json(*args: str, env: dict[str, str] | None = None) -> tuple[int, dict]:
    result = run_cli(*args, env=env)
    return result.returncode, json.loads(result.stdout)


# ---------- depends_on / next / gate ----------

def test_depends_on_alias_parses_renders_and_gates_start(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    env = no_git_env(tmp_path)
    code, out = cli_json("plan", "add", str(root), "--id", "P1.0.E9", "--title", "Merge",
                         "--depends-on", "P1.0.E1,P1.0.E2", "--gate", "pytest -q tests/test_merge.py", env=env)
    assert code == 0, out
    text = plan_path(root).read_text()
    assert "- [ ] P1.0.E9 Merge · depends_on=P1.0.E1,P1.0.E2 · gate=pytest -q tests/test_merge.py" in text
    item = parse_plan(plan_path(root)).by_id()["P1.0.E9"]
    assert item.deps == ["P1.0.E1", "P1.0.E2"] and item.dep_style == "depends_on"
    # another mutation re-renders every line: the author's depends_on form survives
    assert cli_json("plan", "note", str(root), "hello", env=env)[0] == 0
    assert cli_json("plan", "complete", str(root), "P1.0.E1", "--evidence", "x", env=env)[0] == 0
    assert "depends_on=P1.0.E1,P1.0.E2" in plan_path(root).read_text()
    code, out = cli_json("plan", "start", str(root), "P1.0.E9", env=env)
    assert code == 1 and "dependencies are not closed: P1.0.E2" in out["errors"][0]
    assert cli_json("plan", "validate", str(root), env=env)[1]["verdict"] == "ok"


def test_classic_dep_lines_are_untouched(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    before = plan_path(root).read_text()
    assert cli_json("plan", "complete", str(root), "P1.0.E1", "--evidence", "x",
                    env=no_git_env(tmp_path))[0] == 0
    after = plan_path(root).read_text()
    assert "- [ ] P1.0.E2 Second task · dep=P1.0.E1" in before and "- [ ] P1.0.E2 Second task · dep=P1.0.E1" in after
    assert "depends_on" not in after


def test_plan_next_lists_ready_waiting_and_blocked(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    env = no_git_env(tmp_path)
    cli_json("plan", "add", str(root), "--id", "P1.0.R1", "--title", "Independent", "--gate", "unit green", env=env)
    code, out = cli_json("plan", "next", str(root), env=env)
    assert code == 0 and out["tool"] == "plan-next"
    assert out["current"]["id"] == "P1.0.E1"
    assert [r["id"] for r in out["ready"]] == ["P1.0.R1"]
    assert out["ready"][0]["gates"] == ["unit green"]
    waiting = {w["id"]: w["waiting_on"] for w in out["waiting"]}
    assert waiting["P1.0.E2"] == ["P1.0.E1"] and waiting["P1.0.M1"] == ["P1.0.E2"]
    assert out["blocked"] == ["P1.0.L1"]
    assert "已有进行中任务 P1.0.E1" in out["next_hint"]
    cli_json("plan", "complete", str(root), "P1.0.E1", "--evidence", "x", env=env)
    out = cli_json("plan", "next", str(root), env=env)[1]
    assert [r["id"] for r in out["ready"]] == ["P1.0.E2", "P1.0.R1"]   # plan order
    assert out["next_hint"].endswith("P1.0.E2")


def test_gate_is_shown_and_complete_reminds_without_blocking(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    env = no_git_env(tmp_path)
    cli_json("plan", "edit", str(root), "P1.0.E1", "--add-gate", "pytest -q 全绿", env=env)
    show = cli_json("plan", "show", str(root), "--fast", env=env)[1]
    assert show["current"]["gates"] == ["pytest -q 全绿"]
    assert "验收：pytest -q 全绿" in show["next_hint"]
    code, out = cli_json("plan", "complete", str(root), "P1.0.E1", "--evidence", "_outputs/r.json", env=env)
    assert code == 0 and out["verdict"] == "ok"                    # evidence rule unchanged, not blocked
    assert "pytest -q 全绿" in out["gate_reminder"] and "plan note" in out["gate_reminder"]
    assert parse_plan(plan_path(root)).by_id()["P1.0.E1"].state == "done"
    # evidence that cites the gate -> no reminder
    cli_json("plan", "add", str(root), "--id", "P1.0.G1", "--title", "Gated", "--gate", "test:g1", env=env)
    out = cli_json("plan", "complete", str(root), "P1.0.G1", "--evidence", "test:g1", env=env)[1]
    assert "gate_reminder" not in out


def test_add_rejects_metadata_delimiter_in_gate(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    before = plan_path(root).read_text()
    code, out = cli_json("plan", "add", str(root), "--id", "P1.0.X1", "--title", "Bad",
                         "--gate", "a · b", env=no_git_env(tmp_path))
    assert code == 1 and "gate values" in out["errors"][0]
    assert plan_path(root).read_text() == before


# ---------- budgets ----------

def test_validate_budget_warnings_do_not_block(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    env = no_git_env(tmp_path)
    long_scope = "path:" + "a" * 600
    cli_json("plan", "add", str(root), "--id", "P1.0.B1", "--title", "Big", "--scope", long_scope, env=env)
    path = plan_path(root)
    path.write_text(path.read_text() + "\n## 2026-01-01 Diary\n\n" + ("流水账 " * 6000) + "\n")
    code, out = cli_json("plan", "validate", str(root), env=env)
    codes = {w["code"] for w in out["warnings"]}
    assert code == 0 and out["verdict"] == "warn" and not out["errors"]
    assert {"PLAN_OVER_BUDGET", "PLAN_TASK_LINE_LONG", "PLAN_SCOPE_LONG"} <= codes
    assert all(w["hint"] for w in out["warnings"])
    assert "plan compact" in next(w["hint"] for w in out["warnings"] if w["code"] == "PLAN_OVER_BUDGET")


def test_long_note_is_written_but_warned(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    env = no_git_env(tmp_path)
    code, out = cli_json("plan", "note", str(root), "长" * 320, env=env)
    assert code == 0 and out["verdict"] == "warn" and "320 字" in out["warnings"][0]
    assert "长" * 320 in plan_log(root).read_text()
    warnings = cli_json("plan", "validate", str(root), env=env)[1]["warnings"]
    assert any(w["code"] == "PLAN_NOTE_LONG" for w in warnings)


# ---------- compact ----------

JOURNAL_PLAN = """# Demo · Task Plan

🧭 当前 [P1.0] task=[P1.0.E1] First active task
> Done Criteria: finish the controlled plan lifecycle

## Current Coordinate

- Goal: test plan control
- Current task: P1.0.E1
- Next task: P1.0.E2
- Latest learning: none
- Blocker: none

## Active Work

- [x] P1.0.E0 Bootstrap · ev=_tests/bootstrap.txt
- [ ] P1.0.E1 First active task · state=in_progress · dep=P1.0.E0
- [ ] P1.0.E2 Second task · dep=P1.0.E1

### 2026-09-01 旧的小节流水

- 做了很多事

### 2026-09-02 带任务的小节

- [ ] P1.0.E3 Nested task · dep=P1.0.E2

## 当前路线说明

短说明，保留。

## 2026-08-01 周报

- 很长的流水 A

## 历史 Done Criteria

- 旧门槛

## Big undated notes

{big}
"""


def make_journal_project(tmp_path: Path) -> Path:
    root = make_project(tmp_path)
    plan_path(root).write_text(JOURNAL_PLAN.replace("{big}", "说明 " * 1500), encoding="utf-8")
    return root


def test_compact_dry_run_writes_nothing(tmp_path: Path) -> None:
    root = make_journal_project(tmp_path)
    before = plan_path(root).read_text()
    code, out = cli_json("plan", "compact", str(root), env=no_git_env(tmp_path))
    assert code == 0 and out["apply"] is False
    titles = [m["title"] for m in out["moved"]]
    assert titles == ["2026-09-01 旧的小节流水", "2026-08-01 周报", "历史 Done Criteria", "Big undated notes"]
    assert out["bytes_after"] < out["bytes_before"]
    assert plan_path(root).read_text() == before
    assert not (root / "_wiki-methodology" / "_top" / "_logs").exists()


def test_compact_apply_moves_verbatim_keeps_plan_semantics_and_is_idempotent(tmp_path: Path) -> None:
    root = make_journal_project(tmp_path)
    env = no_git_env(tmp_path)
    before_state = parse_plan(plan_path(root))
    before_show = cli_json("plan", "show", str(root), "--fast", env=env)[1]
    code, out = cli_json("plan", "compact", str(root), "--apply", env=env)
    assert code == 0 and out["verdict"] == "ok" and len(out["moved"]) == 4
    text = plan_path(root).read_text()
    archive = Path(out["archive_file"])
    assert archive.name == f"{datetime.now():%Y-%m-%d}-journal-archive.md"
    moved = archive.read_text()
    for kept in ("## Current Coordinate", "P1.0.E3 Nested task", "### 2026-09-02 带任务的小节", "## 当前路线说明"):
        assert kept in text
    for gone in ("旧的小节流水", "很长的流水 A", "旧门槛", "Big undated notes"):
        assert gone not in text.split("## 历史索引")[0] and gone in moved
    assert "## 历史索引（plan compact 移出，原文在 _logs）" in text and f"`_logs/{archive.name}`" in text
    after_state = parse_plan(plan_path(root))
    assert [i.id for i in after_state.items] == [i.id for i in before_state.items]
    after_show = cli_json("plan", "show", str(root), "--fast", env=env)[1]
    for key in ("phase_id", "goal", "current", "next", "counts", "errors"):
        assert after_show[key] == before_show[key]
    assert "compact plan" in plan_log(root).read_text()
    # second run: nothing left to move, index untouched
    again = cli_json("plan", "compact", str(root), "--apply", env=env)[1]
    assert again["moved"] == [] and plan_path(root).read_text() == text
    # plan commands still work after compaction
    assert cli_json("plan", "complete", str(root), "P1.0.E1", "--evidence", "x", env=env)[0] == 0


def test_compact_moves_long_preamble_but_keeps_stamp_and_done_criteria(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    path = plan_path(root)
    text = path.read_text().replace(
        "> Done Criteria: finish the controlled plan lifecycle\n",
        "> Done Criteria: finish the controlled plan lifecycle\n> second criteria line\n>\n"
        + "".join(f"> 历史快照 {n}: " + "细节" * 60 + "\n" for n in range(20)))
    path.write_text(text)
    out = top_plan.compact(str(root), apply=True)
    new = path.read_text()
    assert out["moved"][0]["reason"] == "preamble"
    assert "🧭 当前 [P1.0] task=[P1.0.E1] First active task" in new
    assert "> Done Criteria: finish the controlled plan lifecycle\n> second criteria line" in new
    assert "历史快照 3" not in new and "历史快照 3" in Path(out["archive_file"]).read_text()


def test_compact_conflict_rolls_back_archive(tmp_path: Path, monkeypatch) -> None:
    root = make_journal_project(tmp_path)
    before = plan_path(root).read_text()

    def conflict(*_args, **_kwargs):
        raise PlanConflict("task plan changed concurrently; reread and retry")

    monkeypatch.setattr(top_plan, "atomic_replace_plan", conflict)
    try:
        top_plan.compact(str(root), apply=True)
    except PlanConflict:
        pass
    else:
        raise AssertionError("expected PlanConflict")
    assert plan_path(root).read_text() == before
    logs = root / "_wiki-methodology" / "_top" / "_logs"
    assert not list(logs.glob("*-journal-archive.md"))
    assert not list((logs / "plan-history").glob("*-before-compact.md"))
    assert not (root / "_wiki-methodology" / "_top" / "_task_plan.before-compact.md").is_symlink()


def test_compact_keeps_the_full_original_behind_a_stable_symlink(tmp_path: Path) -> None:
    root = make_journal_project(tmp_path)
    env = no_git_env(tmp_path)
    original = plan_path(root).read_text()
    out = cli_json("plan", "compact", str(root), "--apply", env=env)[1]
    top = root / "_wiki-methodology" / "_top"
    link = top / "_task_plan.before-compact.md"
    snapshot = Path(out["original_snapshot"])
    assert snapshot.parent == top / "_logs" / "plan-history" and snapshot.read_text() == original
    assert link.is_symlink() and not Path(link.readlink()).is_absolute() and link.resolve() == snapshot.resolve()
    assert "`_task_plan.before-compact.md`" in plan_path(root).read_text()  # the slim plan points at the original
    show = cli_json("plan", "show", str(root), "--fast", env=env)[1]
    assert show["before_compact"] == "_wiki-methodology/_top/_task_plan.before-compact.md"


def test_compact_refuses_when_parse_would_change(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    path = plan_path(root)
    # a dated section that holds the only Done Criteria line inside the head window
    text = path.read_text().replace("> Done Criteria: finish the controlled plan lifecycle\n", "")
    text = text.replace("## Current Coordinate", "## 2026-01-01 old\n\nDone Criteria: legacy gate\n\n## Current Coordinate")
    path.write_text(text)
    code, out = cli_json("plan", "compact", str(root), "--apply", env=no_git_env(tmp_path))
    assert code == 1 and "拒绝" in out["errors"][0]
    assert path.read_text() == text


def test_compact_leaves_lightweight_plan_alone(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    path = plan_path(root)
    path.write_text("# Old plan\n\n## 2026-01-01 diary\n\n- stuff\n")
    code, out = cli_json("plan", "compact", str(root), "--apply", env=no_git_env(tmp_path))
    assert code == 0 and out["lightweight"] is True and out["moved"] == []
    assert path.read_text() == "# Old plan\n\n## 2026-01-01 diary\n\n- stuff\n"


# ---------- lightweight mode + hints ----------

def run_hint(cwd: Path, event: str = "SessionStart", session: str = "", state: Path | None = None):
    env = dict(os.environ, TOP_HOOK_STATE=str(state or cwd.parent / "hookstate"))
    data = json.dumps({"cwd": str(cwd), "hook_event_name": event, "session_id": session})
    return subprocess.run([sys.executable, str(HINT)], input=data, text=True, env=env,
                          capture_output=True, timeout=20, cwd=str(cwd))


def test_hint_suggests_compact_for_oversized_plan(tmp_path: Path) -> None:
    root = make_journal_project(tmp_path)
    path = plan_path(root)
    path.write_text(path.read_text() + "\n## 2026-02-02 more\n\n" + "x" * 31_000 + "\n")
    out = run_hint(root).stdout
    assert "计划过大" in out and "plan compact" in out


def test_lightweight_plan_gets_no_maintenance_demands(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    plan_path(root).write_text("# Notes\n\n🧭 当前 [P0] 休眠\n\nsome free text\n")
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
    state = tmp_path / "state"
    start = run_hint(root, "SessionStart", "lw", state).stdout
    assert "轻量模式" in start and "冲突" not in start
    (root / "work.py").write_text("x = 1\n")
    assert run_hint(root, "Stop", "lw", state).stdout == ""        # no closeout reminder
    doctor = json.loads(run_cli("doctor", str(root)).stdout)
    codes = {i["code"]: i["severity"] for i in doctor["issues"]}
    assert codes.get("PLAN_LIGHTWEIGHT") == "info"
    assert doctor["verdict"] == "ok"


def test_empty_active_work_is_lightweight_in_hint(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    plan_path(root).write_text(
        "# P\n\n🧭 当前 [P0.1] task=[none] idle\n\n## Current Coordinate\n\n- Goal: g\n- Current task: none\n"
        "- Next task: none\n- Latest learning: none\n- Blocker: none\n\n## Active Work\n\n")
    assert "轻量模式" in run_hint(root).stdout


# ---------- core doctor ----------

def test_core_doctor_checks_only_links_registry_paths_plan_and_unrecorded(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    (root / "AGENTS.md").write_text("# A\n\n- [plan](_wiki-methodology/_top/_task_plan.md)\n- [gone](docs/missing.md)\n")
    (root / "_meta").mkdir()
    (root / "_meta" / "_registry.yml").write_text("entrypoints:\n  - id: foo\n    path: src/missing.py\n")
    (root / "orphan.png").write_bytes(b"png")                    # full-mode ROOT_CLUTTER must not appear
    doctor = json.loads(run_cli("doctor", str(root), env=no_git_env(tmp_path)).stdout)
    codes = {i["code"] for i in doctor["issues"]}
    assert "DEAD_LINK" in codes and "REGISTRY_PATH_MISSING" in codes
    assert not codes & {"ROOT_CLUTTER", "WIKI_MISSING", "TESTS_MISSING", "DATA_REGISTRY_MISSING", "STATE_DRIFT"}
    dead = next(i for i in doctor["issues"] if i["code"] == "DEAD_LINK")
    assert dead["path"] == "AGENTS.md:4" and "docs/missing.md" in dead["message"]
    full = json.loads(run_cli("doctor", str(root), "--full", env=no_git_env(tmp_path)).stdout)
    assert "ROOT_CLUTTER" in {i["code"] for i in full["issues"]}


def test_core_doctor_reports_unrecorded_commits(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    git = ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "init"], check=True)
    (root / "work.py").write_text("x = 1\n")
    subprocess.run([*git, "add", "work.py"], check=True)
    subprocess.run([*git, "commit", "-qm", "work"], check=True)
    doctor = json.loads(run_cli("doctor", str(root)).stdout)
    issue = next(i for i in doctor["issues"] if i["code"] == "UNRECORDED_COMMITS")
    # context only since 2026-10-16: short or unrelated work does not belong in the plan
    assert issue["severity"] == "info" and "1 commits" in issue["message"]


# ---------- init ----------

def test_init_creates_only_required_parts_then_optional_modules(tmp_path: Path) -> None:
    target = tmp_path / "newproj"
    result = subprocess.run(["bash", str(INIT), str(target)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    files = sorted(str(p.relative_to(target)) for p in target.rglob("*") if p.is_file())
    research_dirs = ["_code", "_data", "_figures", "_legacy", "_meta", "_outputs", "_paper", "_refs", "_sandbox", "_tmp"]
    assert files == sorted([".gitignore", "AGENTS.md", "_wiki-methodology/_top/_logs/_readme.md",
                            "_wiki-methodology/_top/_task_plan.md",
                            *(f"{d}/_readme.md" for d in research_dirs)])  # research baseline + dirs
    assert len((target / "AGENTS.md").read_text().splitlines()) <= 60
    assert not (target / "CLAUDE.md").exists()
    assert "verdict=ok" in result.stdout
    again = subprocess.run(["bash", str(INIT), str(target)], capture_output=True, text=True, timeout=60)
    assert again.returncode == 1
    (target / "AGENTS.md").write_text("# mine\n")
    more = subprocess.run(["bash", str(INIT), str(target), "--with", "codemap,decisions"],
                          capture_output=True, text=True, timeout=60)
    assert more.returncode == 0, more.stderr
    assert (target / "_codemap.md").is_file() and (target / "_wiki-methodology/_top/_decisions").is_dir()
    assert (target / "AGENTS.md").read_text() == "# mine\n"            # never overwrites
    assert not (target / "CLAUDE.md").exists()
    for skeleton in ("_phases", "_external_reviews", "_six_dim_contract.md"):
        assert not (target / "_wiki-methodology" / "_top" / skeleton).exists()
    assert not (target / "_meta" / "_registry.yml").exists()
    bad = subprocess.run(["bash", str(INIT), str(target), "--with", "roadmap"], capture_output=True, text=True)
    assert bad.returncode == 1 and "未知模块" in bad.stderr


def test_core_doctor_ignores_history_refs_but_flags_live_ones(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    path = plan_path(root)
    path.write_text(path.read_text()
                    .replace("ev=_tests/bootstrap.txt", "ev=test:renamed-long-ago")
                    .replace("- [ ] P1.0.E2 Second task · dep=P1.0.E1", "- [ ] P1.0.E2 Second task · dep=P1.0.E1 · gate=test:missing-gate"))
    logs = root / "_wiki-methodology" / "_top" / "_logs"
    logs.mkdir()
    (logs / "2026-01-01.md").write_text("- used test:old-gate back then\n")
    core = json.loads(run_cli("doctor", str(root), env=no_git_env(tmp_path)).stdout)
    dangling = [i["message"] for i in core["issues"] if i["code"] == "REF_DANGLING"]
    assert dangling == ["test:missing-gate is not declared by its owner"]
    full = json.loads(run_cli("doctor", str(root), "--full", env=no_git_env(tmp_path)).stdout)
    assert len([i for i in full["issues"] if i["code"] == "REF_DANGLING"]) == 3


def test_default_doctor_skips_codebook_and_pipeline_stamps(tmp_path: Path) -> None:
    """机主决定（2026-09-24）：CodeBook 新鲜度与 pipeline 印记只在 --full 时检查。"""
    import sixone_core as core
    root = make_project(tmp_path)
    (root / "_codebook").mkdir()
    (root / "_codebook" / "a.md").write_text("---\ntracked: [missing.py]\n---\n# a\n")
    result = core.topic_doctor(str(root))
    assert result["codebook"] == {"skipped": "only with --full"}
    assert result["pipelines"] == {"skipped": "only with --full"}
