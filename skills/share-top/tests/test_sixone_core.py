"""sixone CLI core P1 逻辑测试(直接测 core 函数)。

钉死: 工具返回正确 envelope; topic_map 只露扣子(role∈step/entry)非完整目录;
describe verdict 语义; bootstrap/unknown 的 fail-loud。
"""
import sys
import json
from types import SimpleNamespace
from pathlib import Path

import pytest

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "core"))
import sixone_core as core  # noqa: E402


def _v4_project(tmp_path: Path) -> Path:
    top = tmp_path / "_wiki-methodology" / "_top"
    top.mkdir(parents=True)
    (top / "_task_plan.md").write_text("# plan\n🧭 当前 [P1.0] x · 上 [P0] · 下 [P2]\n## Done Criteria\n- x\n")
    (tmp_path / "_codemap.md").write_text("# map\n")
    meta = tmp_path / "_meta"
    meta.mkdir()
    (meta / "_registry.yml").write_text(
        "functions:\n"
        "- id: derive\n  name: main\n  module: a.py\n  role: step\n  pipeline: figures.derive\n"
        "- id: helper_x\n  name: load\n  module: a.py\n  role: helper\n"
        "- id: plain\n  name: util\n  module: b.py\n  role: unmarked\n"
    )
    return tmp_path


def test_resolve_owner_ref_matches_doctor_keyset(tmp_path):
    """回归(2026-06-11): deposit 的 _resolve_owner_ref 必须与 topic-doctor 同一套键集。
    旧 bug: deposit 只认 registry `functions:`,但 doctor + v4 标准用 `entries:` →
    entries-based 项目的 code: ref 盖不了章(deposit/doctor 各认一套 = 审查实锤)。"""
    meta = tmp_path / "_meta"; meta.mkdir()
    # entries 型 registry(v4 标准键,doctor 也认)
    (meta / "_registry.yml").write_text("entries:\n- id: frontend-chat\n  path: x.js\n")
    # pipeline:canonical 字段名 != 文件名
    pdir = tmp_path / "_pipelines"; pdir.mkdir()
    (pdir / "P1-brief.yml").write_text("id: P1-brief\npipeline: P1-chat-brief\n")
    # gate
    tdir = tmp_path / "_wiki-methodology" / "_tests"; tdir.mkdir(parents=True)
    (tdir / "_gates.yml").write_text("gates:\n- id: g1\n  cmd: 'true'\n  timeout: 5\n  expect: exit0\n")

    assert core._resolve_owner_ref("code:frontend-chat", tmp_path) is True       # entries 键
    assert core._resolve_owner_ref("code:nope", tmp_path) is False               # 假 id 仍拒
    assert core._resolve_owner_ref("pipeline:P1-chat-brief", tmp_path) is True    # canonical pipeline: 字段
    assert core._resolve_owner_ref("pipeline:P1-brief", tmp_path) is True         # id/文件名
    assert core._resolve_owner_ref("pipeline:ghost", tmp_path) is False
    assert core._resolve_owner_ref("test:g1", tmp_path) is True                   # gate id


def test_describe_contract(tmp_path):
    d = core.describe()
    assert d["schema_version"] == "sixone-cli/v1"
    assert set(d["help"]["verdict_semantics"]["enum"]) == {"ok", "warn", "block", "stale"}
    assert "remediation" in d["help"]["verdict_semantics"]["gate"]  # 死锁豁免写进契约


def test_brief_status_doctor_via_core(tmp_path):
    p = str(_v4_project(tmp_path))
    assert core.topic_brief(p)["schema_version"] == "sixone-brief/v1"
    assert core.topic_status(p)["view"]["phase_id"] == "P1.0"
    assert core.topic_doctor(p)["verdict"] in core.VERDICT_ENUM


def test_topic_map_shows_only_buttons(tmp_path):
    """§11 核心: 默认视图只露扣子(role∈step/entry), 不是全部函数。"""
    m = core.topic_map(str(_v4_project(tmp_path)))
    assert m["total_functions"] == 3
    assert len(m["buttons"]) == 1  # 只有 role=step 的 derive; helper/unmarked 不露
    assert m["buttons"][0]["id"] == "derive"
    assert m["buttons"][0]["pipeline"] == "figures.derive"


def test_unknown_project_fails_loud(tmp_path):
    assert "error" in core.topic_brief("/no/such/project/xyz")


def _pl_project(tmp_path: Path) -> Path:
    """带一条真 pipeline manifest 的 v4 项目(2026-06-15 pipeline 印记引擎)。"""
    meta = tmp_path / "_meta"; meta.mkdir()
    (meta / "_registry.yml").write_text(
        "entrypoints:\n  - id: foo\n    path: src/foo.py\n    type: step\n    status: active\n"
        "    tests:\n      - tests/test_foo.py\n")
    (tmp_path / "src").mkdir(); (tmp_path / "src" / "foo.py").write_text("def foo():\n    return 1\n")
    pdir = tmp_path / "_pipelines"; pdir.mkdir()
    (pdir / "myline.yml").write_text(
        "pipeline: myline\ndesc: \"注释必须保留\"\nstatus: active\nsteps:\n  - id: a\n    ref: foo\n")
    gates = tmp_path / "_wiki-methodology" / "_tests"
    gates.mkdir(parents=True)
    (gates / "_gates.yml").write_text(
        "gates:\n  - id: g1\n    cmd: python tests/test_gate.py\n    timeout: 20\n    expect: exit0\n")
    return tmp_path


def test_pipeline_imprint_cycle(tmp_path):
    """印记引擎核心: 没盖=unverified → 盖=fresh → 改 step 代码=自动 stale → doctor gate。"""
    root = _pl_project(tmp_path)
    m = root / "_pipelines" / "myline.yml"
    assert core.pipeline_trust(m, root) == "unverified"
    r = core.verify_pipeline(str(root), "myline")
    assert r["verdict"] == "ok"
    txt = m.read_text(encoding="utf-8")
    assert "verified_steps_hash:" in txt and "注释必须保留" in txt  # 盖章 + 不 reformat
    assert core.pipeline_trust(m, root) == "fresh"
    (root / "src" / "foo.py").write_text("def foo():\n    return 999\n")  # 改 step 代码
    assert core.pipeline_trust(m, root) == "stale"                        # 自动失效(核心诉求)
    d = core.topic_doctor(str(root), full=True)
    assert d["pipelines"]["stale"] == 1 and d["verdict"] in ("stale", "block")


def test_pipeline_imprint_denoise_and_forgery(tmp_path):
    """降噪: 改 manifest 注释不误判 stale;防伪: 手填假 hash 不认。"""
    root = _pl_project(tmp_path)
    m = root / "_pipelines" / "myline.yml"
    core.verify_pipeline(str(root), "myline")
    m.write_text(m.read_text(encoding="utf-8").replace("注释必须保留", "改了说明而已"), encoding="utf-8")
    assert core.pipeline_trust(m, root) == "fresh"                        # 注释不进契约 hash
    forged = core._yaml_set_scalar(m.read_text(encoding="utf-8"), "verified_steps_hash", "deadbeef")
    m.write_text(forged, encoding="utf-8")
    assert core.pipeline_trust(m, root) == "stale"                        # 手填假值 → 不 fresh


def test_pipeline_engine_backward_compat(tmp_path):
    """无 _pipelines 的项目: 扫描空、doctor 不崩、不引入 stale。"""
    p = _v4_project(tmp_path)
    assert core._pipeline_scan(p) == []
    d = core.topic_doctor(str(p), full=True)
    assert d["pipelines"]["total"] == 0 and d["pipelines"]["stale"] == 0


# ───────── 审查回归(2026-06-15 Gemini + Claude 子智能体 findings)─────────

def test_review_high_duplicate_key_stamp(tmp_path):
    """HIGH: manifest 有重复 verified_steps_hash 时,盖章口(改第一处)与 PyYAML(取最后一处)
    不能打架 → verify 后必须只剩一行且 fresh(否则刚盖完就 stale)。"""
    root = _pl_project(tmp_path)
    m = root / "_pipelines" / "myline.yml"
    m.write_text(m.read_text() + "verified_steps_hash: OLD_FORGED\nverified_steps_hash: OLD2\n", encoding="utf-8")
    assert core.verify_pipeline(str(root), "myline")["verdict"] == "ok"
    txt = m.read_text(encoding="utf-8")
    assert txt.count("verified_steps_hash:") == 1            # 去重: 只剩一行
    assert core.pipeline_trust(m, root) == "fresh"           # 盖完真 fresh, 不被旧值劫持


def test_review_high_affected_after_commit(tmp_path):
    """HIGH: 默认 base 必须看得到"已提交"的改动(AI 常先 commit 再 affected),
    否则空清单把"忘回写"伪装成"没啥要写"。"""
    import subprocess
    root = _pl_project(tmp_path)
    (root / "_codebook").mkdir()
    (root / "_codebook" / "core.md").write_text(
        "---\ntitle: 核\nuser_workflow: x\nowner_refs:\n  - code:foo\n"
        "tracked_paths_hint:\n  - src/foo.py\n---\n# 核\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root)
    subprocess.run(["git", "add", "-A"], cwd=root)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "i"], cwd=root)
    (root / "src" / "foo.py").write_text("def foo():\n    return 2\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "change"], cwd=root)
    af = core.affected(str(root))  # 默认 base, 改动已 commit
    assert "src/foo.py" in af["changed_files"]               # 看得到已提交改动
    assert any("core.md" in n for n in af["codebook_nodes_to_rewrite"])


def test_review_med_condition_change_invalidates(tmp_path):
    """MED: 改 step 的 condition(接线语义)必须失效(黑名单子集纳入 wiring 字段)。"""
    root = _pl_project(tmp_path)
    m = root / "_pipelines" / "myline.yml"
    m.write_text("pipeline: myline\nsteps:\n  - id: a\n    ref: foo\n    condition: x>0\n", encoding="utf-8")
    core.verify_pipeline(str(root), "myline")
    assert core.pipeline_trust(m, root) == "fresh"
    m.write_text(m.read_text().replace("x>0", "x<0"), encoding="utf-8")
    assert core.pipeline_trust(m, root) == "stale"           # 改 condition → 失效


def test_review_med_no_code_refuses_stamp(tmp_path):
    """MED: 有 steps 但没一个绑到 registry 代码 → 拒绝盖章(防空 hash 假 fresh)。"""
    root = _pl_project(tmp_path)
    m = root / "_pipelines" / "myline.yml"
    m.write_text("pipeline: myline\nsteps:\n  - id: a\n", encoding="utf-8")  # step 无 ref
    r = core.verify_pipeline(str(root), "myline")
    assert r["verdict"] == "broken"
    assert any(e["check"] == "no_code" for e in r["errors"])


def test_review_med_wip_broken_not_gated(tmp_path):
    """MED 向后兼容: 从未盖章的 broken(WIP, ref 指向未登记 id)不让 doctor 从 ok→warn。"""
    root = _pl_project(tmp_path)
    (root / "_pipelines" / "wip.yml").write_text(
        "pipeline: wip\nsteps:\n  - id: a\n    ref: not_registered_yet\n", encoding="utf-8")
    pls = core._pipeline_scan(root)
    wip = [p for p in pls if p["pipeline"] == "wip"][0]
    assert wip["trust"] == "broken" and wip["stamped"] is False
    # doctor 的 pl_broken 只收 stamped 的 → WIP broken 不计入 warn 触发
    gated = [p for p in pls if p["trust"] == "broken" and p.get("stamped")]
    assert wip not in gated


def test_codegraph_json_health_contract(monkeypatch, tmp_path):
    fresh = {
        "initialized": True,
        "version": "1.2.3",
        "lastIndexed": "2026-09-01T00:00:00Z",
        "pendingChanges": {"added": 0, "modified": 0, "removed": 0},
        "worktreeMismatch": None,
        "index": {"reindexRecommended": False},
    }
    monkeypatch.setattr(
        core.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(fresh), stderr=""),
    )
    status = core._codegraph_status(tmp_path)
    assert status["available"] is True and status["fresh"] is True

    fresh["pendingChanges"]["modified"] = 1
    degraded = core._codegraph_status(tmp_path)
    assert degraded["available"] is True and degraded["fresh"] is False
    assert "clues only" in degraded["note"]


def test_codegraph_impact_partitions_evidence_from_active(monkeypatch, tmp_path):
    response = {
        "affected": [
            {"name": "f", "kind": "function", "filePath": "src/live.py", "startLine": 3},
            {"name": "f", "kind": "function", "filePath": "_outputs/run/frozen_sources/src/live.py", "startLine": 3},
            {"name": "f", "kind": "function", "filePath": "_legacy/old/live.py", "startLine": 3},
            {"name": "f", "kind": "function", "filePath": "external/vendor/live.py", "startLine": 3},
        ]
    }
    monkeypatch.setattr(
        core.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout=json.dumps(response), stderr=""),
    )
    impacts = core._codegraph_impacts(tmp_path, ["f"], depth=1)
    assert [entry["path"] for entry in impacts["active"]] == ["src/live.py"]
    assert impacts["evidence"][0]["path"].startswith("_outputs/")
    assert impacts["legacy_or_temp"][0]["path"].startswith("_legacy/")
    assert impacts["external_or_vendor"][0]["path"].startswith("external/")


def test_affected_task_scope_maps_registry_codebook_and_pipeline(monkeypatch, tmp_path):
    root = _pl_project(tmp_path)
    (root / "_codebook").mkdir()
    (root / "_codebook" / "core.md").write_text(
        "---\ntitle: core\nuser_workflow: x\nowner_refs:\n  - code:foo\n"
        "tracked_paths_hint:\n  - src/foo.py\n---\n# core\n",
        encoding="utf-8",
    )
    subprocess = __import__("subprocess")
    subprocess.run(["git", "init", "-q"], cwd=root)
    subprocess.run(["git", "add", "-A"], cwd=root)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=root,
    )
    monkeypatch.setattr(core, "_codegraph_status", lambda _root: {"available": True, "fresh": True, "note": "fresh"})
    monkeypatch.setattr(
        core, "_codegraph_impacts",
        lambda *_a, **_k: {
            "active": [{"symbol": "foo", "name": "foo", "kind": "function", "path": "src/foo.py", "line": 1}],
            "evidence": [], "legacy_or_temp": [], "external_or_vendor": [],
        },
    )
    monkeypatch.setattr(core, "_codegraph_affected_tests", lambda *_a, **_k: ["tests/test_foo.py"])
    result = core.affected(
        str(root), since="HEAD", task_id="P1.0.E1",
        task_scopes=["symbol:foo", "path:src/foo.py"], task_gates=["gate-foo"],
    )
    assert result["task_id"] == "P1.0.E1"
    assert result["declared_paths"] == ["src/foo.py"]
    assert result["tests_suggested"] == ["tests/test_foo.py"]
    assert any(entry["id"] == "foo" for entry in result["registry_entries_affected"])
    assert any(path.endswith("core.md") for path in result["codebook_nodes_to_rewrite"])
    assert any(entry["pipeline"] == "myline" for entry in result["pipelines_affected"])


def test_affected_resolves_typed_registry_pipeline_and_gate_scopes(monkeypatch, tmp_path):
    root = _pl_project(tmp_path)
    monkeypatch.setattr(
        core, "_codegraph_status",
        lambda _root: {"available": False, "fresh": False, "note": "degraded"},
    )
    result = core.affected(
        str(root), since="HEAD", task_id="P1.0.E2",
        task_scopes=["registry:foo", "pipeline:myline"],
        task_gates=["test:g1"],
    )
    assert result["declared_registry_ids"] == ["foo"]
    assert result["declared_pipeline_ids"] == ["myline"]
    assert "src/foo.py" in result["declared_paths"]
    assert "_pipelines/myline.yml" in result["declared_paths"]
    assert any(entry["id"] == "foo" for entry in result["registry_entries_affected"])
    assert any(entry["pipeline"] == "myline" for entry in result["pipelines_affected"])
    assert result["gates_resolved"][0]["id"] == "g1"
    assert "tests/test_foo.py" in result["tests_suggested"]
    assert "tests/test_gate.py" in result["tests_suggested"]
