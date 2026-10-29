"""Tests for scripts/upstream_watch.py. No real network: gh calls are stubbed."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "upstream_watch.py"
spec = importlib.util.spec_from_file_location("upstream_watch", SCRIPT)
uw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uw)

SHA = "a" * 40


def make_source(**over):
    src = {
        "repo": "owner/repo",
        "paths": ["skills/x/SKILL.md"],
        "absorbed_commit": SHA,
        "absorbed_at": "2026-09-01",
        "mode": "vendored",
        "local_paths": ["references/UPSTREAM-SKILL.md"],
        "watch": True,
        "note": "",
    }
    src.update(over)
    return src


def write_skill(root: Path, name: str, sources: list[dict], local_text: str = "local\n") -> Path:
    skill = root / name
    (skill / "references").mkdir(parents=True)
    (skill / "references" / "UPSTREAM-SKILL.md").write_text(local_text)
    record = skill / "UPSTREAM.json"
    record.write_text(json.dumps({"schema": uw.SCHEMA, "sources": sources}))
    return record


def test_lint_accepts_valid_record(tmp_path):
    record = write_skill(tmp_path, "good", [make_source()])
    sources, errors = uw.lint_record(record)
    assert errors == []
    assert len(sources) == 1


@pytest.mark.parametrize(
    "over, fragment",
    [
        ({"mode": "copied"}, "mode must be one of"),
        ({"absorbed_at": "2026/09/01"}, "absorbed_at must be"),
        ({"absorbed_commit": "not-a-sha"}, "absorbed_commit"),
        ({"repo": "just-a-name"}, "owner/name"),
        ({"watch": "yes"}, "watch must be"),
        ({"local_paths": ["missing.md"]}, "does not exist"),
        ({"paths": ["a.md", "b.md"]}, "paired 1:1"),
        ({"extra": 1}, "unknown keys"),
    ],
)
def test_lint_rejects_bad_fields(tmp_path, over, fragment):
    record = write_skill(tmp_path, "bad", [make_source(**over)])
    sources, errors = uw.lint_record(record)
    assert sources == []
    assert any(fragment in e for e in errors), errors


def test_lint_rejects_missing_keys_and_wrong_schema(tmp_path):
    skill = tmp_path / "s"
    skill.mkdir()
    record = skill / "UPSTREAM.json"
    record.write_text(json.dumps({"schema": "old", "sources": [{"repo": "o/r"}]}))
    _, errors = uw.lint_record(record)
    assert any("schema must be" in e for e in errors)
    assert any("missing keys" in e for e in errors)


def test_semantic_source_may_map_directories(tmp_path):
    record = write_skill(
        tmp_path, "sem",
        [make_source(mode="semantic", paths=["a/", "b/c.md"], local_paths=["references"])],
    )
    sources, errors = uw.lint_record(record)
    assert errors == [] and len(sources) == 1


def test_find_records_skips_legacy(tmp_path):
    write_skill(tmp_path, "live", [make_source()])
    write_skill(tmp_path / "_legacy", "old", [make_source()])
    found = uw.find_records(tmp_path)
    assert [p.parent.name for p in found] == ["live"]


def test_lint_cli_exit_codes(tmp_path, capsys):
    write_skill(tmp_path, "good", [make_source()])
    assert uw.main(["--lint", "--root", str(tmp_path)]) == 0
    write_skill(tmp_path, "bad", [make_source(mode="x")])
    assert uw.main(["--lint", "--root", str(tmp_path)]) == 1
    assert "LINT" in capsys.readouterr().out


class FakeGh:
    """Stub for gh_api keyed by endpoint prefix."""

    def __init__(self, commits, content=b"", fail_on=None):
        self.commits = commits
        self.content = content
        self.fail_on = fail_on
        self.calls = []

    def __call__(self, endpoint, raw=False):
        self.calls.append(endpoint)
        if self.fail_on and self.fail_on in endpoint:
            raise uw.GhError(f"timeout after 20s: gh api {endpoint}")
        if endpoint.startswith("repos/owner/repo/commits/"):
            return json.dumps({"commit": {"committer": {"date": "2026-09-01T10:00:00Z"}}}).encode()
        if "/commits?" in endpoint:
            return json.dumps(self.commits).encode()
        if "/contents/" in endpoint:
            assert raw
            return self.content
        raise AssertionError(endpoint)


def commit(sha, msg="change"):
    return {"sha": sha, "commit": {"message": msg, "committer": {"date": "2026-09-05T00:00:00Z"}}}


def run_remote(tmp_path, monkeypatch, fake, sources, local_text="local\n"):
    write_skill(tmp_path, "sk", sources, local_text)
    monkeypatch.setattr(uw, "gh_api", fake)
    return uw.run(tmp_path, remote=True)


def test_remote_ignores_absorbed_commit_itself(tmp_path, monkeypatch):
    fake = FakeGh([commit(SHA)])
    findings, errors, summary = run_remote(tmp_path, monkeypatch, fake, [make_source()])
    assert findings == [] and errors == []
    assert summary["watched_sources"] == 1
    assert "since=2026-09-01T10%3A00%3A00Z" in fake.calls[1]


def test_remote_vendored_same_content_is_not_reported(tmp_path, monkeypatch):
    fake = FakeGh([commit("b" * 40)], content=b"local\n")
    findings, _, _ = run_remote(tmp_path, monkeypatch, fake, [make_source()])
    assert findings == []


def test_remote_vendored_different_content_is_changed(tmp_path, monkeypatch):
    fake = FakeGh([commit("b" * 40, "rewrite")], content=b"new upstream\n")
    findings, _, summary = run_remote(tmp_path, monkeypatch, fake, [make_source()])
    assert summary["changed"] == 1
    f = findings[0]
    assert f["kind"] == "CHANGED" and f["latest_message"] == "rewrite"
    assert f["local_path"] == "references/UPSTREAM-SKILL.md"
    assert hashlib.sha256(b"new upstream\n").hexdigest() != hashlib.sha256(b"local\n").hexdigest()


def test_remote_semantic_reports_commits_without_content_fetch(tmp_path, monkeypatch):
    fake = FakeGh([commit("c" * 40)])
    src = make_source(mode="semantic", local_paths=["references"])
    findings, _, _ = run_remote(tmp_path, monkeypatch, fake, [src])
    assert [f["kind"] for f in findings] == ["CHANGED"]
    assert not any("/contents/" in c for c in fake.calls)


def test_remote_skips_unwatched(tmp_path, monkeypatch):
    fake = FakeGh([commit("c" * 40)])
    findings, _, summary = run_remote(tmp_path, monkeypatch, fake, [make_source(watch=False)])
    assert findings == [] and fake.calls == [] and summary["watched_sources"] == 0


def test_remote_failure_is_reported_not_retried(tmp_path, monkeypatch):
    fake = FakeGh([], fail_on="/commits?")
    findings, _, summary = run_remote(tmp_path, monkeypatch, fake, [make_source()])
    assert summary["failed"] == 1 and findings[0]["kind"] == "FAIL"
    assert sum("/commits?" in c for c in fake.calls) == 1


def test_remote_cli_writes_report_and_json(tmp_path, monkeypatch, capsys):
    fake = FakeGh([commit("c" * 40)], content=b"different\n")
    write_skill(tmp_path, "sk", [make_source()])
    monkeypatch.setattr(uw, "gh_api", fake)
    report = tmp_path / "out" / "report.json"
    rc = uw.main(["--remote", "--json", "--root", str(tmp_path), "--report", str(report)])
    assert rc == 0
    data = json.loads(report.read_text())
    assert data["summary"]["changed"] == 1
    assert json.loads(capsys.readouterr().out) == data


def test_gh_api_timeout_becomes_gherror(monkeypatch):
    def boom(*a, **k):
        raise uw.subprocess.TimeoutExpired(cmd="gh", timeout=20)

    monkeypatch.setattr(uw.subprocess, "run", boom)
    with pytest.raises(uw.GhError, match="timeout"):
        uw.gh_api("repos/o/r/commits")


def test_real_shared_records_pass_lint():
    """Guard: this skill's own UPSTREAM.json follows the schema."""
    findings, errors, summary = uw.run(SCRIPT.parents[1], remote=False)
    assert errors == []
    assert summary["records"] > 0


def test_other_declared_schema_is_skipped_but_missing_schema_is_not(tmp_path):
    other = tmp_path / "a" / "UPSTREAM.json"
    other.parent.mkdir()
    other.write_text(json.dumps({"schema": "vendored-snapshot/v1", "scope": "x", "sources": [{"path": "LICENSE"}]}))
    assert uw.lint_record(other) == ([], [])
    bare = tmp_path / "b" / "UPSTREAM.json"
    bare.parent.mkdir()
    bare.write_text(json.dumps({"scope": "x", "sources": [{"path": "LICENSE"}]}))
    assert uw.lint_record(bare)[1]
