"""Git tracking triage (sixone-cli.py track), .gitignore baselines and plan-complete integration."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from test_plan_git_link import cli, env_for, git, repo_project
from test_sixone_plan_cli import CLI

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
import top_track  # noqa: E402

INIT = SKILL / "scripts" / "init-research.sh"
MB = 1024 * 1024


def make_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "README.md").write_text("# demo\n")
    git(root, "add", "README.md")
    git(root, "commit", "-qm", "init")
    return root


def write(root: Path, rel: str, text: str = "x\n", size: int | None = None) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if size is None:
        path.write_text(text, encoding="utf-8")
    else:
        with path.open("wb") as handle:          # sparse: cheap even at tens of MB
            handle.truncate(size)
    return path


def track(tmp_path: Path, root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(CLI), "track", str(root), *extra], text=True,
                          capture_output=True, timeout=60, env=env_for(tmp_path))


def track_json(tmp_path: Path, root: Path, *extra: str) -> dict:
    result = track(tmp_path, root, *extra)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def by_path(result: dict, action: str) -> dict[str, str]:
    """path -> reason for the samples of one class (tests keep groups small)."""
    return {s: g["reasons"] for g in result["groups"][action] for s in g["sample"]}


@pytest.mark.parametrize("rel,size,expected", [
    (".env", 10, ("ignore", "credential")),
    ("config/.env.local", 10, ("ignore", "credential")),
    (".env.example", 10, ("commit", "authored")),
    ("keys/server.pem", 10, ("ignore", "credential")),
    ("home/id_ed25519.pub", 10, ("ignore", "credential")),
    ("secrets/credentials.json", 10, ("ignore", "credential")),
    ("_wiki-methodology/_top/.env", 10, ("ignore", "credential")),
    (".venv/lib/site.py", 10, ("ignore", "cache")),
    ("src/__pycache__/a.cpython-311.pyc", 10, ("ignore", "cache")),
    ("src/mod.pyc", 10, ("ignore", "cache")),
    ("pkg/demo.egg-info/PKG-INFO", 10, ("ignore", "cache")),
    ("a/b/.DS_Store", 10, ("ignore", "cache")),
    (".julia_depot/packages/X/src/x.jl", 10, ("ignore", "cache")),
    (".packages/numpy/core.py", 10, ("ignore", "cache")),
    ("lib/python3.11/site-packages/x/y.py", 10, ("ignore", "cache")),
    ("experiments/corpus/fulltext-cache/a.pdf", 10, ("ignore", "cache")),
    ("models/hf_cache/x/config.json", 10, ("ignore", "cache")),
    ("svc/cache/entry.json", 10, ("ignore", "cache")),
    ("tool/results.cache", 10, ("ignore", "cache")),
    ("src/cachetools.py", 10, ("commit", "authored")),
    ("_legacy/2026-01-old/run.py", 10, ("review", "legacy")),
    ("_legacy/old/huge.bin", 50 * MB, ("review", "legacy")),
    ("_legacy/old/.env", 10, ("ignore", "credential")),
    ("_wiki-methodology/_top/_legacy/x.md", 10, ("commit", "top-record")),
    ("_tmp/scratch.py", 10, ("ignore", "temp")),
    ("tmp/run.log", 10, ("ignore", "temp")),
    ("src/tmp/keep.py", 10, ("commit", "authored")),            # tmp only at top level
    ("_tests/_artifacts/shot.png", 10, ("ignore", "temp")),
    ("web/e2e/_artifacts/trace.zip", 10, ("ignore", "temp")),
    ("dist/app.js", 10, ("ignore", "temp")),
    ("_wiki-methodology/_top/_findings/f.md", 10, ("commit", "top-record")),
    ("_wiki-methodology/_top/_logs/big.bin", 50 * MB, ("ignore", "large")),       # size before TOP
    ("_wiki-methodology/_top/_logs/run.log", 10, ("commit", "top-record")),
    ("_wiki-methodology/_top/_findings/long.md", 2 * MB, ("review", "large-text")),
    ("_wiki-methodology/_wiki/table.npy", 10, ("commit", "top-record")),
    ("sub/_wiki-methodology/_top/logs/x.md", 10, ("commit", "top-record")),      # beats the "logs" zone
    ("AGENTS.md", 10, ("commit", "top-record")),
    ("_codemap.md", 10, ("commit", "top-record")),
    ("_meta/_data_registry.yml", 10, ("commit", "top-record")),
    ("sub/.gitignore", 10, ("commit", "top-record")),
    ("analysis/fit.py", 10, ("commit", "authored")),
    ("paper/main.tex", 10, ("commit", "authored")),
    ("Makefile", 10, ("commit", "authored")),
    ("notes/huge.txt", 2 * MB, ("review", "large-text")),
    ("_outputs/model.pt", 50 * MB, ("ignore", "generated-binary")),
    ("_outputs/arr.npy", 10, ("ignore", "generated-binary")),
    # generated zone: judged by origin, the extension is only a proxy
    ("_outputs/run1/metrics.json", 10, ("review", "generated-summary")),
    ("results/summary.md", 10, ("review", "generated-summary")),
    ("exp/logs/train.log", 10, ("review", "generated-summary")),
    ("data/raw/table.csv", 10, ("review", "generated-summary")),
    ("wandb/run-1/files/config.yaml", 10, ("review", "recipe-like")),
    ("wandb/run-1/files/metrics.yaml", 10, ("review", "generated-summary")),
    ("checkpoints/ep1/notes.txt", 10, ("review", "generated-summary")),
    ("_outputs/run1/snapshot.py", 10, ("review", "generated-code")),
    ("runs/x/launch.sh", 10, ("review", "generated-code")),
    ("_outputs/run1/weights.npy", 10, ("ignore", "generated-binary")),
    ("_outputs/run1/dump.json", 20 * MB, ("review", "generated-summary")),      # text: no large rule
    ("_outputs/run1/dump.jsonl", 20 * MB, ("ignore", "large")),
    ("tests/fixtures/tiny.npy", 10, ("review", "fixture")),
    ("tests/fixtures/huge.npy", 20 * MB, ("ignore", "large")),
    ("raw/blob.bin", 20 * MB, ("ignore", "large")),
    ("raw/blob.bin", 10, ("review", "other")),
    ("_paper/figs/fig1.pdf", 10, ("commit", "paper-figure")),
    ("figures/fig2.png", 10, ("commit", "paper-figure")),
    ("_outputs/plot.png", 10, ("review", "generated-summary")),
    ("plots/plot.png", 10, ("review", "figure")),
    ("_outputs/huge.png", 20 * MB, ("ignore", "large")),
    ("_outputs/summary.csv", 10, ("review", "generated-summary")),
    ("tables/summary.csv", 10, ("review", "table")),
    ("_outputs/big.csv", 20 * MB, ("ignore", "large")),
    ("vendor/", None, ("review", "nested-repo")),
])
def test_classify_rules(rel: str, size: int | None, expected: tuple[str, str]) -> None:
    calls = []

    def sizer() -> int | None:
        calls.append(rel)
        return size

    action, reason, _ = top_track.classify(rel, sizer)
    assert (action, reason) == expected
    if expected[1] in {"credential", "cache", "temp", "generated-binary", "legacy"}:
        assert not calls                            # stat only when size decides


def test_track_classifies_real_repo_and_suggests_patterns(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write(root, "analysis/fit.py")
    write(root, "论文 草稿/第 1 章.tex")                      # Chinese + spaces survive -z parsing
    write(root, "_wiki-methodology/_top/_findings/f1.md")
    write(root, ".env", "TOKEN=abc\n")
    write(root, "src/__pycache__/a.pyc")
    write(root, "_tmp/scratch.txt")
    write(root, "_tests/_artifacts/shot.png")
    # _outputs/runs: only generated files -> directory rule at the second level
    write(root, "_outputs/runs/a/x.npy")
    write(root, "_outputs/runs/b/y.npy")
    # _outputs/mixed: a small result table stays visible -> extension rule, never the directory
    write(root, "_outputs/mixed/r1/z.npz")
    write(root, "_outputs/mixed/summary.csv")
    write(root, "_outputs/mixed/huge.png", size=20 * MB)
    write(root, "_outputs/mixed/small.png")
    write(root, "notes/huge.txt", "y" * (2 * MB))
    result = track_json(tmp_path, root)
    assert result["schema_version"] == "sixone-track/v1" and result["tool"] == "track"
    assert result["verdict"] == "warn"
    commit = by_path(result, "commit")
    assert {"analysis/fit.py", "论文 草稿/第 1 章.tex", "_wiki-methodology/_top/_findings/f1.md"} <= set(commit)
    review = by_path(result, "review")
    assert {"_outputs/mixed/summary.csv", "_outputs/mixed/small.png", "notes/huge.txt"} <= set(review)
    assert result["counts"] == {"commit": 3, "ignore": 8, "review": 3, "tracked_should_ignore": 0,
                                "ignore_untracked": 8, "generated_summary": 2, "bulk_untracked": 0, "legacy": 0}
    patterns = {s["pattern"]: s["count"] for s in result["gitignore_suggestions"]}
    assert patterns == {
        "/.env": 1, "__pycache__/": 1, "/_tmp/": 1, "/_tests/_artifacts/": 1,
        "/_outputs/runs/": 2,                           # directory level: nothing else below it
        "/_outputs/**/*.npz": 1,                        # extension level: _outputs/mixed has a csv/png
        "/_outputs/mixed/huge.png": 1,                  # large png: small pngs nearby stay visible
    }
    assert "3 份写出来的文件没进 Git" in result["next_hint"]
    assert "--write-gitignore" in result["next_hint"]
    assert git(root, "status", "--porcelain", "--", "README.md") == ""          # read-only
    assert result["tracked_should_ignore"] == []


def test_write_gitignore_is_idempotent_and_keeps_outside_lines(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    (root / ".gitignore").write_text("# mine\n*.log\n\n# >>> top track (auto) >>>\n/manual/\n"
                                     "# <<< top track <<<\n# tail\n")
    git(root, "add", ".gitignore")
    git(root, "commit", "-qm", "gitignore")
    write(root, "_tmp/a.txt")
    write(root, "_outputs/runs/a/x.npy")
    write(root, "keep.py")
    first = track_json(tmp_path, root, "--write-gitignore")
    assert first["gitignore_write"]["written"] == ["/_outputs/runs/", "/_tmp/"]
    text = (root / ".gitignore").read_text()
    assert text == ("# mine\n*.log\n\n# >>> top track (auto) >>>\n/manual/\n/_outputs/runs/\n/_tmp/\n"
                     "# <<< top track <<<\n# tail\n")
    second = track_json(tmp_path, root, "--write-gitignore")
    assert second["gitignore_write"] == {"path": str(root / ".gitignore"), "written": [], "changed": False}
    assert (root / ".gitignore").read_text() == text
    assert second["counts"]["ignore"] == 0
    # nothing was staged, committed or removed
    assert git(root, "diff", "--cached", "--name-only") == ""
    assert git(root, "rev-list", "--count", "HEAD") == "2"
    # a fresh file without a block gets the block appended at the end
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    (fresh / ".gitignore").write_text("a\n")
    top_track.write_gitignore(fresh, ["/b/", "/b/"])
    assert (fresh / ".gitignore").read_text() == "a\n\n# >>> top track (auto) >>>\n/b/\n# <<< top track <<<\n"


def test_tracked_caches_are_reported_not_removed(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    for n in range(3):
        write(root, f".julia_depot/packages/P{n}/src/p.jl")
    write(root, "src/__pycache__/m.cpython-311.pyc")
    write(root, "deploy/.env", "K=v\n")
    write(root, ".env.example", "K=\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "oops")
    result = track_json(tmp_path, root)
    groups = {g["path"]: g for g in result["tracked_should_ignore"]}
    assert result["counts"]["tracked_should_ignore"] == 5
    assert groups[".julia_depot"]["count"] == 3
    assert groups[".julia_depot"]["command"] == "git rm -r --cached -- .julia_depot"
    assert groups["src/__pycache__"]["reason"] == "cache"
    assert "轮换" in groups["deploy/.env"]["note"]
    assert ".env.example" not in groups
    assert len(git(root, "ls-files").splitlines()) == 7                        # nothing removed
    md = track(tmp_path, root, "--markdown")
    assert md.returncode == 0
    assert "## 已追踪但应忽略" in md.stdout and "git rm -r --cached -- .julia_depot" in md.stdout


def test_modified_tracked_files_are_marked_and_renames_parsed(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write(root, "src/old name.py")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "add")
    git(root, "mv", "src/old name.py", "src/新 名字.py")
    (root / "README.md").write_text("# changed\n")
    result = track_json(tmp_path, root)
    commit = {s: g for g in result["groups"]["commit"] for s in g["sample"]}
    assert set(commit) == {"src/新 名字.py", "README.md"}
    assert result["tracked_commit"] == 2 and result["untracked_commit"] == 0
    assert "2 份已追踪文件有改动待提交" in result["next_hint"]


def test_large_threshold_from_git_config_and_errors(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write(root, "raw/blob.bin", size=2 * MB)
    assert track_json(tmp_path, root)["counts"]["review"] == 1
    git(root, "config", "top.trackLargeMB", "1")
    result = track_json(tmp_path, root)
    assert result["counts"]["ignore"] == 1 and result["large_mb"] == 1.0
    git(root, "config", "top.trackLargeMB", "lots")
    bad = track(tmp_path, root)
    assert bad.returncode == 2 and json.loads(bad.stdout)["verdict"] == "error"
    outside = tmp_path / "plain"
    outside.mkdir()
    missing = track(tmp_path, outside)
    assert missing.returncode == 2
    assert json.loads(missing.stdout)["verdict"] == "error"
    md = track(tmp_path, outside, "--markdown")
    assert md.returncode == 2 and "失败" in md.stdout


def test_clean_repo_is_ok(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    result = track_json(tmp_path, root)
    assert result["verdict"] == "ok" and result["gitignore_suggestions"] == []
    assert "干净" in result["next_hint"]


# ---------- init-research.sh --kind ----------

def init(tmp_path: Path, target: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["bash", str(INIT), str(target), *args], text=True, capture_output=True,
                          timeout=60, env=env_for(tmp_path))


@pytest.mark.parametrize("kind", ["research", "dev"])
def test_init_copies_gitignore_template(tmp_path: Path, kind: str) -> None:
    target = tmp_path / "proj"
    args = [] if kind == "research" else ["--kind", kind]
    result = init(tmp_path, target, *args)
    assert result.returncode == 0, result.stderr
    template = SKILL / "templates" / "gitignore" / f"{kind}.gitignore"
    assert (target / ".gitignore").read_text() == template.read_text()


RESEARCH_DIRS = ["_code", "_data", "_figures", "_legacy", "_meta", "_outputs", "_paper", "_refs", "_sandbox", "_tmp"]
DEV_DIRS = ["_legacy", "_meta", "_sandbox", "_tmp"]
V4 = SKILL / "templates" / "v4-architecture"
FIVE_QUESTIONS = ("## 放什么", "## 不放什么", "## 入口", "## 文件角色", "## 改动原因去哪查")


def top_dirs(target: Path) -> list[str]:
    return sorted(p.name for p in target.iterdir() if p.is_dir() and p.name != "_wiki-methodology")


@pytest.mark.parametrize("kind, dirs", [("research", RESEARCH_DIRS), ("dev", DEV_DIRS)])
def test_init_creates_kind_dirs_with_template_readmes(tmp_path: Path, kind: str, dirs: list[str]) -> None:
    target = tmp_path / "proj"
    result = init(tmp_path, target, "--kind", kind)
    assert result.returncode == 0, result.stderr
    assert top_dirs(target) == dirs
    for d in dirs:
        assert (target / d / "_readme.md").read_text() == (V4 / d / "_readme.md").read_text()
        assert [p.name for p in (target / d).iterdir()] == ["_readme.md"]      # no legacy placeholders
    assert ("templates/dir-readme.md" in result.stdout) == (kind == "dev")


def test_init_dirs_never_overwrite_and_bare_with_keeps_layout(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    (target / "_code").mkdir(parents=True)
    (target / "_code" / "_readme.md").write_text("# mine\n")
    (target / "_data").mkdir()
    (target / "_data" / "README.md").write_text("# data\n")          # any README counts as the declaration
    assert init(tmp_path, target, "--kind", "dev").returncode == 0
    assert top_dirs(target) == ["_code", "_data", "_legacy", "_meta", "_sandbox", "_tmp"]
    (target / "_meta" / "_readme.md").write_text("# edited\n")
    snapshot = {p: p.read_bytes() for p in target.rglob("*") if p.is_file() and "_logs" not in p.parts}
    assert init(tmp_path, target, "--with", "codemap").returncode == 0      # existing plan, no --kind
    assert top_dirs(target) == ["_code", "_data", "_legacy", "_meta", "_sandbox", "_tmp"]
    again = init(tmp_path, target, "--kind", "research")                     # explicit kind tops up dirs
    assert again.returncode == 0, again.stderr
    assert top_dirs(target) == RESEARCH_DIRS
    assert (target / "_code" / "_readme.md").read_text() == "# mine\n"
    assert not (target / "_data" / "_readme.md").exists()
    for path, data in snapshot.items():
        if path.name != ".gitignore":
            assert path.read_bytes() == data, path
    files = sorted(p for p in target.rglob("*") if p.is_file())
    assert init(tmp_path, target, "--kind", "research").returncode == 0
    assert sorted(p for p in target.rglob("*") if p.is_file()) == files


def test_dir_readme_templates_answer_the_five_questions() -> None:
    readmes = sorted(V4.glob("_*/_readme.md"))
    assert {p.parent.name for p in readmes} >= set(RESEARCH_DIRS)
    for path in [SKILL / "templates" / "dir-readme.md", *readmes]:
        text = path.read_text(encoding="utf-8")
        assert all(q in text.splitlines() for q in FIVE_QUESTIONS), path
        assert len(text.splitlines()) <= 25, path
        assert "audit.py" not in text, path


def test_init_appends_missing_baseline_rules_idempotently(tmp_path: Path) -> None:
    target = tmp_path / "proj"
    target.mkdir()
    (target / ".gitignore").write_text("# own\n.env\ncustom/\n")
    assert init(tmp_path, target).returncode == 0
    text = (target / ".gitignore").read_text()
    assert text.startswith("# own\n.env\ncustom/\n\n# >>> top baseline (research) >>>\n")
    block = text.split("# >>> top baseline (research) >>>\n", 1)[1].split("# <<< top baseline <<<", 1)[0]
    assert ".env\n" not in block and "/_outputs/**/*.npy\n" in block and "/_tmp/*\n!/_tmp/_readme.md\n" in block
    # plan exists now: a bare re-run is refused, an explicit --kind only tops up the baseline
    assert init(tmp_path, target).returncode == 1
    again = init(tmp_path, target, "--kind", "research")
    assert again.returncode == 0, again.stderr
    assert (target / ".gitignore").read_text() == text
    dev = init(tmp_path, target, "--kind", "dev")
    assert dev.returncode == 0, dev.stderr
    dev_text = (target / ".gitignore").read_text()
    assert dev_text.startswith(text) and "# >>> top baseline (dev) >>>\n" in dev_text
    assert "/dist/" in dev_text.split("# >>> top baseline (dev) >>>", 1)[1]
    assert init(tmp_path, target, "--kind", "dev").returncode == 0
    assert (target / ".gitignore").read_text() == dev_text
    assert init(tmp_path, target, "--kind", "paper").returncode == 1


def test_dev_template_keeps_fixtures_and_research_keeps_small_results(tmp_path: Path) -> None:
    for kind, ignored, kept in [
        ("dev", ["node_modules/x/i.js", "dist/app.js", "_tests/_artifacts/s.png", "w/model.pt", ".env"],
         ["tests/fixtures/tiny.pt", ".env.example", "src/app.ts"]),
        ("research", ["_outputs/run/a.npy", "_data/raw/b.parquet", "_sandbox/e1/outputs/c.txt", "_tmp/t",
                      "x/_artifacts/y.png", ".julia_depot/p"],
         ["_outputs/run/summary.csv", "_outputs/run/fig.png", "_data/README.md", "_sandbox/e1/run.py"]),
    ]:
        root = tmp_path / kind
        root.mkdir()
        git(root, "init", "-q")
        (root / ".gitignore").write_text((SKILL / "templates" / "gitignore" / f"{kind}.gitignore").read_text())
        check = subprocess.run(["git", "-C", str(root), "check-ignore", "--no-index", "--stdin", "-v", "-n"],
                               input="\n".join(ignored + kept) + "\n", text=True, capture_output=True, timeout=30)
        verdict = {}
        for line in check.stdout.splitlines():
            source, path = line.split("\t", 1)
            pattern = source.split(":", 2)[2] if source != "::" else ""
            verdict[path] = bool(pattern) and not pattern.startswith("!")
        assert all(verdict[p] for p in ignored), (kind, verdict)
        assert not any(verdict[p] for p in kept), (kind, verdict)


# ---------- plan complete integration ----------

def test_complete_commits_top_records_and_classifies_leftovers(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    top = root / "_wiki-methodology" / "_top"
    write(top, "_findings/x.md", "finding\n")
    write(top, "_decisions/d.md", "decision\n")
    write(top, ".env", "TOKEN=1\n")                         # never swept in with the TOP directory
    (root / "src" / "a.py").write_text("a = 2\n")
    write(root, "analysis.py", "print(1)\n")
    write(root, "_tmp/scratch.txt")
    write(root, "data.csv", "a,b\n")
    done = cli(tmp_path, "plan", "complete", str(root), "P1.0.E1", "--evidence", "e", "--commit")
    commit = done["git"]["commits"][0]
    assert "error" not in commit, commit
    files = set(git(root, "show", "--name-only", "--format=", "HEAD").splitlines())
    assert {"src/a.py", "_wiki-methodology/_top/_task_plan.md", "_wiki-methodology/_top/_findings/x.md",
            "_wiki-methodology/_top/_decisions/d.md"} <= files
    assert "_wiki-methodology/_top/.env" not in files
    leftover = done["git"]["uncommitted_outside_scope"]
    assert leftover["by_class"] == {"commit": 1, "ignore": 2, "review": 1}
    assert leftover["authored_sample"] == ["analysis.py"]
    assert "sixone-cli.py track" in done["git"]["track_hint"]
    assert "analysis.py" in git(root, "status", "--porcelain")               # hint only, not committed


def test_complete_without_authored_leftovers_has_no_track_hint(tmp_path: Path) -> None:
    root = repo_project(tmp_path)
    write(root, "_tmp/scratch.txt")
    done = cli(tmp_path, "plan", "complete", str(root), "P1.0.E1", "--evidence", "e", "--commit")
    assert done["git"]["uncommitted_outside_scope"]["by_class"] == {"commit": 0, "ignore": 1, "review": 0}
    assert "track_hint" not in done["git"]


def test_plan_files_scope(tmp_path: Path) -> None:
    sys.path.insert(0, str(SKILL / "scripts"))
    import top_plan
    top = tmp_path / "_wiki-methodology" / "_top"
    top.mkdir(parents=True)
    assert top_plan._plan_files(tmp_path, top / "_task_plan.md") == [
        "_wiki-methodology/_top/_task_plan.md", "_wiki-methodology/_top"]
    odd = tmp_path / "docs"
    odd.mkdir()
    assert top_plan._plan_files(tmp_path, odd / "_task_plan.md") == ["docs/_task_plan.md", "docs/logs"]


# ---------- generated zone: bulk vs summary, compact patterns that never hide kept files ----------

def test_generated_bulk_patterns_hide_only_generated_files(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write(root, "_outputs/zoo/tracked.json", "{}\n")
    write(root, "_outputs/zoo/pinned/p.json", "{}\n")
    write(root, "_sandbox/e0/runs/r0/kept.json", "{}\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "tracked results")
    (root / "_outputs/zoo/tracked.json").write_text('{"v": 2}\n')          # tracked zone text, modified
    for i in range(60):
        write(root, f"_outputs/bulkA/r{i % 7}/f{i}.json")                   # nothing kept -> directory
        write(root, f"_outputs/zoo/s{i % 6}/f{i}.json")                     # tracked json next to it
    for n in range(1, 7):
        write(root, f"_sandbox/e{n}/run.py", "print(1)\n")                  # authored -> e{n} is kept
        write(root, f"_sandbox/e{n}/config.json", "{}\n")                  # authored json: no e{n}/**/*.json
        for i in range(50):
            write(root, f"_sandbox/e{n}/runs/r1/f{i}.json")
    write(root, "_sandbox/e0/runs/r0/new.json")                             # summary-level, stays visible
    for i in range(3):
        write(root, f"_outputs/small/s{i}.md")
    write(root, "_outputs/small/copy.py", "x = 1\n")
    result = track_json(tmp_path, root)
    counts = result["counts"]
    assert counts["ignore"] == 60 + 60 + 300 and counts["tracked_should_ignore"] == 0
    review = {s: g["reasons"] for g in result["groups"]["review"] for s in g["sample"]}
    assert "generated-code" in review["_outputs/small/copy.py"]
    assert "generated-summary" in review["_outputs/small/s0.md"]
    assert counts["generated_summary"] == 3 + 1 + 1                           # small/*.md, new.json, tracked.json
    tracked_group = next(g for g in result["groups"]["review"] if g["dir"] == "_outputs/zoo")
    assert tracked_group["tracked"] == 1
    patterns = {s["pattern"]: s for s in result["gitignore_suggestions"]}
    assert set(patterns) == {"/_outputs/bulkA/", "/_outputs/zoo/*/", "/_sandbox/**/runs/"}
    assert patterns["/_outputs/zoo/*/"]["except"] == ["!/_outputs/zoo/pinned/"]
    assert patterns["/_sandbox/**/runs/"]["except"] == ["!/_sandbox/e0/runs/"]
    assert "generated-bulk" in patterns["/_outputs/bulkA/"]["reasons"]
    assert "汇总层可追踪" in result["next_hint"]
    md = track(tmp_path, root, "--markdown")
    assert "!/_sandbox/e0/runs/" in md.stdout
    before = git(root, "ls-files")
    written = track_json(tmp_path, root, "--write-gitignore")["gitignore_write"]["written"]
    assert written.index("!/_sandbox/e0/runs/") == written.index("/_sandbox/**/runs/") + 1
    status = git(root, "status", "--porcelain", "--untracked-files=all").splitlines()
    visible = {line.split()[-1] for line in status}                           # helper strips the 1st column
    assert "_sandbox/e0/runs/r0/new.json" in visible                         # exception works
    assert {f"_sandbox/e{n}/{f}" for n in range(1, 7) for f in ("run.py", "config.json")} <= visible
    assert {"_outputs/small/copy.py", "_outputs/zoo/tracked.json", ".gitignore"} <= visible
    assert not any("/runs/r1/" in p or p.startswith(("_outputs/bulkA/", "_outputs/zoo/s")) for p in visible)
    assert git(root, "ls-files") == before
    again = track_json(tmp_path, root)
    assert again["counts"]["ignore"] == 0 and again["gitignore_suggestions"] == []


def test_generated_summary_under_threshold_and_direct_children_pattern(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write(root, "results/exp/sub/keep.log", "kept\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "kept logs")
    for i in range(49):
        write(root, f"results/few/r{i}.json")
    for i in range(55):
        write(root, f"results/exp/run{i}.log")        # tracked .log below: no dir, no /**/ -> direct *.log
    result = track_json(tmp_path, root)
    assert result["counts"]["review"] == 49 and result["counts"]["ignore"] == 55
    reasons = {r for g in result["groups"]["review"] for r in g["reasons"]}
    assert reasons == {"generated-summary"}
    assert [s["pattern"] for s in result["gitignore_suggestions"]] == ["/results/exp/*.log"]


def test_bulk_untracked_guard_cache_names_legacy_and_large_patterns(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write(root, "raw/keep.md", "kept\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "kept")
    for i in range(201):
        write(root, f"experiments/corpus/p{i}.md")                     # too many to be hand-written
    for i in range(200):
        write(root, f"notes/batch/n{i}.md")                             # exactly at the limit: still authored
    for i in range(250):
        write(root, f"_wiki-methodology/_top/_logs/l{i}.md")            # the TOP directory is exempt
    for i in range(250):
        write(root, f"_wiki-methodology/_wiki/w{i}.md")                 # a bulk wiki tree is not
    write(root, "experiments/corpus/fulltext-cache/a.pdf")
    write(root, "experiments/corpus/fulltext-cache/b.pdf")
    write(root, "_legacy/2026-old/analysis.py")
    write(root, "raw/big1.bin", size=20 * MB)                           # no other .bin kept in raw -> **/*.bin
    write(root, "raw/big2.bin", size=20 * MB)
    write(root, "media/clip.webmx", size=20 * MB)
    write(root, "media/clip.webmx.md", "about the clip\n")
    write(root, "media/sub/small.webmx")                                # review, same ext -> exact path
    result = track_json(tmp_path, root)
    c = result["counts"]
    assert c["bulk_untracked"] == 201 + 250 and c["legacy"] == 1
    assert result["untracked_commit"] == 200 + 250 + 1                 # notes, TOP logs, media/*.md
    review = {r for g in result["groups"]["review"] for r in g["reasons"]}
    assert {"bulk-untracked", "legacy"} <= review
    assert "按来源判断" in result["next_hint"] and "legacy 约定" in result["next_hint"]
    patterns = {s["pattern"]: s["count"] for s in result["gitignore_suggestions"]}
    assert patterns == {
        "/experiments/corpus/fulltext-cache/": 2,                       # name-derived cache: this directory
        "/raw/**/*.bin": 2,
        "/media/clip.webmx": 1,
    }
    shown = {s for g in result["groups"]["review"] for s in g["sample"]}
    assert any(p.startswith("experiments/corpus/p") for p in shown)


def test_temp_dir_readme_and_keep_files_stay_trackable(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write(root, "_tmp/_readme.md", "what goes here\n")
    write(root, "_tests/_artifacts/.gitkeep", "")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "dir notes")
    write(root, "_tmp/scratch.csv")
    write(root, "_tmp/sub/_readme.md", "sub note\n")
    result = track_json(tmp_path, root)
    assert result["counts"]["tracked_should_ignore"] == 0              # tracked notes are not misfiled
    commit = {s for g in result["groups"]["commit"] for s in g["sample"]}
    assert "_tmp/sub/_readme.md" in commit


# ---------- written files inside evidence / output directories are never swept away ----------

def test_artifact_notes_recipes_and_review_files_block_whole_directory_rules(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write(root, "_tests/_artifacts/notes.md", "tracked acceptance note\n")
    write(root, "_tests/_artifacts/old.png")
    write(root, "_tmp/_readme.md", "what _tmp is for\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "evidence")
    write(root, "_tests/_artifacts/shot.png")
    write(root, "_tests/_artifacts/run.log")
    write(root, "_tests/_artifacts/acceptance.md", "# 验收\n")          # written note -> review
    write(root, "web/e2e/_artifacts/check.py", "print(1)\n")           # written script -> review
    write(root, "web/e2e/_artifacts/trace.zip")
    write(root, "_tmp/scratch.txt")
    write(root, "_tmp/deep/x.txt")
    for i in range(60):
        write(root, f"_outputs/pptx/s{i}.json")
    write(root, "_outputs/pptx/deck.tachie_recipe.yml", "steps: []\n")
    write(root, "_outputs/pptx/cover.prompt.txt", "draw a cover\n")
    for i in range(60):
        write(root, f"_outputs/run/r{i % 3}/m{i}.json")
    write(root, "_outputs/run/tool.py", "x = 1\n" * 90000)                # 532KB script: review, must survive
    result = track_json(tmp_path, root)
    review = {s: r for g in result["groups"]["review"] for s in g["sample"] for r in g["reasons"]}
    assert review["_tests/_artifacts/acceptance.md"] == "artifact-note"
    assert review["web/e2e/_artifacts/check.py"] == "artifact-note"
    reasons = {r: n for g in result["groups"]["review"] for r, n in g["reasons"].items()}
    assert reasons["recipe-like"] == 2 and reasons["generated-code"] == 1
    tsi = {g["path"]: g for g in result["tracked_should_ignore"]}
    assert set(tsi) == {"_tests/_artifacts"} and tsi["_tests/_artifacts"]["count"] == 1   # old.png only
    patterns = {s["pattern"]: s.get("except", []) for s in result["gitignore_suggestions"]}
    assert "/_tests/_artifacts/" not in patterns and "/_outputs/run/" not in patterns
    assert "/_outputs/pptx/" not in patterns
    assert patterns["/_tests/_artifacts/*"] == ["!/_tests/_artifacts/acceptance.md", "!/_tests/_artifacts/notes.md"]
    assert patterns["/_tmp/*"] == ["!/_tmp/_readme.md"]
    assert "/_outputs/pptx/**/*.json" in patterns and "/_outputs/run/**/*.json" in patterns
    track_json(tmp_path, root, "--write-gitignore")
    visible = {line.split()[-1] for line in
               git(root, "status", "--porcelain", "--untracked-files=all").splitlines()}
    assert {"_tests/_artifacts/acceptance.md", "web/e2e/_artifacts/check.py", "_outputs/run/tool.py",
            "_outputs/pptx/deck.tachie_recipe.yml", "_outputs/pptx/cover.prompt.txt", ".gitignore"} == visible
    again = track_json(tmp_path, root)
    assert again["counts"]["ignore"] == 0 and again["gitignore_suggestions"] == []


def test_parent_collapse_reincludes_children_with_review_files(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write(root, "_outputs/zoo/c5/keep.json", "{}\n")                    # tracked json: no **/*.json
    git(root, "add", "-A")
    git(root, "commit", "-qm", "keep one json")
    for c in (0, 1, 2, 3, 4, 6):
        for i in range(10):
            write(root, f"_outputs/zoo/c{c}/m{i}.json")
    write(root, "_outputs/zoo/c0/analyse.py", "print(1)\n")             # review (generated-code) in c0
    result = track_json(tmp_path, root)
    patterns = {s["pattern"]: s.get("except", []) for s in result["gitignore_suggestions"]}
    assert patterns == {"/_outputs/zoo/*/": ["!/_outputs/zoo/c0/", "!/_outputs/zoo/c5/"],
                        "/_outputs/zoo/c0/*.json": []}
    track_json(tmp_path, root, "--write-gitignore")
    visible = {line.split()[-1] for line in
               git(root, "status", "--porcelain", "--untracked-files=all").splitlines()}
    assert visible == {"_outputs/zoo/c0/analyse.py", ".gitignore"}


def test_structure_reports_loose_root_files_and_dirs_without_readme(tmp_path: Path) -> None:
    root = make_repo(tmp_path)                                    # README.md at the root is whitelisted
    for name in ("pyproject.toml", "requirements-dev.txt", "tsconfig.base.json", "docker-compose.prod.yml",
                 "LICENSE", "my.code-workspace", ".gitignore", "AGENTS.md"):
        write(root, name)
    write(root, "analysis_v2.py")
    write(root, "notes 草稿.md")
    write(root, "src/a.py")
    write(root, "src/README.md")
    write(root, "_data/raw.md")
    write(root, "_data/_ReadMe.md")                                # case-insensitive
    write(root, "scripts/run.sh")
    write(root, "_paper/main.tex")
    write(root, ".github/workflows/ci.yml")                        # hidden: not a top-level content dir
    write(root, "_wiki-methodology/_top/_task_plan.md")          # TOP tree: documented by share-top
    git(root, "add", "-A")
    git(root, "commit", "-qm", "layout")
    write(root, "stray.csv")                                      # untracked root file
    write(root, "results/x.json")                                 # untracked, dir without README
    write(root, "_sandbox/e1/run.py")                             # untracked inside an _ dir
    (root / "analysis_v2.py").unlink()                            # deleted tracked file is not loose
    st = track_json(tmp_path, root)["structure"]
    assert st["root_loose"] == {"count": 2, "sample": ["notes 草稿.md", "stray.csv"]}
    assert st["dirs_without_readme"] == {"count": 4, "dirs": ["_paper", "_sandbox", "results", "scripts"]}
    assert st["unarchived"] == {"count": 2, "sample": ["results/x.json", "stray.csv"]}
    result = track_json(tmp_path, root)
    assert result["next_hint"].endswith("根目录散落 2 个文件、4 个顶层目录缺 README；"
                                        "未归档 2 个文件（不在 `_` 目录或带 README 的目录里）")
    md = track(tmp_path, root, "--markdown").stdout
    assert "## 目录结构" in md and "`results/`" in md


def test_structure_unarchived_follows_underscore_or_readme_rule(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write(root, "_tmp/keep.txt")                                  # tracked before the dir was ignored
    write(root, "build/out.txt")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "old layout")
    write(root, ".gitignore", "/_tmp/\n/build/\n")
    write(root, "_sandbox/2026-09-24-x/run.py")                   # `_` dir without README: archived
    write(root, "frontend/README.md")                             # README declares the dir (even untracked)
    write(root, "frontend/src/app.ts")
    write(root, "scratch/a.py")                                   # plain dir, no README: unarchived
    write(root, "scratch/b.py")
    write(root, "pyproject.toml")                                 # whitelisted root file
    write(root, "todo.txt")                                       # other root file: unarchived
    write(root, ".github/workflows/ci.yml")                       # hidden config dir
    write(root, "_tmp/new.txt")                                   # ignored: not seen at all
    st = track_json(tmp_path, root)["structure"]
    assert st["unarchived"] == {"count": 3, "sample": ["scratch/a.py", "scratch/b.py", "todo.txt"]}
    # `_` dirs also need a README; dirs ignored as a whole (/_tmp/, /build/) are not asked for one
    assert st["dirs_without_readme"] == {"count": 2, "dirs": ["_sandbox", "scratch"]}
    md = track(tmp_path, root, "--markdown").stdout
    assert "未归档 3 个文件（不在 `_` 目录或带 README 的目录里）" in md and "`todo.txt`" in md


def test_structure_is_quiet_for_a_tidy_repo(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    result = track_json(tmp_path, root)
    assert result["structure"]["root_loose"]["count"] == 0
    assert result["structure"]["dirs_without_readme"]["count"] == 0
    assert result["structure"]["unarchived"]["count"] == 0
    assert "散落" not in result["next_hint"] and "未归档" not in result["next_hint"]


def test_legacy_dir_readme_is_a_note_not_a_legacy_question(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write(root, "_legacy/_readme.md", "what goes here\n")
    write(root, "_legacy/2026-old/analysis.py")
    result = track_json(tmp_path, root)
    commit = {s for g in result["groups"]["commit"] for s in g["sample"]}
    assert "_legacy/_readme.md" in commit
    assert result["counts"]["legacy"] == 1
