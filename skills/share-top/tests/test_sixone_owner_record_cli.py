from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
CLI = SKILL / "scripts" / "sixone-cli.py"


def make_project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    top = root / "_wiki-methodology" / "_top"
    tests = root / "_wiki-methodology" / "_tests"
    meta = root / "_meta"
    codebook = root / "_codebook"
    for path in (top, tests, meta, codebook, root / "_pipelines"):
        path.mkdir(parents=True, exist_ok=True)
    (root / "_codemap.md").write_text("# map\n", encoding="utf-8")
    (top / "_task_plan.md").write_text(
        "# plan\n\n🧭 当前 [P1.0] task=[none] idle\n"
        "> Done Criteria: owner and record cases pass\n\n"
        "## Current Coordinate\n\n- Goal: test\n- Current task: none\n"
        "- Next task: P1.0.E1\n- Latest learning: none\n- Blocker: none\n\n"
        "## Active Work\n\n- [ ] P1.0.E1 Work\n",
        encoding="utf-8",
    )
    (meta / "_registry.yml").write_text(
        "entries:\n  - id: demo\n    path: src/demo.py\n",
        encoding="utf-8",
    )
    (meta / "_data_registry.yml").write_text(
        "assets:\n  - id: data-demo\n    path: data/demo.csv\n",
        encoding="utf-8",
    )
    (tests / "_gates.yml").write_text(
        "gates:\n  - id: gate-demo\n    cmd: pytest -q\n",
        encoding="utf-8",
    )
    (root / "_pipelines" / "demo.yml").write_text(
        "pipeline: demo-line\nsteps: []\n",
        encoding="utf-8",
    )
    (codebook / "demo.md").write_text("# Demo\n", encoding="utf-8")
    return root


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args], capture_output=True,
        text=True, timeout=20,
    )


def body(result: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(result.stdout)


def test_owner_list_show_and_resolve(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    listed = run_cli("owner", "list", str(root))
    assert listed.returncode == 0
    owners = {entry["column"]: entry for entry in body(listed)["owners"]}
    assert owners["top"]["enabled"] is True
    assert owners["code"]["enabled"] is True

    shown = run_cli("owner", "show", str(root), "tests")
    assert shown.returncode == 0
    assert any(entry["exists"] for entry in body(shown)["paths"])

    registry = body(run_cli("owner", "resolve", str(root), "registry:demo"))
    assert registry["count"] == 1
    assert registry["matches"][0]["entry"]["path"] == "src/demo.py"
    gate = body(run_cli("owner", "resolve", str(root), "gate:gate-demo"))
    assert gate["count"] == 1
    symbol = body(run_cli("owner", "resolve", str(root), "symbol:Demo"))
    assert "search symbol" in symbol["next_hint"]


def test_record_add_list_and_show(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    created = run_cli(
        "record", "add", "finding", str(root),
        "--title", "Parser case", "--summary", "A bounded record was created.",
        "--evidence", "_tests/case.txt",
    )
    assert created.returncode == 0, created.stderr
    created_body = body(created)
    assert created_body["verdict"] == "ok"
    assert created_body["path"].startswith("_wiki-methodology/_top/_findings/")

    listed = body(run_cli("record", "list", "finding", str(root)))
    assert listed["count"] == 1
    shown = body(run_cli("record", "show", str(root), created_body["path"]))
    assert "# Parser case" in shown["content"]
    assert shown["truncated"] is False


def test_record_show_rejects_path_escape(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    result = run_cli("record", "show", str(root), "../../etc/passwd")
    assert result.returncode == 2
    assert "inside _wiki-methodology/_top" in body(result)["error"]


def test_log_record_preserves_generic_evidence_as_verification(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    created = run_cli(
        "record", "add", "log", str(root),
        "--title", "Migration case", "--summary", "Control plane migrated.",
        "--evidence", "test:record-case",
    )
    assert created.returncode == 0, created.stderr
    path = root / body(created)["path"]
    text = path.read_text(encoding="utf-8")
    assert "### Verification" in text
    assert "test:record-case" in text
