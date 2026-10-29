#!/usr/bin/env python3
"""Knowledge tree (doctree): CLI contract, check codes, determinism, managed-output cleanup, place."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))
import doctree_place  # noqa: E402
import doctree_summaries  # noqa: E402

TREE_YML = """\
version: 1
root: proj
scan:
  include: ["_wiki-methodology/**/*.md"]
  exclude: ["_wiki-methodology/_wiki/private/**"]
coverage: ["_wiki-methodology/_top/decisions/anchors/*.md"]
mounts:
  - glob: "_wiki-methodology/_top/decisions/anchors/anchor-*.md"
    topics: [anchors]
columns:
  - {label: 知识, glob: ["_wiki-methodology/_wiki/**"]}
  - {label: 测试, glob: ["_wiki-methodology/_tests/**"]}
place: {variant: knn, min_score: 0.05, min_margin: 0.25}
nodes:
  - {id: proj, title: Project}
  - {id: auth, parent: proj, title: 账号与登录, one_line: 登录页、口令、角色权限, aliases: [登录, 口令]}
  - {id: kb, parent: proj, title: 知识库, one_line: 检索、重排序、文献, aliases: [知识库, 检索]}
  - {id: anchors, parent: proj, title: 衔接点, one_line: 改上游的登记, place: rule-only}
"""
W = "_wiki-methodology"
LOGIN = f"{W}/_wiki/login.md"
RERANK = f"{W}/_tests/rerank.md"
ANCHOR = f"{W}/_top/decisions/anchors/anchor-01-x.md"


def write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def sha(root: Path, rel: str) -> str:
    return hashlib.sha256((root / rel).read_bytes()).hexdigest()[:12]


def summaries(root: Path, docs: dict[str, dict]) -> None:
    lines = ["version: 1", "docs:"]
    for rel, e in docs.items():
        lines.append(f"  {rel}:")
        lines += [f"    {k}: {json.dumps(v, ensure_ascii=False)}" for k, v in e.items()]
    write(root, "_meta/_doc_summaries.yml", "\n".join(lines) + "\n")


def make_project(root: Path) -> None:
    write(root, f"{W}/_top/_task_plan.md", "# Plan\n")
    write(root, "_meta/_doc_tree.yml", TREE_YML)
    write(root, LOGIN, "# 登录页\n\n登录页阴影改为设计 token，口令提交方式不变。\n")
    write(root, RERANK, "# 重排序评测\n\n## 一句话\n\n知识库检索加重排序后命中率提升。\n")
    write(root, ANCHOR, "---\nstatus: active\nsuperseded_by: 没有，仍在用\n---\n# Anchor 01\n\n> 立 2026-05-08\n\n改了核心的一处会话字段。\n")
    write(root, f"{W}/_top/decisions/anchors/README.md", "# anchors\n\n说明。\n")
    summaries(root, {LOGIN: {"topics": ["auth"], "summary": "登录页阴影改用设计 token；口令提交方式不变。",
                             "source": "reviewed", "reviewed_sha": sha(root, LOGIN)},
                     RERANK: {"topics": ["kb", "auth"]}})


def doctree(root: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPTS / "doctree.py"), *args], cwd=root, text=True,
                          capture_output=True, check=False, env=env, stdin=subprocess.DEVNULL, timeout=60)


def as_json(r: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(r.stdout)


def codes(root: Path) -> set[tuple[str, str, str]]:
    r = doctree(root, "check", "--format", "json")
    return {(i["severity"], i["code"], i["where"]) for i in as_json(r)["issues"]}


def snapshot(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def test_not_enabled_gives_parseable_json_and_touches_nothing(tmp_path: Path) -> None:
    write(tmp_path, f"{W}/_top/_task_plan.md", "# Plan\n")
    before = snapshot(tmp_path)
    for cmd in (["check"], ["show"]):
        r = doctree(tmp_path, *cmd, "--format", "json")
        assert r.returncode == 0 and as_json(r)["enabled"] is False and as_json(r)["issues"] == []
    assert "not enabled" in doctree(tmp_path, "check").stdout
    for cmd in (["build"], ["place", "--title", "x"], ["summaries", "stamp", "a.md"]):
        r = doctree(tmp_path, *cmd, "--format", "json")
        assert r.returncode == 2, cmd
        err = as_json(r)
        assert err["enabled"] is False and err["error"]["kind"] == "not-enabled" and "not enabled" in r.stderr
    assert snapshot(tmp_path) == before


def test_build_is_byte_identical_and_marks_derived_and_auto(tmp_path: Path) -> None:
    make_project(tmp_path)
    r = doctree(tmp_path, "build", "--json", env={**os.environ, "PYTHONHASHSEED": "1"})
    assert r.returncode == 0, r.stderr
    assert len(as_json(r)["written"]) == 6  # TREE + 4 node pages + CATALOG
    first = snapshot(tmp_path / W)
    r2 = doctree(tmp_path, "build", "--json", env={**os.environ, "PYTHONHASHSEED": "999"})
    assert as_json(r2)["written"] == [] and len(as_json(r2)["unchanged"]) == 6
    assert snapshot(tmp_path / W) == first
    out_a, out_b = tmp_path.parent / f"{tmp_path.name}-a", tmp_path.parent / f"{tmp_path.name}-b"
    doctree(tmp_path, "build", "--out", str(out_a), env={**os.environ, "PYTHONHASHSEED": "3"})
    doctree(tmp_path, "build", "--out", str(out_b), env={**os.environ, "PYTHONHASHSEED": "4"})
    assert snapshot(out_a) == snapshot(out_b)
    for page in [tmp_path / W / "TREE.md", tmp_path / W / "CATALOG.md", *(tmp_path / W / "_tree").glob("*.md")]:
        assert page.read_text(encoding="utf-8").startswith("<!-- doctree:generated")
    tree = (tmp_path / W / "TREE.md").read_text(encoding="utf-8")
    assert "(_tree/auth.md)" in tree and "(CATALOG.md)" in tree
    kb = (tmp_path / W / "_tree" / "kb.md").read_text(encoding="utf-8")
    assert "〔自动摘录，未审〕知识库检索加重排序后命中率提升" in kb       # no summary in the entry -> marked excerpt
    auth = (tmp_path / W / "_tree" / "auth.md").read_text(encoding="utf-8")
    assert "— 登录页阴影改用设计 token" in auth and "也相关" in auth  # reviewed entry unmarked; secondary topic
    anchors = (tmp_path / W / "_tree" / "anchors.md").read_text(encoding="utf-8")
    assert "`状态: active`" in anchors and "改了核心的一处会话字段" in anchors
    catalog = (tmp_path / W / "CATALOG.md").read_text(encoding="utf-8")
    assert "_task_plan" not in catalog and "README.md" in catalog  # plan structure is never a doc


def test_check_flags_staleness_of_every_generated_file(tmp_path: Path) -> None:
    make_project(tmp_path)
    doctree(tmp_path, "build")
    ok = doctree(tmp_path, "check", "--format", "tsv")
    assert ok.returncode == 0, ok.stdout
    assert f"warn\tORPHAN\t{W}/_top/decisions/anchors/README.md" in ok.stdout
    assert "DEAD_LINK" not in ok.stdout  # prose superseded_by is not a link
    catalog = tmp_path / W / "CATALOG.md"
    catalog.write_text(catalog.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    assert ("block", "STALE", f"{W}/CATALOG.md") in codes(tmp_path)
    doctree(tmp_path, "build")
    (tmp_path / W / "_tree" / "kb.md").unlink()
    assert ("block", "STALE", f"{W}/_tree/kb.md") in codes(tmp_path)
    doctree(tmp_path, "build")
    write(tmp_path, ANCHOR, "---\nstatus: retired\n---\n# Anchor 01\n\n改了核心的一处会话字段。\n")
    r = doctree(tmp_path, "check", "--format", "json")
    assert r.returncode == 1 and as_json(r)["verdict"] == "block"
    assert ("block", "STALE", f"{W}/_tree/anchors.md") in codes(tmp_path)


def test_summary_drift_codes_and_stamp(tmp_path: Path) -> None:
    make_project(tmp_path)
    doctree(tmp_path, "build")
    assert ("warn", "SUMMARY_MISSING", RERANK) in codes(tmp_path)
    write(tmp_path, LOGIN, "# 登录页\n\n口令登录已删除，只保留扫码。\n")
    assert ("warn", "SUMMARY_STALE", LOGIN) in codes(tmp_path)
    table = tmp_path / "_meta" / "_doc_summaries.yml"
    before = table.read_bytes()
    dry = doctree(tmp_path, "summaries", "stamp", LOGIN, "--json")
    assert dry.returncode == 0 and as_json(dry)["changed"] == [LOGIN] and as_json(dry)["written"] is False
    assert table.read_bytes() == before
    rejected = doctree(tmp_path, "summaries", "stamp", LOGIN, f"{W}/nope.md", "--write", "--json")
    assert rejected.returncode == 1 and as_json(rejected)["failed"] and table.read_bytes() == before
    assert doctree(tmp_path, "summaries", "stamp", LOGIN, "--write").returncode == 0
    assert ("warn", "SUMMARY_STALE", LOGIN) not in codes(tmp_path)
    assert "unchanged=1" in doctree(tmp_path, "summaries", "stamp", LOGIN, "--write").stdout
    summaries(tmp_path, {LOGIN: {"topics": ["auth"], "summary": "草稿。", "source": "auto"},
                         f"{W}/_wiki/gone.md": {"topics": ["auth"], "summary": "x", "source": "reviewed"},
                         ANCHOR: {"summary": "y", "source": "maybe"},
                         RERANK: {"topics": ["nope"], "summary": "z", "source": "reviewed", "reviewed_sha": sha(tmp_path, RERANK)}})
    write(tmp_path, f"{W}/_wiki/private/p.md", "# P\n\n私有。\n")
    with table.open("a", encoding="utf-8") as fh:
        fh.write(f"  {W}/_wiki/private/p.md:\n    summary: p\n")
    found = codes(tmp_path)
    assert ("warn", "SUMMARY_AUTO", LOGIN) in found
    assert ("block", "ENTRY_DEAD", f"{W}/_wiki/gone.md") in found
    assert ("block", "ENTRY_INVALID", ANCHOR) in found
    assert ("block", "TOPIC_INVALID", RERANK) in found
    assert ("warn", "ENTRY_OUT_OF_SCOPE", f"{W}/_wiki/private/p.md") in found


def test_structure_errors_block_check_and_build(tmp_path: Path) -> None:
    make_project(tmp_path)
    cfg = tmp_path / "_meta" / "_doc_tree.yml"
    cfg.write_text(TREE_YML.replace("root: proj", "root: proj\nx-owner: team\nmystery: 1")
                   + "  - {id: kb, parent: proj, title: dup}\n  - {id: a, parent: b, title: A}\n"
                   + "  - {id: b, parent: a, title: B}\n  - {id: c, parent: zz, title: C}\n  - {id: lone, title: L}\n",
                   encoding="utf-8")
    found = codes(tmp_path)
    for code in ("DUP_ID", "PARENT_CYCLE", "PARENT_MISSING", "EXTRA_ROOT"):
        assert any(s == "block" and c == code for s, c, _ in found), code
    assert ("warn", "CONFIG_UNKNOWN_KEY", "_meta/_doc_tree.yml") in found
    assert sum(1 for _s, c, _w in found if c == "CONFIG_UNKNOWN_KEY") == 1  # x-owner is an extension key
    before = snapshot(tmp_path)
    b = doctree(tmp_path, "build", "--json")
    assert b.returncode == 1 and as_json(b)["blocking"] and snapshot(tmp_path) == before
    cfg.write_text(TREE_YML.replace("root: proj", "root: nothere"), encoding="utf-8")
    assert any(c == "ROOT_MISSING" for _s, c, _w in codes(tmp_path))
    cfg.write_text(TREE_YML.replace("anchor-*.md", "nomatch-*.md")
                   + "  - {id: empty, parent: proj, title: E}\n", encoding="utf-8")
    found = codes(tmp_path)
    assert any(c == "MOUNT_EMPTY" for _s, c, _w in found) and ("warn", "NODE_EMPTY", "empty") in found


def test_superseded_by_path_must_exist(tmp_path: Path) -> None:
    make_project(tmp_path)
    write(tmp_path, ANCHOR, "---\nsuperseded_by: anchor-99-new.md\n---\n# Anchor 01\n\n正文正文正文。\n")
    doctree(tmp_path, "build")
    assert ("block", "DEAD_LINK", ANCHOR) in codes(tmp_path)


def test_cleanup_touches_only_managed_pages(tmp_path: Path) -> None:
    make_project(tmp_path)
    doctree(tmp_path, "build")
    note = write(tmp_path, f"{W}/_tree/notes.md", "# 手写笔记\n")
    cfg = tmp_path / "_meta" / "_doc_tree.yml"
    cfg.write_text(TREE_YML.replace("  - {id: kb, parent: proj, title: 知识库, one_line: 检索、重排序、文献, aliases: [知识库, 检索]}\n", "")
                   .replace("topics: [kb, auth]", ""), encoding="utf-8")
    summaries(tmp_path, {LOGIN: {"topics": ["auth"], "summary": "s", "source": "reviewed", "reviewed_sha": sha(tmp_path, LOGIN)}})
    assert ("block", "STALE", f"{W}/_tree/kb.md") in codes(tmp_path)
    r = doctree(tmp_path, "build", "--json")
    assert r.returncode == 0 and as_json(r)["deleted"] == [f"{W}/_tree/kb.md"]
    assert note.read_text(encoding="utf-8") == "# 手写笔记\n"
    assert ("warn", "UNMANAGED_IN_OUTPUT", f"{W}/_tree/notes.md") in codes(tmp_path)
    index = write(tmp_path, f"{W}/INDEX.md", "# 手写索引\n")
    cfg.write_text(TREE_YML.replace("version: 1", f"version: 1\noutput: {{tree: {W}/INDEX.md}}"), encoding="utf-8")
    refused = doctree(tmp_path, "build", "--json")
    assert refused.returncode == 1 and as_json(refused)["refused"] == [f"{W}/INDEX.md"]
    assert index.read_text(encoding="utf-8") == "# 手写索引\n"
    assert ("block", "OUTPUT_UNMANAGED", f"{W}/INDEX.md") in codes(tmp_path)


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores directory permissions")
def test_partial_write_failure_exits_3_and_reports(tmp_path: Path) -> None:
    make_project(tmp_path)
    doctree(tmp_path, "build")
    node_dir = tmp_path / W / "_tree"
    cfg = tmp_path / "_meta" / "_doc_tree.yml"
    cfg.write_text(TREE_YML + "  - {id: newnode, parent: proj, title: 新节点}\n", encoding="utf-8")
    node_dir.chmod(0o555)
    try:
        r = doctree(tmp_path, "build", "--json")
    finally:
        node_dir.chmod(0o755)
    body = as_json(r)
    assert r.returncode == 3, r.stdout + r.stderr
    assert f"{W}/TREE.md" in body["written"] and body["failed"][0]["path"] == f"{W}/_tree/newnode.md"
    assert "failed" in r.stderr


def test_usage_and_config_errors_exit_2(tmp_path: Path) -> None:
    make_project(tmp_path)
    bad = doctree(tmp_path, "check", "--bogus", "--format", "json")
    assert bad.returncode == 2 and as_json(bad)["error"]["kind"] == "usage" and bad.stderr
    assert doctree(tmp_path, "place", "--json").returncode == 2
    assert as_json(doctree(tmp_path, "place", "missing.md", "--json"))["error"]["exit"] == 2
    assert doctree(tmp_path, "--tree", "nope.yml", "check").returncode == 2
    assert doctree(tmp_path, "show", "nonode").returncode == 2
    cfg = tmp_path / "_meta" / "_doc_tree.yml"
    cfg.write_text("nodes: [\n", encoding="utf-8")
    broken = doctree(tmp_path, "check", "--json")
    assert broken.returncode == 2 and as_json(broken)["error"]["kind"] == "config"
    cfg.write_text(TREE_YML.replace("version: 1", "version: 2"), encoding="utf-8")
    assert "unsupported version" in doctree(tmp_path, "check").stderr
    cfg.write_text(TREE_YML.replace("version: 1", "version: 1\noutput: {tree: ../outside.md}"), encoding="utf-8")
    assert doctree(tmp_path, "build").returncode == 2
    help_ = doctree(tmp_path, "--help")
    assert help_.returncode == 0 and "Examples" in help_.stdout and "Exit codes" in help_.stdout


def test_place_gives_candidates_and_never_writes(tmp_path: Path) -> None:
    make_project(tmp_path)
    doctree(tmp_path, "build")
    before = snapshot(tmp_path)
    draft = write(tmp_path.parent / f"{tmp_path.name}-drafts", "new.md", "# 登录页口令输入框\n\n登录页的口令输入改为显示强度提示。\n")
    good = as_json(doctree(tmp_path, "place", str(draft), "--json"))
    assert good["schema_version"] == "doctree-place/v1" and good["candidates"][0]["node"] == "auth"
    novel = as_json(doctree(tmp_path, "place", "--title", "无人机巡检图像识别", "--json"))
    assert novel["verdict"] == "new-node" and novel["suggest_new_node"]["parent"] == "proj"
    rule = write(tmp_path, f"{W}/_top/decisions/anchors/anchor-02-y.md", "# Anchor 02\n\n新的衔接点。\n")
    assert as_json(doctree(tmp_path, "place", str(rule), "--json"))["verdict"] == "rule"
    rule.unlink()
    assert snapshot(tmp_path) == before
    (tmp_path / "_meta" / "_doc_tree.yml").write_text(TREE_YML.replace("place: {variant: knn, min_score: 0.05, min_margin: 0.25}\n", ""), encoding="utf-8")
    raw = as_json(doctree(tmp_path, "place", str(draft), "--json"))
    assert raw["calibrated"] is False and raw["verdict"] == "uncertain"
    assert "判定线未校准" in doctree(tmp_path, "place", str(draft)).stdout


def test_tokenizers_split_scripts_and_take_extra_stopwords() -> None:
    assert doctree_place.tokenize_cjk("登录页口令") == ["登录", "录页", "页口", "口令"]
    assert doctree_place.tokenize_ascii("Login-Page tool_x 2026 the") == ["login", "page", "tool"]
    tok = doctree_place.make_tokenizer({"stopwords": {"cjk": ["录页"], "ascii": ["Page"]}})
    assert "录页" not in tok("登录页") and "page" not in tok("login page")


def test_show_reports_where_each_field_comes_from(tmp_path: Path) -> None:
    make_project(tmp_path)
    login = as_json(doctree(tmp_path, "show", "--doc", LOGIN, "--json"))
    assert (login["topics_from"], login["summary_from"], login["review"]) == ("entry", "entry", "fresh")
    anchor = as_json(doctree(tmp_path, "show", "--doc", ANCHOR, "--json"))
    assert (anchor["topics_from"], anchor["summary_from"], anchor["review"]) == ("mount", "excerpt", "none")
    write(tmp_path, LOGIN, "# 登录页\n\n改了。\n")
    assert as_json(doctree(tmp_path, "show", "--doc", LOGIN, "--json"))["review"] == "stale"
    outline = as_json(doctree(tmp_path, "show", "--json"))["outline"]
    assert [o["node"] for o in outline] == ["proj", "auth", "kb", "anchors"]


def test_stamp_keeps_the_header_and_reads_back(tmp_path: Path) -> None:
    make_project(tmp_path)
    table = tmp_path / "_meta" / "_doc_summaries.yml"
    table.write_text("# 团队说明\n" + table.read_text(encoding="utf-8"), encoding="utf-8")
    write(tmp_path, LOGIN, "# 登录页\n\n改了一句。\n")
    assert doctree(tmp_path, "summaries", "stamp", LOGIN, "--write").returncode == 0
    assert table.read_text(encoding="utf-8").startswith("# 团队说明\nversion: 1\ndocs:\n")
    entries = doctree_summaries.load_summaries(table)
    assert entries[LOGIN].reviewed_sha == sha(tmp_path, LOGIN) and entries[RERANK].source == "auto"
