#!/usr/bin/env python3
"""Knowledge tree compatibility: projects without a tree, the old layout, question-and-answer plans,
and a portable copy like the one exported to team kits. The tree changes brief/doctor only when
the project opted in with _meta/_doc_tree.yml."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
PLAN = SCRIPTS / "plan"
DOCTREE_FILES = ("doctree.py", "doctree_model.py", "doctree_summaries.py", "doctree_scan.py", "doctree_check.py",
                 "doctree_render.py", "doctree_place.py")


def run(script: Path, *args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(script), *args], cwd=cwd, env=env, text=True, capture_output=True,
                          check=False, stdin=subprocess.DEVNULL, timeout=60)


def write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def hashes(paths: list[Path]) -> dict[str, str]:
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def tree_yml(wiki: str = "_wiki-methodology") -> str:
    return (f"version: 1\nroot: p\noutput: {{tree: {wiki}/TREE.md, node_dir: {wiki}/_tree, catalog: {wiki}/CATALOG.md}}\n"
            f"scan: {{include: [\"{wiki}/**/*.md\"]}}\n"
            "nodes:\n  - {id: p, title: P}\n  - {id: kb, parent: p, title: 知识库, one_line: 检索与文献}\n")


def v4_project(root: Path) -> None:
    write(root, "_wiki-methodology/_top/_task_plan.md", "# Plan\n\n> **Current: [P1.1] ship**\n")
    write(root, "_wiki-methodology/_wiki/README.md", "# Wiki\n")
    write(root, "_wiki-methodology/_wiki/kb.md", "# 检索\n\n知识库检索的说明文字。\n")


# --------------------------------------------------------------------------- group 1: no tree


def test_without_tree_config_brief_and_doctor_are_unchanged(tmp_path: Path) -> None:
    v4_project(tmp_path)
    brief_text = run(SCRIPTS / "topic-brief.py", str(tmp_path)).stdout
    brief_json = json.loads(run(SCRIPTS / "topic-brief.py", str(tmp_path), "--json").stdout)
    doctor = run(SCRIPTS / "topic-doctor.py", str(tmp_path), "--format", "tsv").stdout
    core = run(SCRIPTS / "topic-doctor.py", str(tmp_path), "--core", "--format", "tsv").stdout
    assert "tree" not in brief_json and "tree:" not in brief_text and "docs ->" not in brief_text
    assert "TREE_" not in doctor and "TREE_" not in core
    # a hand-written TREE.md in a project that did not opt in changes nothing
    write(tmp_path, "_wiki-methodology/TREE.md", "# my own tree notes\n")
    assert json.loads(run(SCRIPTS / "topic-brief.py", str(tmp_path), "--json").stdout) == brief_json
    assert run(SCRIPTS / "topic-brief.py", str(tmp_path)).stdout == brief_text
    assert run(SCRIPTS / "topic-doctor.py", str(tmp_path), "--format", "tsv").stdout == doctor


def test_plan_runs_without_pyyaml_in_a_tree_project(tmp_path: Path) -> None:
    v4_project(tmp_path)
    write(tmp_path, "_meta/_doc_tree.yml", tree_yml())
    bare = subprocess.run([sys.executable, "-S", str(SCRIPTS / "top_plan_cli.py"), "help"], cwd=tmp_path, text=True,
                          capture_output=True, timeout=60, stdin=subprocess.DEVNULL,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    assert bare.returncode == 0, bare.stderr
    no_yaml = subprocess.run([sys.executable, "-S", str(SCRIPTS / "doctree.py"), "check"], cwd=tmp_path, text=True,
                             capture_output=True, timeout=60, stdin=subprocess.DEVNULL)
    if no_yaml.returncode != 0:  # PyYAML lives outside the stdlib path: an environment error, not a crash
        assert no_yaml.returncode == 3 and "PyYAML" in no_yaml.stderr and "Traceback" not in no_yaml.stderr


# --------------------------------------------------------------------------- group 2: old layout


def test_old_layout_uses_configured_paths(tmp_path: Path) -> None:
    write(tmp_path, "wiki-methodology/top/task_plan.md", "# Plan\n\n> **Current: [P2.1] legacy**\n")
    write(tmp_path, "wiki-methodology/wiki/kb.md", "# 检索\n\n知识库检索的说明文字。\n")
    before = run(SCRIPTS / "topic-brief.py", str(tmp_path)).stdout
    assert "tree:" not in before
    write(tmp_path, "_meta/_doc_tree.yml", tree_yml("wiki-methodology"))
    write(tmp_path, "_meta/_doc_summaries.yml", "docs:\n  wiki-methodology/wiki/kb.md:\n    topics: [kb]\n")
    assert run(SCRIPTS / "doctree.py", "build", cwd=tmp_path).returncode == 0
    assert (tmp_path / "wiki-methodology" / "_tree" / "kb.md").is_file()
    assert not (tmp_path / "_wiki-methodology").exists()
    assert "task_plan" not in (tmp_path / "wiki-methodology" / "CATALOG.md").read_text(encoding="utf-8")
    brief = run(SCRIPTS / "topic-brief.py", str(tmp_path)).stdout
    assert "docs -> wiki-methodology/TREE.md" in brief and "entry=wiki-methodology/TREE.md built=yes" in brief
    doctor = run(SCRIPTS / "topic-doctor.py", str(tmp_path), "--format", "tsv")
    assert "TREE_STALE" not in doctor.stdout and "TREE_SUMMARY_MISSING" in doctor.stdout
    write(tmp_path, "wiki-methodology/wiki/kb.md", "# 检索\n\n改过的说明。\n")
    stale = run(SCRIPTS / "topic-doctor.py", str(tmp_path), "--format", "tsv").stdout
    assert "warn\tTREE_STALE" in stale  # strict in `doctree check`, a reminder in the general doctor


# --------------------------------------------------------------------------- group 3: Q&A plan + tree


def test_tree_on_a_question_and_answer_plan_leaves_the_plan_alone(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    env = {**os.environ, "GIT_CEILING_DIRECTORIES": str(tmp_path), "TOP_LOCK_DIR": str(tmp_path / "locks"),
           "TMUX_TMPDIR": str(tmp_path / "no-tmux"), "TOP_PROJECTS_DIR": str(tmp_path)}
    env.pop("TMUX", None)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for args in (["init", "弄清检索为什么要重排"], ["ask", "重排值得上线吗？", "--done-when", "有评测数字"]):
        r = subprocess.run([str(PLAN), *args], cwd=root, env=env, text=True, capture_output=True, timeout=60,
                           stdin=subprocess.DEVNULL)
        assert r.returncode == 0, r.stdout + r.stderr
    top = root / "_wiki-methodology" / "_top"
    plan_files = sorted(p for p in top.rglob("*") if p.is_file())
    assert (top / "_questions" / "Q1.md") in plan_files
    before = hashes(plan_files)
    write(root, "_wiki-methodology/_wiki/kb.md", "# 检索\n\n知识库检索的说明文字。\n")
    write(root, "_meta/_doc_tree.yml", tree_yml())
    write(root, "_meta/_doc_summaries.yml",
          "docs:\n  _wiki-methodology/_wiki/kb.md:\n    topics: [kb]\n    summary: 检索说明。\n    source: reviewed\n")
    assert run(SCRIPTS / "doctree.py", "build", cwd=root).returncode == 0
    assert run(SCRIPTS / "doctree.py", "check", cwd=root).returncode == 0
    assert run(SCRIPTS / "doctree.py", "summaries", "stamp", "_wiki-methodology/_wiki/kb.md", "--write", cwd=root).returncode == 0
    assert hashes(plan_files) == before
    catalog = (root / "_wiki-methodology" / "CATALOG.md").read_text(encoding="utf-8")
    assert "_questions" not in catalog and "_task_plan" not in catalog and "kb.md" in catalog
    check = subprocess.run([str(PLAN), "check"], cwd=root, env=env, text=True, capture_output=True, timeout=60,
                           stdin=subprocess.DEVNULL)
    assert check.returncode == 0, check.stdout + check.stderr
    brief = run(SCRIPTS / "topic-brief.py", str(root)).stdout
    assert "tree: on nodes=2 entry=_wiki-methodology/TREE.md built=yes" in brief


# --------------------------------------------------------------------------- group 4: portable copy (team kit)


def test_portable_copy_runs_without_the_maintainer_home(tmp_path: Path) -> None:
    kit = tmp_path / "kit" / "share-top"
    shutil.copytree(SCRIPTS, kit / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(SKILL / "core", kit / "core", ignore=shutil.ignore_patterns("__pycache__"))
    for name in DOCTREE_FILES:
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        assert "/mnt/" not in text and ".ai-shared" not in text and "Path.home" not in text, name
    proj = tmp_path / "proj"
    v4_project(proj)
    write(proj, "_meta/_doc_tree.yml", tree_yml())
    env = {**os.environ, "HOME": str(tmp_path / "empty-home"), "PYTHONDONTWRITEBYTECODE": "1"}
    build = run(kit / "scripts" / "doctree.py", "build", "--json", cwd=proj, env=env)
    assert build.returncode == 0, build.stderr
    assert json.loads(build.stdout)["written"]
    check = run(kit / "scripts" / "doctree.py", "check", "--json", cwd=proj, env=env)
    assert check.returncode == 0 and json.loads(check.stdout)["verdict"] in ("ok", "warn")
