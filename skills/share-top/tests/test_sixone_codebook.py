"""sixone CodeBook v4 测试: deposit_validate 闭集校验 + hash 盖章 + trust 派生。

钉死防伪造核心(v4 §3/§4):AI 不能手填 last_verified_hash 蒙混;盖章只由工具算;
trust 实时从 hash 派生(fresh/stale/broken/unverified)。
"""
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "core"))
import sixone_core as core  # noqa: E402


def _project(tmp_path: Path) -> Path:
    (tmp_path / "_meta").mkdir()
    (tmp_path / "_meta" / "_registry.yml").write_text(
        "functions:\n- id: track_atoms\n  name: main\n  module: _code/track.py\n"
    )
    code = tmp_path / "_code"
    code.mkdir()
    (code / "track.py").write_text("def main():\n    return 1\n")
    (tmp_path / "_codebook").mkdir()
    return tmp_path


def _good_node(tmp_path: Path) -> str:
    node = tmp_path / "_codebook" / "atom_tracking.md"
    node.write_text(
        "---\n"
        "title: Atom tracking system\n"
        "user_workflow: user runs the tracker on a tilt series\n"
        "owner_refs:\n  - code:track_atoms\n"
        "tracked_paths_hint:\n  - _code/track.py\n"
        "---\n"
        "# Atom tracking\nentry: `_code/track.py`\n"
    )
    return "_codebook/atom_tracking.md"


def test_validate_pass_stamps_hash(tmp_path):
    p = _project(tmp_path)
    rel = _good_node(p)
    r = core.deposit_validate(str(p), rel)
    assert r["verdict"] == "ok"
    assert len(r["stamped"]) == 64  # sha256 hex
    # 盖章真写进了 frontmatter
    assert "last_verified_hash" in (p / rel).read_text()


def test_trust_fresh_then_stale_then_broken(tmp_path):
    p = _project(tmp_path)
    rel = _good_node(p)
    core.deposit_validate(str(p), rel)
    node = p / rel
    assert core.codebook_trust(node, p) == "fresh"
    # 改 tracked 代码 → stale(hash 不符)
    (p / "_code" / "track.py").write_text("def main():\n    return 999\n")
    assert core.codebook_trust(node, p) == "stale"
    # 删 tracked 代码 → broken
    (p / "_code" / "track.py").unlink()
    assert core.codebook_trust(node, p) == "broken"


def test_unverified_when_no_stamp(tmp_path):
    """AI 没盖章(或手填被剥) → unverified, 不是 fresh。防"手填 hash 蒙混"。"""
    p = _project(tmp_path)
    rel = _good_node(p)
    assert core.codebook_trust(p / rel, p) == "unverified"


def test_fake_hash_is_caught(tmp_path):
    """AI 手填一个假 hash → trust 实时算必不符 → stale, 蒙混不过(v4 §0 健忘型根除)。"""
    p = _project(tmp_path)
    node = p / "_codebook" / "fake.md"
    node.write_text(
        "---\ntitle: x\nuser_workflow: y\nowner_refs:\n  - code:track_atoms\n"
        "tracked_paths_hint:\n  - _code/track.py\n"
        "last_verified_hash: deadbeef" + "0" * 56 + "\n---\nbody\n"
    )
    assert core.codebook_trust(node, p) == "stale"  # 假 hash 算出来不符


def test_validate_fail_returns_template_and_errors(tmp_path):
    """缺必填字段 → block + 逐条 error + 模板(actionable, 防死锁)。"""
    p = _project(tmp_path)
    node = p / "_codebook" / "bad.md"
    node.write_text("---\ntitle: x\n---\nbody\n")  # 缺 user_workflow/owner_refs/tracked
    r = core.deposit_validate(str(p), "_codebook/bad.md")
    assert r["verdict"] == "block"
    assert any(e["check"] == "a_schema" for e in r["errors"])
    assert "template" in r and "owner_refs" in r["template"]


def test_validate_fail_strips_handwritten_stamp(tmp_path):
    """失败时剥除手写 last_verified_hash(防藏在失败编辑里的伪造存活)。"""
    p = _project(tmp_path)
    node = p / "_codebook" / "bad2.md"
    node.write_text("---\ntitle: x\nlast_verified_hash: " + "a" * 64 + "\n---\nbody\n")
    core.deposit_validate(str(p), "_codebook/bad2.md")
    assert "last_verified_hash" not in node.read_text()  # 被剥


def test_doctor_surfaces_codebook_trust(tmp_path):
    """ledger_doctor 聚合 CodeBook 节点新鲜度: 改了 tracked 代码 → 节点 stale → verdict 升级。"""
    p = _project(tmp_path)
    # 给一个最小 v4 task_plan 让 topic-doctor 能跑
    top = p / "_wiki-methodology" / "_top"; top.mkdir(parents=True)
    (top / "_task_plan.md").write_text("# plan\n🧭 当前 [P1.0] x\n## Done Criteria\n- x\n")
    rel = _good_node(p)
    core.deposit_validate(str(p), rel)
    d1 = core.topic_doctor(str(p), full=True)
    assert d1["codebook"]["total"] == 1 and not d1["codebook"]["needs_attention"]
    # 改 tracked 代码 → 节点 stale → doctor 报出来 + verdict 至少 stale
    (p / "_code" / "track.py").write_text("def main():\n    return 999\n")
    d2 = core.topic_doctor(str(p), full=True)
    assert d2["codebook"]["needs_attention"][0]["trust"] == "stale"
    assert d2["verdict"] in ("stale", "block")
    assert d2["next_hint"]


# ───────── 三方 code-review 找到的 bug 的回归测试 ─────────

def test_scalar_field_gives_clear_error_not_char_garbage(tmp_path):
    """忘了写 '- ' (标量非列表) → 清晰"必须是列表"错, 不是逐字符垃圾(三方共识 bug)。"""
    p = _project(tmp_path)
    node = p / "_codebook" / "scalar.md"
    node.write_text(
        "---\ntitle: x\nuser_workflow: y\nowner_refs: code:track_atoms\n"
        "tracked_paths_hint: _code/track.py\n---\nbody\n"
    )
    r = core.deposit_validate(str(p), "_codebook/scalar.md")
    assert r["verdict"] == "block"
    # 报"必须是列表", 不是一堆单字符 c_tracked_missing
    assert any("列表" in e.get("detail", "") for e in r["errors"])


def test_tracked_directory_rejected(tmp_path):
    """tracked 指目录 → block(不是 exists 通过但 hash 跳过→假 fresh, Codex+Gemini 洞)。"""
    p = _project(tmp_path)
    node = p / "_codebook" / "dir.md"
    node.write_text(
        "---\ntitle: x\nuser_workflow: y\nowner_refs:\n  - code:track_atoms\n"
        "tracked_paths_hint:\n  - _code\n---\nbody\n"  # _code 是目录
    )
    r = core.deposit_validate(str(p), "_codebook/dir.md")
    assert r["verdict"] == "broken"
    assert core.codebook_trust(node, p) == "broken"


def test_tracked_traversal_rejected(tmp_path):
    """tracked 用 .. 或绝对路径越界 → block(Gemini path-traversal 假 fresh 洞)。"""
    p = _project(tmp_path)
    node = p / "_codebook" / "trav.md"
    node.write_text(
        "---\ntitle: x\nuser_workflow: y\nowner_refs:\n  - code:track_atoms\n"
        "tracked_paths_hint:\n  - ../../../etc/hostname\n---\nbody\n"
    )
    r = core.deposit_validate(str(p), "_codebook/trav.md")
    assert r["verdict"] == "broken"


def test_change_frontmatter_after_stamp_goes_stale(tmp_path):
    """盖章后改 owner_refs/title → hash 变 → stale(修 Codex"戳未绑校验元数据")。"""
    p = _project(tmp_path)
    rel = _good_node(p)
    core.deposit_validate(str(p), rel)
    node = p / rel
    assert core.codebook_trust(node, p) == "fresh"
    # 手改 title(frontmatter 散文)→ 应 stale(hash 绑了 frontmatter 子集)
    t = node.read_text().replace("title: Atom tracking system", "title: HACKED")
    node.write_text(t)
    assert core.codebook_trust(node, p) == "stale"


def test_owner_ref_unresolvable_is_broken(tmp_path):
    """owner_ref 解析不了 → broken(codebook_trust 该分支 round-2 没覆盖)。"""
    p = _project(tmp_path)
    node = p / "_codebook" / "badref.md"
    node.write_text(
        "---\ntitle: x\nuser_workflow: y\nowner_refs:\n  - code:nonexistent_fn\n"
        "tracked_paths_hint:\n  - _code/track.py\nlast_verified_hash: " + "a"*64 + "\n---\nbody\n"
    )
    assert core.codebook_trust(node, p) == "broken"


def test_code_ref_by_name_rejected(tmp_path):
    """code:<name> 应被拒(只按 id), 防 code:main 歧义(Codex bug 4)。"""
    p = _project(tmp_path)  # registry: id=track_atoms, name=main
    assert core._resolve_owner_ref("code:main", p) is False
    assert core._resolve_owner_ref("code:track_atoms", p) is True


def test_hash_stable_across_tricky_bodies(tmp_path):
    """盖章后立刻读回应 fresh: 中文 + 正文含 '---' 横线 + 无结尾换行(hash 稳定性回归)。"""
    p = _project(tmp_path)
    node = p / "_codebook" / "tricky.md"
    node.write_text(
        "---\ntitle: 原子追踪\nuser_workflow: 师兄跑追踪\nowner_refs:\n  - code:track_atoms\n"
        "tracked_paths_hint:\n  - _code/track.py\n---\n中文正文\n\n---\n\n分隔线后还有内容"  # 无结尾 \n
    )
    r = core.deposit_validate(str(p), "_codebook/tricky.md")
    assert r["verdict"] == "ok"
    assert core.codebook_trust(node, p) == "fresh"  # 写回再读字节级一致


def test_dead_link_in_code_fence_not_flagged(tmp_path):
    """代码块里的链接不算断链(Codex+Gemini 误报); 带 title 的有效链接也不误报。"""
    p = _project(tmp_path)
    node = p / "_codebook" / "links.md"
    node.write_text(
        "---\ntitle: x\nuser_workflow: y\nowner_refs:\n  - code:track_atoms\n"
        "tracked_paths_hint:\n  - _code/track.py\n---\n"
        "valid: [t](_code/track.py \"标题\")\n```\n[fake](does/not/exist.py)\n```\n"
    )
    r = core.deposit_validate(str(p), "_codebook/links.md")
    assert r["verdict"] == "ok"  # 两个都不该报断链 → 顺利盖章
