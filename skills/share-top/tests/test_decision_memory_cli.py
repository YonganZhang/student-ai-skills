"""Public CLI checks: recover a decision without replaying a conversation."""
from pathlib import Path

from test_sixone_owner_record_cli import body, make_project, run_cli


def test_decision_round_trip_and_selective_recall(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    before = (root / "_wiki-methodology/_top/_task_plan.md").read_bytes()
    created = run_cli(
        "record", "add", "decision", str(root), "--title", "融合 mask 约束",
        "--summary", "先做有效性掩码，再聚合。", "--request", "缺失模态不能当作真实零值",
        "--rationale", "补零后无掩码聚合改变有效模态的权重",
        "--alternative", "直接平均：拒绝，会混入缺失值",
        "--file", "src/fusion.py::masked_mean", "--source", "task:P1.0.E1",
        "--source", "session:fixture-explicit-reference", "--commit", "uncommitted",
        "--test", "not-run: fixture demonstrates record transport only",
        "--evidence", "tests/test_missing_modality.py",
    )
    assert created.returncode == 0, created.stderr
    ref = body(created)["path"]
    found = body(run_cli("record", "search", str(root), "融合 MASK"))
    assert found["complete"] is True
    assert [item["path"] for item in found["records"]] == [ref]
    shown = body(run_cli("record", "show", str(root), ref))
    for text in ("缺失模态不能当作真实零值", "补零后无掩码", "直接平均", "masked_mean",
                 "task:P1.0.E1", "not-run:", "uncommitted", "test_missing_modality.py"):
        assert text in shown["content"]
    assert body(run_cli("record", "search", str(root), "不存在的约束"))["records"] == []
    assert (root / "_wiki-methodology/_top/_task_plan.md").read_bytes() == before


def test_old_records_search_and_default_output_limit(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    directory = root / "_wiki-methodology/_top/_decisions"
    directory.mkdir()
    for i in range(8):
        (directory / f"2026-01-{i+1:02}.md").write_text(
            f"# Legacy mask decision {i}\n\nReject averaging missing inputs.\n" + "context " * 300,
            encoding="utf-8",
        )
    (directory / "_template.md").write_text("# mask template")
    result = body(run_cli("record", "search", str(root), "mask"))
    assert result["count"] == 8
    assert len(result["records"]) == 3
    assert result["results_truncated"] is True
    assert result["complete"] is True
    assert all(len(item["excerpt"]) <= 700 for item in result["records"])
    assert all("template" not in item["path"] for item in result["records"])


def test_no_implicit_commit_or_passed_verification(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    created = body(run_cli("record", "add", "decision", str(root),
                           "--title", "Pending experiment", "--summary", "Try masked fusion"))
    content = body(run_cli("record", "show", str(root), created["path"]))["content"]
    assert "unknown / not supplied" in content
    assert "not-run: no verification supplied" in content
    assert "unknown: source not supplied" in content


def test_search_excludes_escaped_symlinks_and_oversized_records(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    directory = root / "_wiki-methodology/_top/_decisions"
    directory.mkdir()
    secret = tmp_path / "outside.md"
    secret.write_text("# mask SECRET_OUTSIDE")
    (directory / "escaped.md").symlink_to(secret)
    (directory / "oversized.md").write_text("# mask\n" + "x" * 70000)
    result = run_cli("record", "search", str(root), "mask")
    data = body(result)
    assert data["skipped"] == 2
    assert data["complete"] is False
    assert data["records"] == []
    assert "SECRET_OUTSIDE" not in result.stdout


def test_search_rejects_invalid_queries_and_missing_top(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    for query in (" ", "x" * 257, " ".join(str(i) for i in range(13))):
        assert run_cli("record", "search", str(root), query).returncode == 2
    assert run_cli("record", "search", str(root), "mask", "--limit", "99").returncode == 2
    assert run_cli("record", "search", str(tmp_path / "absent"), "mask").returncode == 2


def test_show_bounds_a_single_long_line(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    directory = root / "_wiki-methodology/_top/_decisions"
    directory.mkdir()
    path = directory / "long.md"
    path.write_text("# Long\n" + "x" * 30000)
    shown = body(run_cli("record", "show", str(root), str(path.relative_to(root))))
    assert len(shown["content"]) <= 12000
    assert shown["truncated"] is True


def test_search_scope_is_explicit(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    created = body(run_cli("record", "add", "finding", str(root),
                           "--title", "mask finding", "--summary", "Missingness changes weights"))
    assert body(run_cli("record", "search", str(root), "mask"))["count"] == 0
    found = body(run_cli("record", "search", str(root), "mask", "--kind", "all"))
    assert found["records"][0]["path"] == created["path"]


def test_wrong_record_kind_does_not_silently_drop_decision_fields(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    result = run_cli("record", "add", "finding", str(root), "--title", "A finding",
                     "--summary", "A result", "--rationale", "A decision reason")
    assert result.returncode == 2
    assert "kind=decision" in body(result)["stderr"]
    assert body(run_cli("record", "list", "finding", str(root)))["count"] == 0


def test_scan_limit_reports_incomplete_instead_of_false_exhaustiveness(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    directory = root / "_wiki-methodology/_top/_decisions"
    directory.mkdir()
    for i in range(502):
        (directory / f"{i:04}.md").write_text("# mask\n")
    result = body(run_cli("record", "search", str(root), "mask"))
    assert result["scanned"] == 500
    assert result["scan_truncated"] is True
    assert result["complete"] is False
    assert len(result["records"]) == 3


def test_search_does_not_follow_an_external_record_directory(tmp_path: Path) -> None:
    root = make_project(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("# mask SECRET_OUTSIDE")
    (root / "_wiki-methodology/_top/_decisions").symlink_to(outside, target_is_directory=True)
    result = run_cli("record", "search", str(root), "mask")
    assert body(result)["skipped"] == 1
    assert body(result)["complete"] is False
    assert "SECRET_OUTSIDE" not in result.stdout
