#!/usr/bin/env python3
"""Regression tests for Topic six-column tools."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_DIR / "scripts"


def run_script(script: str, root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def write_v4_project(root: Path) -> None:
    (root / "_wiki-methodology" / "_top").mkdir(parents=True)
    (root / "_wiki-methodology" / "_top" / "_task_plan.md").write_text(
        "# Plan\n\n> **Current: [P1.1] ship**\n> Done Criteria: concrete gate\n",
        encoding="utf-8",
    )
    (root / "_wiki-methodology" / "_wiki").mkdir(parents=True)
    (root / "_wiki-methodology" / "_wiki" / "README.md").write_text("# Wiki\n", encoding="utf-8")
    (root / "_wiki-methodology" / "_tests").mkdir(parents=True)
    (root / "_wiki-methodology" / "_tests" / "README.md").write_text("# Tests\n", encoding="utf-8")
    (root / "_meta").mkdir()
    (root / "_meta" / "_registry.yml").write_text(
        "entries:\n  - id: api\n    path: src/api.py\n    status: active\n",
        encoding="utf-8",
    )
    (root / "_meta" / "_data_registry.yml").write_text(
        "assets:\n  - id: sample\n    path: _data/sample.csv\n",
        encoding="utf-8",
    )
    (root / "_data").mkdir()
    (root / "_data" / "sample.csv").write_text("x\n", encoding="utf-8")
    (root / "src").mkdir()
    (root / "src" / "api.py").write_text("def api():\n    return 1\n", encoding="utf-8")
    (root / "_codemap.md").write_text("# Map\n\n## Current work\nship stuff\n", encoding="utf-8")


def test_topic_brief_reports_all_six_columns(tmp_path: Path) -> None:
    write_v4_project(tmp_path)

    result = run_script("topic-brief.py", tmp_path)

    assert result.returncode == 0
    assert "[Topic Brief]" in result.stdout
    for label in ("plan:", "code:", "tests:", "wiki:", "fs:", "data:"):
        assert label in result.stdout
    assert "entries=1" in result.stdout
    assert "assets=1 missing_paths=0" in result.stdout
    assert "closeout: if this turn changes code/data/tests/assets/structure" in result.stdout
    assert "topic-closeout + topic-doctor" in result.stdout


def test_topic_doctor_detects_state_drift_and_registry_schema(tmp_path: Path) -> None:
    write_v4_project(tmp_path)

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "warn\tSTATE_DRIFT\t_codemap.md:" in result.stdout
    assert "info\tREGISTRY_SCHEMA\t_meta/_registry.yml\tentries total=1" in result.stdout


def test_topic_brief_supports_legacy_top_and_wiki_index(tmp_path: Path) -> None:
    (tmp_path / "wiki-methodology" / "top").mkdir(parents=True)
    (tmp_path / "wiki-methodology" / "top" / "task_plan.md").write_text(
        "# Plan\n\n> **Current: [P2.1] legacy**\n> Done Criteria: legacy gate\n",
        encoding="utf-8",
    )
    (tmp_path / "wiki-methodology" / "wiki").mkdir(parents=True)
    (tmp_path / "wiki-methodology" / "INDEX.md").write_text("# Index\n", encoding="utf-8")
    (tmp_path / "wiki-methodology" / "tests").mkdir(parents=True)
    (tmp_path / "wiki-methodology" / "tests" / "README.md").write_text("# Tests\n", encoding="utf-8")
    (tmp_path / "_meta").mkdir()
    (tmp_path / "_meta" / "_registry.yml").write_text(
        "plugin_tools:\n  - name: demo\n",
        encoding="utf-8",
    )
    (tmp_path / "_meta" / "_data_registry.yml").write_text("datasets: []\n", encoding="utf-8")
    (tmp_path / "_codemap.md").write_text("# Map\n", encoding="utf-8")

    result = run_script("topic-brief.py", tmp_path)

    assert result.returncode == 0
    assert "profile: legacy-compatible" in result.stdout
    assert "plan: legacy-compatible:wiki-methodology/top/task_plan.md" in result.stdout
    assert "plugin_tools=1" in result.stdout
    assert "entry=INDEX.md" in result.stdout


def test_topic_doctor_reports_nonstandard_plan_without_missing(tmp_path: Path) -> None:
    (tmp_path / "_top").mkdir()
    (tmp_path / "_top" / "_task_plan.md").write_text(
        "# Plan\n\n> **Current: [P3] custom**\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "PLAN_FOUND_NONSTANDARD\t_top/_task_plan.md" in result.stdout
    assert "PLAN_MISSING" not in result.stdout


def test_topic_brief_no_top_project_signals_do_not_exit_silently(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest"}}\n', encoding="utf-8")
    (tmp_path / "src").mkdir()

    result = run_script("topic-brief.py", tmp_path)

    assert result.returncode == 0
    assert "[Topic Brief]" in result.stdout
    assert "profile: active-software" in result.stdout
    assert "plan: plan=missing" in result.stdout


def test_topic_doctor_recognizes_wrapper_registry_schema(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    (tmp_path / "_meta" / "_registry.yml").write_text(
        "code_domains:\n  ui:\n    path: src/ui\ncross_domain_edges:\n  - from: ui\n    to: api\n",
        encoding="utf-8",
    )

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "REGISTRY_SCHEMA_UNKNOWN" not in result.stdout
    assert "code_domains+cross_domain_edges total=2" in result.stdout


def test_topic_doctor_ignores_negative_state_pointer(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    (tmp_path / "_codemap.md").write_text(
        "# Map\n\nThis is not the current queue; see _task_plan.md.\n",
        encoding="utf-8",
    )

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "STATE_DRIFT" not in result.stdout


def test_topic_doctor_downgrades_full_v4_gaps_for_public_mini(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Public docs\n", encoding="utf-8")

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "info\tPROFILE_SUGGESTED\t" in result.stdout
    assert "public-contrib" in result.stdout
    assert "warn\tREGISTRY_MISSING" not in result.stdout
    assert "info\tREGISTRY_MISSING" in result.stdout


def test_top_md_is_legacy_compatible_not_mini(tmp_path: Path) -> None:
    (tmp_path / "TOP.md").write_text("# Old TOP\n", encoding="utf-8")

    result = run_script("topic-brief.py", tmp_path)

    assert result.returncode == 0
    assert "profile: legacy-compatible" in result.stdout
    assert "plan: legacy-compatible:TOP.md" in result.stdout


def test_topic_doctor_checks_entrypoint_paths(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    (tmp_path / "_meta" / "_registry.yml").write_text(
        "entrypoints:\n  - id: missing\n    path: src/missing.py\n",
        encoding="utf-8",
    )

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "REGISTRY_SCHEMA\t_meta/_registry.yml\tentrypoints total=1" in result.stdout
    assert "warn\tREGISTRY_PATH_MISSING\t_meta/_registry.yml\t1 registered paths do not exist" in result.stdout


def test_topic_doctor_flags_current_state_even_with_generic_see(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    (tmp_path / "_codemap.md").write_text(
        "# Map\n\nCurrent state: blocked on auth; see issue #1.\n",
        encoding="utf-8",
    )

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "warn\tSTATE_DRIFT\t_codemap.md:" in result.stdout


def test_topic_brief_finds_no_top_software_root_from_nested_dir(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"scripts":{"test":"vitest"}}\n', encoding="utf-8")
    nested = tmp_path / "src" / "feature"
    nested.mkdir(parents=True)

    result = run_script("topic-brief.py", nested)

    assert result.returncode == 0
    assert f"project: {tmp_path}" in result.stdout
    assert "profile: active-software" in result.stdout


def test_v4_template_passes_wiki_entry_check() -> None:
    template = SKILL_DIR / "templates" / "v4-architecture"

    doctor = run_script("topic-doctor.py", template, "--format", "tsv")
    brief = run_script("topic-brief.py", template)

    assert doctor.returncode == 0
    assert "WIKI_ENTRY_MISSING" not in doctor.stdout
    assert "entry=_readme.md" in brief.stdout


def test_topic_brief_reports_complex_software_capabilities(tmp_path: Path) -> None:
    (tmp_path / "wiki-methodology" / "top").mkdir(parents=True)
    (tmp_path / "wiki-methodology" / "top" / "task_plan.md").write_text("# Plan\n", encoding="utf-8")
    (tmp_path / "_meta").mkdir()
    (tmp_path / "_meta" / "_registry.yml").write_text(
        "plugin_tools:\n  - name: plugin\nscenarios:\n  - id: s1\ncontract_tests:\n  - id: c1\n",
        encoding="utf-8",
    )
    (tmp_path / "_meta" / "_data_registry.yml").write_text("assets: []\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "test-all.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    result = run_script("topic-brief.py", tmp_path)

    assert result.returncode == 0
    assert "profile: legacy-compatible" in result.stdout
    assert "capabilities: active-complex-software" in result.stdout
    assert "plugins" in result.stdout
    assert "test-gate-script" in result.stdout


def test_topic_doctor_detects_root_clutter_and_sandbox_drift(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    (tmp_path / "orphan.png").write_bytes(b"png")
    (tmp_path / "_sandbox").mkdir()
    (tmp_path / "_sandbox" / "_index.yml").write_text("experiments: []\n", encoding="utf-8")
    (tmp_path / "_sandbox" / "exp1").mkdir()

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv")

    assert "warn\tROOT_CLUTTER\t.\t1 top-level files look like orphan artifacts" in result.stdout
    assert "warn\tSANDBOX_INDEX_DRIFT\t_sandbox/_index.yml\t1 sandbox dirs are not indexed" in result.stdout


def test_topic_doctor_warns_when_software_trace_exists_without_ssdo_entry(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    (tmp_path / "_outputs" / "traces").mkdir(parents=True)
    (tmp_path / "_outputs" / "traces" / "report.json").write_text('{"ok": true}\n', encoding="utf-8")

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "warn\tSSDO_ENTRY_MISSING\t_wiki-methodology/_tests/_ssdo_protocol.md" in result.stdout


def test_topic_doctor_allows_software_trace_with_ssdo_entry(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    (tmp_path / "_outputs" / "traces").mkdir(parents=True)
    (tmp_path / "_outputs" / "traces" / "timeline.jsonl").write_text("{}\n", encoding="utf-8")
    (tmp_path / "_wiki-methodology" / "_tests" / "_ssdo_protocol.md").write_text(
        "# SSDO\n\nAudit-first reader: `python scripts/audit.py last`\n",
        encoding="utf-8",
    )

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "SSDO_ENTRY_MISSING" not in result.stdout
    assert "info\tSSDO_ENTRY\t_wiki-methodology/_tests" in result.stdout


def test_topic_doctor_blocks_complex_software_without_ssdo_entry(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "test-all.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (tmp_path / "_meta" / "_registry.yml").write_text(
        "plugin_tools:\n  - name: plugin\nscenarios:\n  - id: s1\ncontract_tests:\n  - id: c1\n",
        encoding="utf-8",
    )

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 1
    assert "block\tSSDO_ENTRY_MISSING\t_wiki-methodology/_tests/_ssdo_protocol.md" in result.stdout


def test_topic_doctor_links_accepts_declared_owner_refs(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    (tmp_path / "_wiki-methodology" / "_tests" / "_api.md").write_text(
        "---\nid: test:api\nstatus: active\n---\n\n# API test\n",
        encoding="utf-8",
    )
    (tmp_path / "_codemap.md").write_text(
        "# Map\n\n- code:api is covered by test:api and uses data:sample.\n",
        encoding="utf-8",
    )

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv", "--links")

    assert result.returncode == 0
    assert "REF_DANGLING" not in result.stdout
    assert "info\tREF_SCHEMA\t.\tdeclared_refs=" in result.stdout


def test_topic_doctor_links_blocks_dangling_refs(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    (tmp_path / "_codemap.md").write_text("# Map\n\n- code:api is covered by test:missing.\n", encoding="utf-8")

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv", "--links")

    assert result.returncode == 1
    assert "block\tREF_DANGLING\t_codemap.md:3\ttest:missing is not declared by its owner" in result.stdout


def test_topic_doctor_links_blocks_duplicate_declared_refs(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    (tmp_path / "_meta" / "_data_registry.yml").write_text(
        "assets:\n"
        "  - id: sample\n"
        "    path: _data/sample.csv\n"
        "  - id: sample\n"
        "    path: _data/sample.csv\n",
        encoding="utf-8",
    )

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv", "--links")

    assert result.returncode == 1
    assert "block\tREF_DUPLICATE\t_meta/_data_registry.yml, _meta/_data_registry.yml\tdata:sample declared 2 times" in result.stdout


def test_topic_doctor_links_numeric_summary_keys_are_not_dup_refs(tmp_path: Path) -> None:
    # `total:` summary counts under two registry sections must NOT mint a phantom
    # `code:total` ref that false-fires REF_DUPLICATE; a genuine duplicate id must
    # still fire so the numeric-skip does not gut the real check.
    write_v4_project(tmp_path)
    (tmp_path / "_meta" / "_registry.yml").write_text(
        "plugin_tools:\n"
        "  source_file: src/main.py\n"
        "  total: 22\n"
        "  tools:\n"
        "    - id: tool_a\n"
        "scenarios:\n"
        "  source: _meta/scenarios.yml\n"
        "  total: 30\n"
        "entries:\n"
        "  - id: api\n"
        "    path: src/api.py\n"
        "  - id: dupe\n"
        "    path: src/api.py\n"
        "  - id: dupe\n"
        "    path: src/api.py\n",
        encoding="utf-8",
    )

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv", "--links")

    assert "code:total declared" not in result.stdout
    assert "code:dupe declared 2 times" in result.stdout
    assert result.returncode == 1


def test_topic_doctor_links_container_sections_mint_inner_ids_not_metadata(tmp_path: Path) -> None:
    # A container section (dict with an inner `tools` list) must mint the REAL
    # resource ids from the list — and must NOT mint sibling metadata keys
    # (source_file / cache_protocol / the literal word `tools`) as phantom refs.
    # Phantom refs both false-fire REF_DUPLICATE across sections and silently
    # whitelist dangling codemap refs (self-review A-F1/F2/F3).
    write_v4_project(tmp_path)
    (tmp_path / "_meta" / "_registry.yml").write_text(
        "plugin_tools:\n"
        "  source_file: src/main.py\n"
        "  cache_protocol:\n"
        "    - one\n"
        "  total: 22\n"
        "  tools:\n"
        "    - id: parse_file\n"
        "    - id: classify_rock\n",
        encoding="utf-8",
    )
    # codemap references the real inner tool id -> must be accepted as declared;
    # a metadata-key ref must now be DANGLING (it is not a declared resource).
    (tmp_path / "_codemap.md").write_text(
        "# Map\n\n- code:parse_file does parsing.\n- code:source_file is fake.\n",
        encoding="utf-8",
    )

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv", "--links")

    assert "code:parse_file is not declared" not in result.stdout  # real id minted
    assert "code:source_file is not declared" in result.stdout      # phantom gone -> dangling
    assert "code:tools" not in result.stdout                         # literal key not minted


def test_topic_doctor_links_warns_retired_ref_without_exit(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    (tmp_path / "_meta" / "_registry.yml").write_text(
        "entries:\n  - id: old_api\n    path: src/api.py\n    status: deprecated\n",
        encoding="utf-8",
    )

    result = run_script("topic-doctor.py", tmp_path, "--format", "tsv", "--links")

    assert result.returncode == 0
    assert "warn\tREF_RETIRED_WITHOUT_EXIT\t_meta/_registry.yml\tcode:old_api status=deprecated needs superseded_by or retire_reason" in result.stdout


def init_git(root: Path) -> None:
    subprocess.run(["git", "init"], cwd=root, text=True, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, text=True, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Topic Test"], cwd=root, text=True, capture_output=True, check=True)
    subprocess.run(["git", "add", "."], cwd=root, text=True, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=root, text=True, capture_output=True, check=True)


def test_topic_closeout_blocks_code_change_without_owner_updates(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    init_git(tmp_path)
    (tmp_path / "src" / "new_feature.py").write_text("def run():\n    return 2\n", encoding="utf-8")

    result = run_script("topic-closeout.py", tmp_path, "--format", "tsv")

    assert result.returncode == 1
    assert "block\tCLOSEOUT_CODEMAP_MISSING\t_codemap.md" in result.stdout
    assert "block\tCLOSEOUT_REGISTRY_MISSING\t_meta/_registry.yml" in result.stdout
    assert "warn\tCLOSEOUT_TEST_GATE_MISSING" in result.stdout
    assert "warn\tCLOSEOUT_PLAN_NOT_TOUCHED" in result.stdout


def test_topic_closeout_skips_non_topic_project(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('base')\n", encoding="utf-8")
    init_git(tmp_path)
    (tmp_path / "src" / "new_feature.py").write_text("def run():\n    return 2\n", encoding="utf-8")

    result = run_script("topic-closeout.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert result.stdout == ""


def test_topic_closeout_requires_codemap_and_registry_together(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    init_git(tmp_path)
    (tmp_path / "src" / "new_feature.py").write_text("def run():\n    return 2\n", encoding="utf-8")
    (tmp_path / "_codemap.md").write_text("# Map\n\n- src/new_feature.py\n", encoding="utf-8")

    codemap_only = run_script("topic-closeout.py", tmp_path, "--format", "tsv")

    assert codemap_only.returncode == 1
    assert "CLOSEOUT_CODEMAP_MISSING" not in codemap_only.stdout
    assert "block\tCLOSEOUT_REGISTRY_MISSING\t_meta/_registry.yml" in codemap_only.stdout

    subprocess.run(["git", "checkout", "--", "_codemap.md"], cwd=tmp_path, text=True, capture_output=True, check=True)
    (tmp_path / "_meta" / "_registry.yml").write_text(
        "entries:\n  - id: new_feature\n    path: src/new_feature.py\n",
        encoding="utf-8",
    )

    registry_only = run_script("topic-closeout.py", tmp_path, "--format", "tsv")

    assert registry_only.returncode == 1
    assert "block\tCLOSEOUT_CODEMAP_MISSING\t_codemap.md" in registry_only.stdout
    assert "CLOSEOUT_REGISTRY_MISSING" not in registry_only.stdout


def test_topic_closeout_accepts_code_change_with_owner_updates(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    init_git(tmp_path)
    (tmp_path / "src" / "new_feature.py").write_text("def run():\n    return 2\n", encoding="utf-8")
    (tmp_path / "_codemap.md").write_text("# Map\n\n- src/new_feature.py\n", encoding="utf-8")
    (tmp_path / "_meta" / "_registry.yml").write_text(
        "entries:\n  - id: new_feature\n    path: src/new_feature.py\n",
        encoding="utf-8",
    )
    (tmp_path / "_wiki-methodology" / "_tests" / "_coverage.md").write_text(
        "# Coverage\n\n- new_feature: unit pending\n",
        encoding="utf-8",
    )
    (tmp_path / "_wiki-methodology" / "_top" / "_task_plan.md").write_text(
        "# Plan\n\n> **Current: [P1.1] ship new feature**\n> Done Criteria: code + owner updates\n",
        encoding="utf-8",
    )

    result = run_script("topic-closeout.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "CLOSEOUT_CODEMAP_MISSING" not in result.stdout
    assert "CLOSEOUT_REGISTRY_MISSING" not in result.stdout
    assert "CLOSEOUT_TEST_GATE_MISSING" not in result.stdout
    assert "CLOSEOUT_PLAN_NOT_TOUCHED" not in result.stdout


def test_topic_closeout_warns_trace_sensitive_code_change_needs_ssdo_evidence(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    (tmp_path / "_wiki-methodology" / "_tests" / "_ssdo_protocol.md").write_text(
        "# SSDO\n\nAudit-first reader: `python scripts/audit.py last`\n",
        encoding="utf-8",
    )
    init_git(tmp_path)
    (tmp_path / "src" / "trace_reader.py").write_text("def run():\n    return 'trace'\n", encoding="utf-8")
    (tmp_path / "_codemap.md").write_text("# Map\n\n- src/trace_reader.py\n", encoding="utf-8")
    (tmp_path / "_meta" / "_registry.yml").write_text(
        "entries:\n  - id: trace_reader\n    path: src/trace_reader.py\n",
        encoding="utf-8",
    )
    (tmp_path / "_wiki-methodology" / "_tests" / "_coverage.md").write_text(
        "# Coverage\n\nTrace/SSDO audit: `python scripts/audit.py last`\n",
        encoding="utf-8",
    )
    (tmp_path / "_wiki-methodology" / "_top" / "_task_plan.md").write_text(
        "# Plan\n\n> **Current: [P1.1] ship trace reader**\n> Done Criteria: command gate + trace audit\n",
        encoding="utf-8",
    )

    result = run_script("topic-closeout.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "warn\tCLOSEOUT_SSDO_EVIDENCE_NEEDED\t_wiki-methodology/_tests" in result.stdout


def test_topic_closeout_blocks_data_change_without_data_registry(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    init_git(tmp_path)
    (tmp_path / "_data" / "new.csv").write_text("x\n2\n", encoding="utf-8")

    result = run_script("topic-closeout.py", tmp_path, "--format", "tsv")

    assert result.returncode == 1
    assert "block\tCLOSEOUT_DATA_OWNER_MISSING\t_meta/_data_registry.yml" in result.stdout


def test_finding_doctor_blocks_closed_finding_without_evidence(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    findings = tmp_path / "_wiki-methodology" / "_top" / "_findings"
    findings.mkdir()
    (findings / "_2026-06-06_fixed.md").write_text(
        "---\nstatus: fixed\nowner_col: COL4\n---\n\n# Fixed\n",
        encoding="utf-8",
    )

    result = run_script("finding-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 1
    assert "block\tFINDING_CLOSURE_MISSING" in result.stdout


def test_finding_doctor_warns_active_finding_missing_owner(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    findings = tmp_path / "_wiki-methodology" / "_top" / "_findings"
    findings.mkdir()
    (findings / "_2026-06-06_open.md").write_text(
        "---\nstatus: open\nseverity: major\n---\n\n# Open\n",
        encoding="utf-8",
    )

    result = run_script("finding-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "warn\tFINDING_OWNER_MISSING" in result.stdout


def test_finding_doctor_allows_closed_finding_with_evidence(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    findings = tmp_path / "_wiki-methodology" / "_top" / "_findings"
    findings.mkdir()
    (findings / "_2026-06-06_fixed.md").write_text(
        "---\nstatus: fixed\nowner_col: COL4\nclosure_evidence: pytest passed\n---\n\n# Fixed\n",
        encoding="utf-8",
    )

    result = run_script("finding-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert result.stdout == ""


def test_finding_doctor_warns_pending_external_review(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    reviews = tmp_path / "_wiki-methodology" / "_top" / "_external_reviews"
    reviews.mkdir()
    (reviews / "_2026-06-06_claude.md").write_text(
        "---\nstatus: pending\nreviewer: claude\n---\n\n## Adoption Decision\n\npending\n",
        encoding="utf-8",
    )

    result = run_script("finding-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "warn\tREVIEW_ADOPTION_PENDING" in result.stdout


def test_finding_doctor_warns_when_active_findings_need_digest(tmp_path: Path) -> None:
    write_v4_project(tmp_path)
    findings = tmp_path / "_wiki-methodology" / "_top" / "_findings"
    findings.mkdir()
    for index in range(8):
        (findings / f"_2026-06-06_open_{index}.md").write_text(
            "---\nstatus: open\nowner_col: COL2\n---\n\n# Open\n",
            encoding="utf-8",
        )

    result = run_script("finding-doctor.py", tmp_path, "--format", "tsv")

    assert result.returncode == 0
    assert "warn\tFINDING_DIGEST_NEEDED" in result.stdout
