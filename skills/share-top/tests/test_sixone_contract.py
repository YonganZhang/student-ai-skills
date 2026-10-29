"""sixone CLI P0 契约测试 — 钉死脚本 --json envelope 的机器可读契约。

这是 sixone CLI 的地基测试:
任何 client 必须能只读 envelope 拿到 schema_version / verdict / issues, 不靠人读文本。
新增脚本 --json 或改 envelope 字段时, 必须同步这里, 否则 CLI client 会静默漂移。
"""
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
DOCTOR = SCRIPTS / "topic-doctor.py"
STATUS = SCRIPTS / "top-status.py"
BRIEF = SCRIPTS / "topic-brief.py"

VERDICT_ENUM = {"ok", "warn", "block"}  # doctor 级; 'stale' 由聚合层(closeout)补


def _json(script: Path, project: Path) -> dict:
    out = subprocess.run(
        [sys.executable, str(script), str(project), "--json"],
        capture_output=True, text=True,
    )
    return json.loads(out.stdout)


def _run_doctor_json(project: Path) -> dict:
    return _json(DOCTOR, project)


def _v4_skeleton(tmp_path: Path) -> Path:
    top = tmp_path / "_wiki-methodology" / "_top"
    top.mkdir(parents=True)
    (top / "_task_plan.md").write_text(
        "# plan\n🧭 当前 [P1.0] do a thing · 上 [P0] · 下 [P2]\n## Done Criteria\n- x\n"
    )
    (tmp_path / "_codemap.md").write_text("# map\n")
    return tmp_path


def test_doctor_json_is_valid_envelope(tmp_path):
    """--json 输出必须是合法 JSON, 且含契约要求的全部顶层字段。"""
    (tmp_path / "_wiki-methodology" / "_top").mkdir(parents=True)
    (tmp_path / "_wiki-methodology" / "_top" / "_task_plan.md").write_text("# plan\n")
    env = _run_doctor_json(tmp_path)
    assert env["schema_version"] == "sixone-doctor/v1"
    assert env["tool"] == "topic-doctor"
    assert env["verdict"] in VERDICT_ENUM
    assert set(env["summary"]) == {"block", "warn", "info"}
    assert isinstance(env["issues"], list)


def test_doctor_json_issue_shape(tmp_path):
    """每条 issue 必须有 client 依赖的 4 字段(severity/code/path/message)。"""
    env = _run_doctor_json(tmp_path)  # 空目录 → 必有 missing-layer issues
    assert env["issues"], "空项目应至少报缺层 issue"
    for issue in env["issues"]:
        assert set(issue) >= {"severity", "code", "path", "message"}
        assert issue["severity"] in {"block", "warn", "info"}


def test_doctor_verdict_matches_summary(tmp_path):
    """verdict 必须跟 summary 自洽: 有 block→block, 否则有 warn→warn, 否则 ok。"""
    env = _run_doctor_json(tmp_path)
    s = env["summary"]
    expected = "block" if s["block"] else ("warn" if s["warn"] else "ok")
    assert env["verdict"] == expected


def test_doctor_text_format_unchanged(tmp_path):
    """加 --json 不能动默认 text 输出(stop-hook/top-gate 仍解析它)。"""
    out = subprocess.run(
        [sys.executable, str(DOCTOR), str(tmp_path)],
        capture_output=True, text=True,
    ).stdout
    assert "SUMMARY:" in out and "block=" in out


def test_status_json_bounded_view(tmp_path):
    """top-status --json: sixone-status/v1, view 有界(recent_findings ≤ 5)。"""
    env = _json(STATUS, _v4_skeleton(tmp_path))
    assert env["schema_version"] == "sixone-status/v1"
    assert env["view"]["phase_id"] == "P1.0"
    assert len(env["view"]["recent_findings"]) <= 5  # 读时截断, 防上下文膨胀


def test_brief_json_envelope(tmp_path):
    """topic-brief --json: sixone-brief/v1, 含 profile/code/owners。"""
    env = _json(BRIEF, _v4_skeleton(tmp_path))
    assert env["schema_version"] == "sixone-brief/v1"
    assert env["bootstrap_needed"] is False
    assert "profile" in env and "owners" in env


def test_brief_bootstrap_on_empty(tmp_path):
    """空目录(无六合一信号) → bootstrap_needed=True, 不返回困惑空结果(补 L6)。"""
    env = _json(BRIEF, tmp_path)
    assert env["bootstrap_needed"] is True


def test_status_text_unchanged(tmp_path):
    """top-status 默认 text 输出不变。"""
    out = subprocess.run(
        [sys.executable, str(STATUS), str(_v4_skeleton(tmp_path))],
        capture_output=True, text=True,
    ).stdout
    assert "TOP Status:" in out and "## Current" in out


def test_sixone_version_ladder(tmp_path):
    """版本探测契约: 盘上特征派生 v4 / v4.5-partial / v4.5(不手写戳)。
    阶梯协议 references/upgrades/README.md 依赖这个枚举; 加 v5 必须同步这里。"""
    p = _v4_skeleton(tmp_path)
    env = _json(BRIEF, p)
    assert env["sixone_version"] == "v4"
    assert env["sixone_latest"]  # 常量存在即可, 不 pin 具体值(升级时别让测试挡路)
    # + gates manifest only → partial
    gates = p / "_wiki-methodology" / "_tests"
    gates.mkdir(parents=True)
    (gates / "_gates.yml").write_text("gates: []\n")
    assert _json(BRIEF, p)["sixone_version"] == "v4.5-partial"
    # + codebook node → v4.5
    cb = p / "_codebook"
    cb.mkdir()
    (cb / "main.md").write_text("---\ntitle: x\n---\nbody\n")
    assert _json(BRIEF, p)["sixone_version"] == "v4.5"
    # _index.md 不算节点(下划线前缀是导航/模板)
    (cb / "main.md").unlink()
    (cb / "_index.md").write_text("# toc\n")
    assert _json(BRIEF, p)["sixone_version"] == "v4.5-partial"
