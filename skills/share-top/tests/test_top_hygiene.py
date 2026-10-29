"""top-hygiene.py behavior tests in disposable Git repositories under tmp_path."""
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'top-hygiene.py'
_spec = importlib.util.spec_from_file_location('top_hygiene', SCRIPT)
h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h)

OLD = '2020-01-01T00:00:00+0000'


def git(root, *args, env=None):
    return subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True, text=True,
                          env={**os.environ, **(env or {})}).stdout.strip()


def commit(root, name, text, msg, old=False):
    (Path(root) / name).write_text(text)
    git(root, 'add', name)
    env = {'GIT_AUTHOR_DATE': OLD, 'GIT_COMMITTER_DATE': OLD} if old else None
    git(root, 'commit', '-q', '-m', msg, env=env)


@pytest.fixture
def ws(tmp_path):
    """projects root with one main repo and worktrees in every class."""
    root = tmp_path / 'projects'
    repo = root / 'repo'
    repo.mkdir(parents=True)
    git(repo, 'init', '-q', '-b', 'main')
    git(repo, 'config', 'user.email', 'test@example.invalid')
    git(repo, 'config', 'user.name', 'Test')
    commit(repo, 'a.txt', 'base\n', 'base')
    wt = root / '_worktrees'
    # merged + clean -> SAFE
    git(repo, 'worktree', 'add', '-q', '-b', 'done', str(wt / 'done'))
    # merged + dirty -> REVIEW
    git(repo, 'worktree', 'add', '-q', '-b', 'dirty', str(wt / 'dirty'))
    (wt / 'dirty' / 'wip.txt').write_text('wip\n')
    # unmerged + old -> REVIEW
    git(repo, 'worktree', 'add', '-q', '-b', 'stale', str(wt / 'stale'))
    commit(wt / 'stale', 's.txt', 's\n', 'stale work', old=True)
    # unmerged + recent -> KEEP, located under .claude/worktrees/
    git(repo, 'worktree', 'add', '-q', '-b', 'active', str(repo / '.claude' / 'worktrees' / 'active'))
    commit(repo / '.claude' / 'worktrees' / 'active', 'n.txt', 'n\n', 'active work')
    # branches without worktrees
    git(repo, 'branch', 'merged-free')
    git(repo, 'checkout', '-q', '-b', 'old-unmerged')
    commit(repo, 'o.txt', 'o\n', 'old', old=True)
    git(repo, 'checkout', '-q', 'main')
    return root, repo


def by_path(report):
    return {Path(w['path']).name: w for w in report['worktrees']}


def by_branch(report):
    return {b['name']: b for b in report['branches']}


def test_worktree_classes_and_locations(ws):
    root, repo = ws
    r = h.scan_repo(repo, root)
    assert r['base'] == 'main' and r['base_reason'] == '本地 main'
    w = by_path(r)
    assert w['repo']['main'] and w['repo']['class'] == 'KEEP'
    assert w['done']['class'] == 'SAFE' and w['done']['merged'] and w['done']['clean']
    assert w['dirty']['class'] == 'REVIEW' and w['dirty']['clean'] is False and w['dirty']['dirty_count'] == 1
    assert w['stale']['class'] == 'REVIEW' and w['stale']['merged'] is False and w['stale']['head_age_days'] > 14
    assert w['active']['class'] == 'KEEP' and w['active']['merged'] is False
    assert w['done']['location'] == '~/projects/_worktrees/'
    assert w['active']['location'] == '.claude/worktrees/'
    assert w['repo']['location'] == '其他'


def test_branch_classes(ws):
    root, repo = ws
    b = by_branch(h.scan_repo(repo, root))
    assert b['merged-free']['class'] == 'SAFE'
    assert b['old-unmerged']['class'] == 'REVIEW'
    assert b['main']['class'] == 'KEEP' and '当前分支' in b['main']['notes']
    # merged but checked out in a worktree is never SAFE
    assert b['done']['merged'] and b['done']['worktree'] and b['done']['class'] == 'KEEP'
    assert b['active']['class'] == 'KEEP'  # unmerged but recent


def test_stash_and_uncommitted(ws):
    root, repo = ws
    (repo / 'a.txt').write_text('changed\n')
    git(repo, 'stash', 'push', '-q', '-m', 'keep me')
    (repo / 'a.txt').write_text('changed again\n')
    (repo / 'data').mkdir()
    for i in range(3):
        (repo / 'data' / f'f{i}.csv').write_text('x')
    with open(repo / 'data' / 'big.bin', 'wb') as f:  # sparse 51 MB
        f.truncate(51 * 1024 * 1024)
    r = h.scan_repo(repo, root)
    assert len(r['stashes']) == 1 and 'keep me' in r['stashes'][0]['message']
    assert r['stashes'][0]['age_days'] is not None
    u = r['uncommitted']
    # `.claude/` holds a linked worktree -> untracked; data/ collapsed to one entry
    assert u['tracked'] == 1 and u['count'] == u['tracked'] + u['untracked']
    assert u['untracked_files'] >= 4
    assert dict(u['top_dirs'])['data/'] == 1
    assert [p for p, _ in u['big_untracked']] == ['data/big.bin']


def test_base_prefers_origin_head_then_current_branch(tmp_path):
    src = tmp_path / 'src'
    src.mkdir()
    git(src, 'init', '-q', '-b', 'trunkish')
    git(src, 'config', 'user.email', 't@example.invalid')
    git(src, 'config', 'user.name', 'T')
    commit(src, 'a', 'a', 'a')
    assert h.detect_base(src) == ('trunkish', '主 worktree 当前分支')
    clone = tmp_path / 'clone'
    subprocess.run(['git', 'clone', '-q', str(src), str(clone)], check=True)
    assert h.detect_base(clone) == ('origin/trunkish', 'origin/HEAD')


def test_all_summary_and_json_skip_linked_worktrees(ws, capsys):
    root, repo = ws
    (root / 'not-a-repo').mkdir()
    assert [p.name for p in h.discover(root)] == ['repo']
    assert h.main(['--all', '--root', str(root), '--summary']) == 0
    out = capsys.readouterr().out
    rows = [ln for ln in out.splitlines() if ln.startswith('| repo ')]
    assert len(rows) == 1 and '| 5 | 1/2/2 |' in rows[0]
    assert '### Worktrees' not in out
    assert h.main(['--all', '--root', str(root), '--json']) == 0
    data = json.loads(capsys.readouterr().out)
    assert [r['name'] for r in data['repos']] == ['repo']
    # a linked worktree path maps back to its main repo
    assert h.repo_root(root / '_worktrees' / 'done') == repo


def test_markdown_report_lists_sections(ws, capsys):
    root, repo = ws
    assert h.main([str(repo), '--root', str(root)]) == 0
    out = capsys.readouterr().out
    for s in ('基准分支: `main`', '### Worktrees (5)', '### 分支', '### Stash (0)', '### 未提交改动'):
        assert s in out
    assert '| SAFE | `' in out and '`merged-free`' in out


def test_apply_safe_requires_yes(ws):
    root, repo = ws
    with pytest.raises(SystemExit) as e:
        h.main([str(repo), '--root', str(root), '--apply-safe'])
    assert e.value.code == 2
    assert (root / '_worktrees' / 'done').is_dir()


def test_apply_safe_removes_only_safe(ws, capsys):
    root, repo = ws
    wt = root / '_worktrees'
    assert h.main([str(repo), '--root', str(root), '--apply-safe', '--yes']) == 0
    out = capsys.readouterr().out
    assert '已移除 worktree' in out
    assert not (wt / 'done').exists()
    assert (wt / 'dirty' / 'wip.txt').exists() and (wt / 'stale').is_dir()
    assert (repo / '.claude' / 'worktrees' / 'active').is_dir()
    branches = set(git(repo, 'for-each-ref', '--format=%(refname:short)', 'refs/heads').split())
    # SAFE branch and the branch freed by the removed SAFE worktree are gone (-d)
    assert 'merged-free' not in branches and 'done' not in branches
    # everything else stays: occupied, unmerged, current
    assert {'main', 'dirty', 'stale', 'active', 'old-unmerged'} <= branches
    listed = git(repo, 'worktree', 'list', '--porcelain')
    assert str(wt / 'dirty') in listed and str(wt / 'done') not in listed


def test_apply_safe_skips_worktree_dirtied_after_scan(ws):
    root, repo = ws
    r = h.scan_repo(repo, root)
    assert by_path(r)['done']['class'] == 'SAFE'
    (root / '_worktrees' / 'done' / 'late.txt').write_text('late\n')
    log = h.apply_safe(r, root, 60)
    assert any('复核时非 clean' in x for x in log)
    assert (root / '_worktrees' / 'done' / 'late.txt').exists()


# ---------------------------------------------------------------- task branches

TASK_PLAN = """# Demo · Task Plan

🧭 当前 [P1.0] task=[P1.0.E1] Active task
> Done Criteria: hygiene knows task branches

## Current Coordinate

- Goal: test task branches
- Current task: P1.0.E1
- Next task: P1.0.E2
- Latest learning: none
- Blocker: none

## Active Work

- [ ] P1.0.E1 Active task · state=in_progress
- [ ] P1.0.E2 Pending task
- [ ] P1.0.E3 Blocked task · state=blocked · reason=waiting
- [x] P1.0.D1 Done merged · ev=_tests/d1.txt
- [x] P1.0.D2 Done unmerged · ev=_tests/d2.txt
- [x] P1.0.D3 Done branch only · ev=_tests/d3.txt
- [x] P1.0.D4 Done but dirty · ev=_tests/d4.txt
- [x] P1.0.C1 Cancelled task · state=cancelled · reason=dropped
"""


def task_wt(repo, tid):
    path = repo / '.worktrees' / tid
    git(repo, 'worktree', 'add', '-q', '-b', f'task/{tid}', str(path))
    return path


@pytest.fixture
def tws(tmp_path):
    """TOP project repo: plan in the main worktree, task/<ID> branches and .worktrees/<ID>."""
    root = tmp_path / 'projects'
    repo = root / 'proj'
    top = repo / '_wiki-methodology' / '_top'
    top.mkdir(parents=True)
    git(repo, 'init', '-q', '-b', 'main')
    git(repo, 'config', 'user.email', 'test@example.invalid')
    git(repo, 'config', 'user.name', 'Test')
    (repo / '.git' / 'info' / 'exclude').write_text('.worktrees/\n')
    (top / '_task_plan.md').write_text(TASK_PLAN, encoding='utf-8')
    git(repo, 'add', '.')
    git(repo, 'commit', '-q', '-m', 'plan')
    assert h.top_plan.validate(str(repo))['verdict'] == 'ok'
    task_wt(repo, 'P1.0.E1')                      # in_progress, merged + clean
    task_wt(repo, 'P1.0.E3')                      # blocked
    task_wt(repo, 'P1.0.D1')                      # done, merged + clean
    commit(task_wt(repo, 'P1.0.D2'), 'd2.txt', 'd2\n', 'd2 work')  # done, unmerged
    (task_wt(repo, 'P1.0.D4') / 'wip.txt').write_text('wip\n')     # done, merged, dirty
    git(repo, 'branch', 'task/P1.0.D3')           # done, merged, no worktree
    git(repo, 'branch', 'task/P1.0.C1')           # cancelled
    git(repo, 'branch', 'task/P1.0.X9')           # orphan: not in plan
    git(repo, 'branch', 'task/not-an-id')         # not a task ID -> generic rules
    git(repo, 'branch', 'merged-free')            # plain branch -> generic rules
    git(repo, 'checkout', '-q', '-b', 'task/P1.0.E2')  # pending, unmerged + old
    commit(repo, 'e2.txt', 'e2\n', 'old e2', old=True)
    git(repo, 'checkout', '-q', 'main')
    return root, repo


def test_task_classes_follow_plan_state(tws):
    root, repo = tws
    r = h.scan_repo(repo, root)
    assert not r['errors']
    w = {x['task_id']: x for x in r['worktrees'] if x['task_id']}
    b = by_branch(r)
    # in progress / pending / blocked -> KEEP even when merged+clean or unmerged+stale
    assert w['P1.0.E1']['class'] == 'KEEP' and w['P1.0.E1']['merged'] and w['P1.0.E1']['clean']
    assert w['P1.0.E1']['task_reason'] == '任务进行中' and w['P1.0.E1']['location'] == '.worktrees/(任务)'
    assert w['P1.0.E3']['class'] == 'KEEP' and w['P1.0.E3']['task_state'] == 'blocked'
    assert b['task/P1.0.E2']['class'] == 'KEEP' and b['task/P1.0.E2']['merged'] is False
    assert b['task/P1.0.E2']['age_days'] > 30 and b['task/P1.0.E2']['task_state'] == 'pending'
    # done + merged + clean -> SAFE; its occupied branch waits for the worktree removal
    assert w['P1.0.D1']['class'] == 'SAFE' and w['P1.0.D1']['task_reason'] == '任务已完成且已合并'
    assert b['task/P1.0.D1']['class'] == 'KEEP' and b['task/P1.0.D1']['worktree']
    assert b['task/P1.0.D3']['class'] == 'SAFE' and b['task/P1.0.D3']['task_reason'] == '任务已完成且已合并'
    # done + merged but dirty -> REVIEW
    assert w['P1.0.D4']['class'] == 'REVIEW' and w['P1.0.D4']['clean'] is False
    # done + unmerged -> REVIEW with plan merge hint
    for item in (w['P1.0.D2'], b['task/P1.0.D2']):
        assert item['class'] == 'REVIEW' and item['merged'] is False
        assert 'sixone-cli.py plan merge' in item['action'] and item['action'].endswith(f"{repo} P1.0.D2")
    # cancelled / orphan -> REVIEW
    assert b['task/P1.0.C1']['class'] == 'REVIEW' and b['task/P1.0.C1']['task_reason'] == '任务已取消，确认是否丢弃分支'
    assert b['task/P1.0.X9']['class'] == 'REVIEW' and b['task/P1.0.X9']['task_state'] is None
    assert b['task/P1.0.X9']['task_reason'].startswith('孤儿任务分支')
    # non-task branches keep the generic rules
    assert b['task/not-an-id']['task_id'] is None and b['task/not-an-id']['class'] == 'SAFE'
    assert b['merged-free']['class'] == 'SAFE' and b['merged-free']['task_id'] is None
    assert b['main']['class'] == 'KEEP'
    assert r['task_summary'] == {'total': 9, 'to_merge': 1, 'cleanable': 2}


def test_task_fields_in_json_summary_and_markdown(tws, capsys):
    root, repo = tws
    assert h.main([str(repo), '--root', str(root), '--json']) == 0
    data = json.loads(capsys.readouterr().out)
    b = {x['name']: x for x in data['repos'][0]['branches']}
    assert (b['task/P1.0.D2']['task_id'], b['task/P1.0.D2']['task_title'], b['task/P1.0.D2']['task_state']) == \
        ('P1.0.D2', 'Done unmerged', 'done')
    assert b['merged-free']['task_id'] is None and 'task_state' in b['merged-free']
    assert h.main([str(repo), '--root', str(root), '--summary']) == 0
    out = capsys.readouterr().out
    row = [ln for ln in out.splitlines() if ln.startswith('| proj ')][0]
    assert '| 9(待合并 1,可清理 2) |' in row and '### Worktrees' not in out
    assert h.main([str(repo), '--root', str(root)]) == 0
    out = capsys.readouterr().out
    assert '### 任务分支 (9)' in out and '孤儿任务分支' in out and 'plan merge' in out
    assert '| `P1.0.E1` | Active task | in_progress |' in out


def test_apply_safe_removes_only_finished_merged_tasks(tws, capsys):
    root, repo = tws
    assert h.main([str(repo), '--root', str(root), '--apply-safe', '--yes']) == 0
    wt = repo / '.worktrees'
    assert not (wt / 'P1.0.D1').exists()
    assert (wt / 'P1.0.E1').is_dir() and (wt / 'P1.0.E3').is_dir() and (wt / 'P1.0.D2').is_dir()
    assert (wt / 'P1.0.D4' / 'wip.txt').exists()
    branches = set(git(repo, 'for-each-ref', '--format=%(refname:short)', 'refs/heads').split())
    assert not {'task/P1.0.D1', 'task/P1.0.D3', 'merged-free', 'task/not-an-id'} & branches
    assert {'main', 'task/P1.0.E1', 'task/P1.0.E2', 'task/P1.0.E3', 'task/P1.0.D2', 'task/P1.0.D4',
            'task/P1.0.C1', 'task/P1.0.X9'} <= branches


def test_task_branch_without_plan_is_review_and_reported(tmp_path):
    root = tmp_path / 'projects'
    repo = root / 'noplan'
    repo.mkdir(parents=True)
    git(repo, 'init', '-q', '-b', 'main')
    git(repo, 'config', 'user.email', 'test@example.invalid')
    git(repo, 'config', 'user.name', 'Test')
    commit(repo, 'a.txt', 'a\n', 'a')
    git(repo, 'branch', 'task/P1.0.E1')
    r = h.scan_repo(repo, root)
    b = by_branch(r)['task/P1.0.E1']
    assert b['class'] == 'REVIEW' and b['merged'] and '计划文件缺失' in b['task_reason']
    assert any('计划文件缺失' in e for e in r['errors'])
