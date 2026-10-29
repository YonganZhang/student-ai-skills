#!/usr/bin/env python3
"""Knowledge tree hardening (post-implementation review): stamp writes, error contract, path bounds,
output collisions, runnable reference examples, relocated output, new-node parent."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import doctree  # noqa: E402
import doctree_summaries  # noqa: E402
from test_doctree import ANCHOR, LOGIN, RERANK, TREE_YML, W, as_json, codes, make_project, sha, snapshot, write  # noqa: E402


def run(root: Path, *args: str, script: str = "doctree.py") -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args], cwd=root, text=True, capture_output=True,
                          check=False, stdin=subprocess.DEVNULL, timeout=60)


def table_text(root: Path) -> str:
    return (root / "_meta" / "_doc_summaries.yml").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- stamp: concurrency and targeted edits


def test_stamp_does_not_lose_a_write_made_after_its_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_project(tmp_path)
    summaries = {LOGIN: {"topics": ["auth"], "summary": "登录。", "source": "auto"},
                 RERANK: {"topics": ["kb"], "summary": "重排。", "source": "auto"}}
    lines = ["version: 1", "docs:"] + [f"  {p}:\n" + "\n".join(f"    {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in e.items())
                                       for p, e in summaries.items()]
    write(tmp_path, "_meta/_doc_summaries.yml", "\n".join(lines) + "\n")
    original = doctree.context

    def racing_context(args):  # another writer finishes between this call's parse and its write
        result = original(args)
        other = run(tmp_path, "summaries", "stamp", RERANK, "--write")
        assert other.returncode == 0, other.stderr
        return result

    monkeypatch.setattr(doctree, "context", racing_context)
    monkeypatch.chdir(tmp_path)
    assert doctree.main(["summaries", "stamp", LOGIN, "--write"]) == 0
    entries = doctree_summaries.load_summaries(tmp_path / "_meta" / "_doc_summaries.yml")
    assert entries[LOGIN].source == "reviewed" and entries[RERANK].source == "reviewed"


def test_parallel_stamps_all_land(tmp_path: Path) -> None:
    make_project(tmp_path)
    docs = [f"{W}/_wiki/d{i}.md" for i in range(6)]
    for i, d in enumerate(docs):
        write(tmp_path, d, f"# D{i}\n\n第 {i} 篇。\n")
    write(tmp_path, "_meta/_doc_summaries.yml", "version: 1\ndocs:\n" + "".join(
        f"  {d}:\n    topics: [kb]\n    summary: 第{i}篇。\n    source: auto\n" for i, d in enumerate(docs)))
    procs = [subprocess.Popen([sys.executable, str(SCRIPTS / "doctree.py"), "summaries", "stamp", d, "--write"],
                              cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for d in docs]
    results = [(p.wait(timeout=60), p.stderr.read()) for p in procs]
    assert all(code == 0 for code, _ in results), results
    entries = doctree_summaries.load_summaries(tmp_path / "_meta" / "_doc_summaries.yml")
    assert all(entries[d].source == "reviewed" and entries[d].reviewed_sha == sha(tmp_path, d) for d in docs)


def test_stamp_changes_only_the_target_entry(tmp_path: Path) -> None:
    make_project(tmp_path)
    other = f"{W}/_wiki/other.md"
    flow = f"{W}/_wiki/flow.md"
    write(tmp_path, other, "# O\n\n其他。\n")
    write(tmp_path, flow, "# F\n\n流式。\n")
    before = ("# 头部说明\nversion: 1\ndocs:\n"
              f"  # --- 账号 ---\n  {LOGIN}:\n    topics: [auth]   # 主归属\n    summary: \"登录页。\"\n    source: auto\n"
              f"  {other}: [invalid, shape]\n"
              f"  {flow}: {{topics: [kb], summary: 流式条目, source: auto}}\n"
              "  # 文末注释\n")
    write(tmp_path, "_meta/_doc_summaries.yml", before)
    r = run(tmp_path, "summaries", "stamp", LOGIN, "--write", "--json")
    assert r.returncode == 0, r.stdout + r.stderr
    after = table_text(tmp_path)
    expected = before.replace("    source: auto\n", f"    source: reviewed\n    reviewed_sha: '{sha(tmp_path, LOGIN)}'\n", 1)
    assert after == expected
    refused = run(tmp_path, "summaries", "stamp", flow, "--write", "--json")  # flow style: edit by hand
    assert refused.returncode == 1 and table_text(tmp_path) == after
    bad = run(tmp_path, "summaries", "stamp", other, "--write", "--json")  # malformed entry: never "repaired"
    assert bad.returncode == 1 and table_text(tmp_path) == after
    assert as_json(bad)["failed"][0]["path"] == other


def test_stamp_replaces_existing_values_in_place(tmp_path: Path) -> None:
    make_project(tmp_path)  # LOGIN has source: reviewed and a current reviewed_sha
    write(tmp_path, LOGIN, "# 登录页\n\n改了一句。\n")
    before = table_text(tmp_path)
    assert run(tmp_path, "summaries", "stamp", LOGIN, "--write").returncode == 0
    after = table_text(tmp_path)
    assert len(after.splitlines()) == len(before.splitlines())
    assert f"reviewed_sha: \"{sha(tmp_path, LOGIN)}\"" in after or f"reviewed_sha: '{sha(tmp_path, LOGIN)}'" in after
    assert ("warn", "SUMMARY_STALE", LOGIN) not in codes(tmp_path)


def test_stamp_detects_an_outside_edit_and_exits_3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_project(tmp_path)
    write(tmp_path, LOGIN, "# 登录页\n\n改了一句。\n")
    table = tmp_path / "_meta" / "_doc_summaries.yml"
    original = doctree_summaries.stamp_text

    def editor_saves_meanwhile(text, targets, path):
        table.write_text(text + "# 编辑器存盘\n", encoding="utf-8")
        return original(text, targets, path)

    monkeypatch.setattr(doctree_summaries, "stamp_text", editor_saves_meanwhile)
    monkeypatch.chdir(tmp_path)
    assert doctree.main(["summaries", "stamp", LOGIN, "--write"]) == 3
    assert table.read_text(encoding="utf-8").endswith("# 编辑器存盘\n")


# --------------------------------------------------------------------------- error contract


@pytest.mark.parametrize("patch", [
    "mounts: 4", "columns: 4", "mounts: [{glob: 3, topics: [kb]}]", "columns: [{label: X}]", "columns: [{label: [X], glob: a}]",
    "output: {tree: [x]}", "root: [proj]", "nodes: [{id: proj, title: P, parent: [x]}]",
    "scan: {include: 5}", "coverage: {a: 1}", "summary_sections: 7",
    "place: {variant: magic}", "place: {stopwords: [a]}",
])
def test_wrong_types_in_valid_yaml_are_config_errors(tmp_path: Path, patch: str) -> None:
    make_project(tmp_path)
    # a repeated top-level key replaces the earlier one (last wins in PyYAML)
    (tmp_path / "_meta" / "_doc_tree.yml").write_text(TREE_YML + patch + "\n", encoding="utf-8")
    r = run(tmp_path, "check", "--json")
    assert r.returncode == 2, r.stdout + r.stderr
    assert as_json(r)["error"]["kind"] == "config" and "Traceback" not in r.stderr
    doctor = run(tmp_path, str(tmp_path), "--format", "tsv", script="topic-doctor.py")
    assert "Traceback" not in doctor.stderr and "block\tTREE_CONFIG_ERROR" in doctor.stdout


def test_node_fields_with_wrong_types_are_config_errors(tmp_path: Path) -> None:
    make_project(tmp_path)
    (tmp_path / "_meta" / "_doc_tree.yml").write_text(TREE_YML + "  - {id: z, parent: proj, title: Z, aliases: {a: 1}}\n", encoding="utf-8")
    r = run(tmp_path, "check", "--json")
    assert r.returncode == 2 and as_json(r)["error"]["kind"] == "config"


@pytest.mark.parametrize("target", ["_meta/_doc_tree.yml", "_meta/_doc_summaries.yml"])
def test_invalid_utf8_is_a_config_error_everywhere(tmp_path: Path, target: str) -> None:
    make_project(tmp_path)
    p = tmp_path / target
    p.write_bytes(p.read_bytes() + b"\n# \xff\xfe broken\n")
    for args in (["check", "--json"], ["build", "--json"], ["summaries", "stamp", LOGIN, "--json"]):
        r = run(tmp_path, *args)
        assert r.returncode == 2, (args, r.stdout, r.stderr)
        assert as_json(r)["error"]["kind"] == "config" and "UTF-8" in r.stderr
    doctor = run(tmp_path, str(tmp_path), "--format", "tsv", script="topic-doctor.py")
    assert "Traceback" not in doctor.stderr and "TREE_CONFIG_ERROR" in doctor.stdout
    brief = run(tmp_path, str(tmp_path), script="topic-brief.py")
    assert brief.returncode == 0 and "Traceback" not in brief.stderr


# --------------------------------------------------------------------------- path bounds and collisions


@pytest.mark.parametrize("bad_id", ["../../outside", "a/b", "..", ".hidden", "/abs"])
def test_node_ids_cannot_leave_the_output_dir(tmp_path: Path, bad_id: str) -> None:
    proj = tmp_path / "proj"
    make_project(proj)
    (proj / "_meta" / "_doc_tree.yml").write_text(TREE_YML + f"  - {{id: '{bad_id}', parent: proj, title: X}}\n", encoding="utf-8")
    before = snapshot(tmp_path)
    for args in (["check", "--json"], ["build", "--json"]):
        r = run(proj, *args)
        assert r.returncode == 2 and as_json(r)["error"]["kind"] == "config", (args, r.stdout)
    assert snapshot(tmp_path) == before


def test_node_dir_symlinked_outside_the_project_is_refused(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    make_project(proj)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (proj / W / "_tree").symlink_to(outside, target_is_directory=True)
    r = run(proj, "build", "--json")
    assert r.returncode == 2 and as_json(r)["error"]["kind"] == "config"
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("output", [
    "{catalog: _wiki-methodology/TREE.md}",
    "{tree: _wiki-methodology/_tree/auth.md}",
    "{catalog: _wiki-methodology/_tree/notes.md}",
])
def test_output_collisions_are_refused(tmp_path: Path, output: str) -> None:
    make_project(tmp_path)
    (tmp_path / "_meta" / "_doc_tree.yml").write_text(TREE_YML.replace("version: 1", f"version: 1\noutput: {output}", 1), encoding="utf-8")
    before = snapshot(tmp_path)
    for args in (["check", "--json"], ["build", "--json"]):
        r = run(tmp_path, *args)
        assert r.returncode == 2 and as_json(r)["error"]["kind"] == "config", (args, r.stdout)
    assert snapshot(tmp_path) == before


# --------------------------------------------------------------------------- docs, relocation, place


def test_reference_examples_run_as_written(tmp_path: Path) -> None:
    text = (SKILL_DIR / "references" / "knowledge-tree.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```yaml\n(.*?)```", text, re.S)
    tree = next(b for b in blocks if b.startswith("# _meta/_doc_tree.yml"))
    table = next(b for b in blocks if b.startswith("# _meta/_doc_summaries.yml"))
    write(tmp_path, "_meta/_doc_tree.yml", tree)
    write(tmp_path, "_meta/_doc_summaries.yml", table)
    for rel in doctree_summaries.load_summaries(tmp_path / "_meta" / "_doc_summaries.yml"):
        write(tmp_path, rel, "# 登录页\n\n登录页阴影改用设计 token。\n")
    write(tmp_path, "_wiki-methodology/_top/_decisions/adr-001-x.md", "# ADR 1\n\n一条决策的说明。\n")
    assert run(tmp_path, "build").returncode == 0
    check = run(tmp_path, "check", "--json")
    assert check.returncode == 0, check.stdout
    assert as_json(check)["summary"]["block"] == 0
    assert not [i for i in as_json(check)["issues"] if i["code"] in ("TOPIC_INVALID", "MOUNT_EMPTY", "CONFIG_UNKNOWN_KEY")]


def test_relocated_output_keeps_every_link_resolvable(tmp_path: Path) -> None:
    make_project(tmp_path)
    deep = tmp_path.parent / f"{tmp_path.name}-deep" / "a" / "b" / "c"
    assert run(tmp_path, "build", "--out", str(deep)).returncode == 0
    r = run(tmp_path, "check", "--out", str(deep), "--json")
    assert r.returncode == 0 and not [i for i in as_json(r)["issues"] if i["code"] in ("DEAD_LINK", "STALE")]


def test_new_node_suggestion_is_a_sibling_of_the_nearest_node(tmp_path: Path) -> None:
    make_project(tmp_path)
    cfg = tmp_path / "_meta" / "_doc_tree.yml"
    deeper = TREE_YML + ("  - {id: rerank, parent: kb, title: 重排序, one_line: 检索结果再排序}\n"
                         "  - {id: ce, parent: rerank, title: 交叉编码器, one_line: 交叉编码器模型, aliases: [交叉编码器]}\n")
    cfg.write_text(deeper, encoding="utf-8")
    query = ("place", "--title", "交叉编码器", "--json")
    s1 = as_json(run(tmp_path, *query))["candidates"][0]["score"]
    # just under the line: below min_score, but close enough (>= 0.6 * min_score) to suggest a parent
    cfg.write_text(deeper.replace("min_score: 0.05", f"min_score: {round(s1 * 1.3, 4)}"), encoding="utf-8")
    r = as_json(run(tmp_path, *query))
    assert r["verdict"] == "new-node" and r["candidates"][0]["node"] == "ce"
    assert r["suggest_new_node"]["parent"] == "rerank"  # beside the nearest node, not just its top-level branch


# --------------------------------------------------------------------------- summaries table syntax (tool-managed)

OTHER = f"{W}/_wiki/other.md"
RESTRICTED = {
    "source_block": f"  {LOGIN}:\n    summary: 登录。\n    source: >-\n      auto\n    reviewed_sha: old\n",
    "sha_block": f"  {LOGIN}:\n    summary: 登录。\n    source: auto\n    reviewed_sha: |-\n      old\n  {OTHER}:\n    summary: 其他。\n",
    "entry_alias": f"  {OTHER}: &base\n    summary: 其他。\n    source: auto\n    reviewed_sha: old\n  {LOGIN}: *base\n",
    "scalar_alias": f"  {OTHER}:\n    summary: &label auto\n  {LOGIN}:\n    summary: 登录。\n    source: *label\n",
}


@pytest.mark.parametrize("case", sorted(RESTRICTED))
def test_block_scalars_anchors_and_aliases_are_refused(tmp_path: Path, case: str) -> None:
    make_project(tmp_path)
    write(tmp_path, OTHER, "# O\n\n其他。\n")
    table = tmp_path / "_meta" / "_doc_summaries.yml"
    table.write_text("version: 1\ndocs:\n" + RESTRICTED[case], encoding="utf-8")
    before = table.read_bytes()
    stamp = run(tmp_path, "summaries", "stamp", LOGIN, "--write", "--json")
    assert stamp.returncode == 2, stamp.stdout + stamp.stderr
    assert as_json(stamp)["error"]["kind"] == "config" and table.read_bytes() == before
    check = run(tmp_path, "check", "--json")
    assert check.returncode == 2 and as_json(check)["error"]["kind"] == "config"
    assert re.search(r"line \d+", check.stderr), check.stderr
    doctor = run(tmp_path, str(tmp_path), "--format", "tsv", script="topic-doctor.py")
    assert "block\tTREE_CONFIG_ERROR" in doctor.stdout and "Traceback" not in doctor.stderr


def test_stamp_output_is_reparsed_before_it_is_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    make_project(tmp_path)
    write(tmp_path, LOGIN, "# 登录页\n\n改了一句。\n")
    table = tmp_path / "_meta" / "_doc_summaries.yml"
    before = table.read_bytes()
    original = doctree_summaries._apply_edits

    def corrupting(text, edits):  # a buggy edit that damages a neighbour must never reach disk
        return original(text, edits).replace(f"  {RERANK}:", f"  {RERANK}: broken", 1)

    monkeypatch.setattr(doctree_summaries, "_apply_edits", corrupting)
    monkeypatch.chdir(tmp_path)
    assert doctree.main(["summaries", "stamp", LOGIN, "--write"]) == 1
    assert table.read_bytes() == before
