#!/usr/bin/env python3
"""`plan` — the short, text-first front end of the TOP plan CLI (for AIs and people).

Reads print a few plain lines instead of JSON (a phase view costs ~1/4 of `plan show`); writes
answer in one or two lines. Every command still goes through top_plan (CAS, invariants, log),
and `--json` prints the underlying JSON. Old-style `sixone-cli.py plan …` calls keep working:
an old subcommand, or a project path right after the verb, is handed to sixone-cli unchanged.

    plan                       core of the project here: goal, table of contents, doing, next, stuck
    plan 论文 | plan 25 | plan ~/projects/x     another project (name fragment / tmux window / path)
    plan [项目] 当前|上一|下一|全部|P3 [--细节]   one phase (summary + steps), optionally with details
    plan ls [--all]            one line per project
    plan help                  cheat sheet
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import top_plan  # noqa: E402
import top_qa  # noqa: E402
import top_qa_cli  # noqa: E402
from top_common import (  # noqa: E402
    PlanConflict, PlanError, current_phase, parse_plan, phase_state, phase_steps,
)

SCRIPTS = Path(__file__).resolve().parent
SIXONE = SCRIPTS / "sixone-cli.py"
PLAN_RELS = (Path("_wiki-methodology/_top/_task_plan.md"), Path("wiki-methodology/top/task_plan.md"))
PROJECTS_DIR = Path(os.environ.get("TOP_PROJECTS_DIR", Path.home() / "projects"))
# tmux session whose windows `plan ls` lists by bare index; others show as "session:index".
DEFAULT_TMUX_SESSION = os.environ.get("PLAN_TMUX_SESSION", "main")
STEP_ICONS = {"done": "✅", "in_progress": "▶", "pending": "☐", "blocked": "⏸", "cancelled": "✕"}
PHASE_ICONS = {"done": "✅", "in_progress": "🔄", "blocked": "⏸", "pending": "⏳", "cancelled": "✕"}
PHASE_STATE_TEXT = {"done": "完成", "in_progress": "进行中", "blocked": "卡住", "pending": "未开始", "cancelled": "放弃"}
SCOPES = {"当前": "current", "current": "current", "cur": "current", "上一": "prev", "prev": "prev",
          "previous": "prev", "下一": "next", "next": "next", "全部": "all", "all": "all"}
DETAIL_FLAGS = {"--细节", "--details", "-d"}
# Old sixone-cli subcommands without a short form: passed through as-is (JSON output).
PASSTHROUGH = {"show", "list", "validate", "next", "compact", "inspect", "handoff", "milestone", "merge", "edit"}

HELP = """plan — 计划的短命令（看的出人话短文字，改的回一两行；--json 出原始 JSON）

看（任何项目都能看；不写项目就是当前目录所在的项目）
  plan                        核心：目标、阶段目录、正在做、下一步、卡点
  plan 论文 | plan 25 | plan ~/projects/x    别的项目：名字里的几个字 / tmux 窗口号 / 路径
  plan [项目] 当前|上一|下一|全部|P3        看一个阶段的小结和步骤（current/prev/next/all 也行）
  plan [项目] P3 --细节        连同细节文章 _plan_details.md 里这一阶段的一节
  plan ls [--all]             各项目一行（默认只列开着窗口的项目）
  plan check                  检查计划（错误和可读性提醒；含版本）
  plan upgrade [--apply]      检查/升级项目 TOP 版本；无版本先检查内容

改（默认当前项目；改别的项目用 -p <路径|窗口号>，不接受模糊名字）
  plan add "一句人话" [--to P3] [--gate "怎样算做完"]    加一步（默认加到当前阶段末尾）
  plan insert P3.2 "一句人话" [--why "原因"]             紧跟在 P3.2 后面插一步
  plan start P3.2 | plan done P3.2 --ev "证据" [--commit] | plan done P3.2 --no-artifact "原因"
  plan block P3.2 "等谁/等什么" | plan cancel P3.2 "原因" | plan reopen P3.2
  plan replan P3.2 "为什么换" --with "新做法" [--with "…"]   换路线
  plan rename P3.2 "新说法"   （P3 这样的阶段 ID 就改阶段名）
  plan note "一句话" [--fail|--learn] [--on P3.2]          记一笔（进日志，不进计划）
  plan phase "阶段名" [--summary "为什么做"]              加一个阶段
  plan summary P3 "得到了什么，所以下一阶段做什么"         改阶段小结
  plan drop P3 "原因"          整段放弃
  plan goal "一两句：做完是什么样"
  plan archive [--keep N]      收起做完的阶段
  plan rewrite 草稿.md [--apply] [--accept-dropped]       整份改写（旧格式→目录格式也用它）

写法：只有 阶段→步骤 两层；标题写逻辑层的一句人话；技术细节写进 _top/_plan_details.md。
细则：~/.claude/skills/share-top/references/plan-writing.md
"""


class CliError(Exception):
    pass


# top_plan speaks English in a few errors (shared with the JSON CLI); the short CLI says it plainly.
_ERROR_TEXT = [
    (r"^unknown phase id: (\S+)", "没有阶段 {0}"),
    (r"^unknown (?:task|parent) id: (\S+)", "没有 {0} 这一步（plan 全部 看有哪些）"),
    (r"^complete requires --evidence or --no-artifact-reason", "完成要给证据：plan done <ID> --ev \"证据\"；没有产物就 --no-artifact \"原因\""),
    (r"^another task is already in_progress: (\S+)", "已经有一步在做（{0}）：先 plan done 或 plan block 它"),
    (r"^only pending task can start: (\S+) is (\S+)", "{0} 现在是 {1}，只有待办的步骤能开始"),
    (r"^dependencies are not closed: (.+)", "还要先做完：{0}"),
    (r"^duplicate task id: (\S+)", "{0} 已经有了"),
    (r"^open children prevent (?:completion|cancellation): (.+)", "下面还有没关的步骤：{0}"),
    (r"^task is already closed: (\S+)", "{0} 已经关了"),
    (r"^only done/cancelled/blocked task can reopen: (\S+) is (\S+)", "{0} 现在是 {1}，不用重开"),
    (r"^closed task cannot be edited: (\S+)", "{0} 已经关了，先 plan reopen 再改"),
]


def _plain(message: str) -> str:
    for pattern, text in _ERROR_TEXT:
        match = re.match(pattern, message)
        if match:
            return text.format(*match.groups())
    return message


# ---------- which project ----------

def _plan_root(start: Path) -> Path | None:
    """Nearest directory with a plan; a git worktree maps to its main worktree (the plan lives
    there, see top_plan._main_worktree_root), so every worktree of a project is one project."""
    start = start.expanduser().resolve()
    for directory in [start, *start.parents]:
        if any((directory / rel).is_file() for rel in PLAN_RELS):
            return top_plan._main_worktree_root(directory).resolve()
        if directory == Path.home() or directory.parent == directory:
            return None
    return None


def _tmux_windows() -> list[tuple[str, str, str, str]]:
    """(session, index, cwd, window name) of every tmux window; empty without tmux."""
    try:
        out = subprocess.run(
            ["tmux", "list-windows", "-a", "-F", "#{session_name}\t#{window_index}\t#{pane_current_path}\t#{window_name}"],
            capture_output=True, text=True, timeout=3, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 4:
            rows.append((parts[0], parts[1], parts[2], parts[3]))
    return rows


def _current_session() -> str:
    if not os.environ.get("TMUX"):
        return ""
    try:
        return subprocess.run(["tmux", "display-message", "-p", "#{session_name}"], capture_output=True,
                              text=True, timeout=3, stdin=subprocess.DEVNULL).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _by_window(index: str) -> Path:
    rows = [row for row in _tmux_windows() if row[1] == index]
    if len(rows) > 1:
        preferred = _current_session() or DEFAULT_TMUX_SESSION
        rows = [row for row in rows if row[0] == preferred] or rows
    if not rows:
        raise CliError(f"没有 {index} 号 tmux 窗口")
    if len(rows) > 1:
        raise CliError(f"{index} 号窗口不止一个：" + "、".join(f"{r[0]}:{r[1]}" for r in rows) + "；改用路径")
    root = _plan_root(Path(rows[0][2]))
    if root is None:
        raise CliError(f"{index} 号窗口（{rows[0][2]}）不在任何有计划的项目里")
    return root


def _by_name(fragment: str) -> Path:
    needle = fragment.lower()
    found: dict[Path, str] = {}
    if PROJECTS_DIR.is_dir():
        for child in sorted(PROJECTS_DIR.iterdir()):
            if needle in child.name.lower() and _plan_root(child) == child.resolve():
                found[child.resolve()] = child.name
    for _, index, cwd, name in _tmux_windows():
        if needle in name.lower():
            root = _plan_root(Path(cwd))
            if root is not None:
                found.setdefault(root, f"{root.name}（{index} 号窗口：{name}）")
    if not found:
        raise CliError(f"没找到名字里有「{fragment}」的项目；plan ls --all 看全部")
    if len(found) > 1:
        raise CliError(f"「{fragment}」对上 {len(found)} 个项目：" + "；".join(list(found.values())[:8]) + "。说得再具体点，或用窗口号/路径")
    return next(iter(found))


def resolve(selector: str | None, *, write: bool = False) -> Path:
    if not selector:
        root = _plan_root(Path.cwd())
        if root is None:
            raise CliError("当前目录不在任何有计划的项目里：plan ls 看有哪些，或 plan <项目>")
        return root
    if selector.isdigit():
        return _by_window(selector)
    if "/" in selector or selector.startswith(("~", ".")):
        root = _plan_root(Path(selector))
        if root is None:
            raise CliError(f"{selector} 不在任何有计划的项目里")
        return root
    if write:
        raise CliError("改别的项目要给路径或窗口号（-p ~/projects/x 或 -p 25），不接受模糊名字")
    return _by_name(selector)


def _is_qa(project: Path) -> bool:
    return top_qa.is_qa(top_plan._plan_path(str(project))[1])


def _is_project_path(value: str) -> bool:
    if not ("/" in value or value.startswith(("~", "."))):
        return False
    try:
        return Path(value).expanduser().is_dir()
    except OSError:  # a long note containing "/" is text, not a path (ENAMETOOLONG)
        return False


# ---------- reading ----------

def _clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _step_line(item, *, indent: str = "  ") -> str:
    extra = ""
    if item.state == "in_progress" and item.gates:
        extra = f"（验收：{'；'.join(item.gates)}）"
    elif item.state in ("blocked", "cancelled") and item.reason:
        extra = f"（{item.reason}）"
    return f"{indent}{STEP_ICONS.get(item.state, '·')} {item.id} {item.title}{extra}"


def _details_section(plan_path: Path, phase_id: str) -> str:
    details = plan_path.parent / top_plan.DETAILS_NAME
    if not details.is_file():
        return f"（还没有细节文章 {top_plan.DETAILS_NAME}）"
    lines = details.read_text(encoding="utf-8", errors="ignore").splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(rf"^##\s+{re.escape(phase_id)}(\s|$)", line)), None)
    if start is None:
        return f"（细节文章里没有 ## {phase_id} 这一节）"
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[start:end]).strip()


def _phase_block(state, phase, archived: dict[str, list[dict[str, str]]], *, details: bool) -> list[str]:
    index = state.phases.index(phase) + 1
    value = phase_state(phase, state.items)
    steps = phase_steps(phase, state.items)
    counted = [s for s in steps if s.state != "cancelled"]
    count = f"，{sum(1 for s in counted if s.state == 'done')}/{len(counted)}" if counted else ""
    out = [f"第 {index}/{len(state.phases)} 阶段 · {phase.id} {phase.title}（{PHASE_STATE_TEXT[value]}{count}）"]
    if phase.summary:
        out.append(f"  小结：{phase.summary}")
    out += [_step_line(step) for step in steps]
    if not steps and archived.get(phase.id):
        out.append(f"  （{len(archived[phase.id])} 步已收起：" + "；".join(s["title"] for s in archived[phase.id]) + "）")
    if details:
        out += ["", _details_section(state.path, phase.id)]
    return out


def view(project: Path, scope: str | None, *, details: bool) -> str:
    state = parse_plan(top_plan._plan_path(str(project))[1])
    if not state.outline:
        return _legacy_view(project, state, scope)
    archived = top_plan._archived_by_phase(state.path)
    if scope is None:
        return _core(project, state, details=details)
    if scope == "all":
        blocks = []
        for phase in state.phases:
            blocks.append("\n".join(_phase_block(state, phase, archived, details=details)))
        return "\n\n".join(blocks) or "还没有阶段"
    current = current_phase(state)
    if scope in ("current", "prev", "next"):
        if current is None:
            raise CliError("没有当前阶段（全部完成或还没有阶段）；plan 全部 看整份")
        at = state.phases.index(current) + {"current": 0, "prev": -1, "next": 1}[scope]
        if not 0 <= at < len(state.phases):
            raise CliError("当前已经是第一个阶段" if at < 0 else "当前已经是最后一个阶段")
        phase = state.phases[at]
    else:
        phase = next((p for p in state.phases if p.id == scope), None)
        if phase is None:
            raise CliError(f"没有阶段 {scope}；有：{'、'.join(p.id for p in state.phases)}")
    return "\n".join(_phase_block(state, phase, archived, details=details))


def _core(project: Path, state, *, details: bool) -> str:
    shown = top_plan.show(str(project), fast=True)
    goal = (shown.get("goal") or "").strip()
    lines = [f"{project.name} · 目标：{goal if goal and not goal.startswith('<') else '（还没写，plan goal）'}"]
    current = current_phase(state)
    for index, phase in enumerate(state.phases, 1):
        value = phase_state(phase, state.items)
        mark = "→" if current is not None and phase.id == current.id else " "
        lines.append(f"{mark} {PHASE_ICONS[value]} {index} {phase.id} {phase.title}")
    doing, upcoming = shown.get("current"), shown.get("next")
    if doing:
        gates = "；".join(doing.get("gates") or [])
        lines.append(f"正在做：{doing['id']} {doing['title']}" + (f"（验收：{gates}）" if gates else ""))
    lines.append(f"下一步：{upcoming['id']} {upcoming['title']}" if upcoming else "下一步：没有可以直接开始的步骤")
    blockers = shown.get("blockers") or []
    if blockers:
        lines.append("卡点：" + "；".join(f"{b['id']} {b['title']}" + (f"（{b['reason']}）" if b.get("reason") else "")
                                         for b in blockers[:3]) + (f"；共 {len(blockers)} 项" if len(blockers) > 3 else ""))
    if details and current is not None:
        lines += ["", _details_section(state.path, current.id)]
    return "\n".join(lines)


def _legacy_view(project: Path, state, scope: str | None) -> str:
    shown = top_plan.show(str(project), fast=True)
    lines = [f"{project.name} · 旧格式计划（任务清单）：主线难读，按 references/qa-plan.md 改写成问答格式（plan rewrite 草稿.md --to qa）"]
    if shown.get("goal"):
        lines.append(f"目标：{_clip(shown['goal'], 120)}")
    if scope == "all":
        lines += [_step_line(item) for item in state.items if not item.closed]
        return "\n".join(lines)
    for label, key in (("正在做", "current"), ("下一步", "next")):
        if shown.get(key):
            lines.append(f"{label}：{shown[key]['id']} {_clip(shown[key]['title'], 80)}")
    counts = shown.get("counts") or {}
    lines.append("任务：" + "，".join(f"{name} {counts.get(key, 0)}" for name, key in
                                     (("待办", "pending"), ("阻塞", "blocked"), ("完成", "done"))) + "（plan <项目> 全部 看未完成的）")
    return "\n".join(lines)


def ls(show_all: bool) -> str:
    windows: dict[Path, list[str]] = {}
    for session, index, cwd, _ in _tmux_windows():
        root = _plan_root(Path(cwd))
        if root is not None:
            windows.setdefault(root, []).append(index if session == DEFAULT_TMUX_SESSION else f"{session}:{index}")
    roots = set(windows)
    if show_all and PROJECTS_DIR.is_dir():
        roots |= {child.resolve() for child in PROJECTS_DIR.iterdir() if _plan_root(child) == child.resolve()}
    rows = []
    for root in roots:
        try:
            state = parse_plan(top_plan._plan_path(str(root))[1])
        except OSError:
            continue
        where = "#" + ",#".join(sorted(windows.get(root, []), key=lambda v: (len(v), v))) if windows.get(root) else "   "
        if state.format == "qa":
            text = top_qa_cli.ls_row(root)
        elif state.outline:
            phase = current_phase(state)
            doing = next((i for i in state.items if i.state == "in_progress"), None)
            stuck = sum(1 for i in state.items if i.state == "blocked")
            text = (f"{state.phases.index(phase) + 1}/{len(state.phases)} {_clip(phase.title, 18)}" if phase
                    else "全部完成" if state.phases else "还没有阶段")
            text += f" · ▶ {_clip(doing.title, 24)}" if doing else ""
            text += f" · 卡 {stuck}" if stuck else ""
        elif state.items:
            doing = next((i for i in state.items if i.state == "in_progress"), None)
            text = "旧格式" + (f" · ▶ {doing.id}" if doing else "")
        else:
            text = "轻量（没有任务）"
        rows.append((min((int(v) for v in windows.get(root, []) if v.isdigit()), default=10_000), root.name,
                     f"{where:<8} {_clip(root.name, 26):<26} {text}"))
    if not rows:
        return "没有开着窗口的项目；plan ls --all 看全部"
    return "\n".join(row[2] for row in sorted(rows))


# ---------- writing ----------

def _now_line(project: Path) -> str:
    if _is_qa(project):
        return top_qa_cli.now_line(project)
    shown = top_plan.show(str(project), fast=True)
    parts = []
    phase = shown.get("phase")
    if phase:
        parts.append(f"第 {phase['index']}/{shown.get('phase_count')} 阶段")
    if shown.get("current"):
        parts.append(f"正在做 {shown['current']['id']} {_clip(shown['current']['title'], 30)}")
    if shown.get("next"):
        parts.append(f"下一步 {shown['next']['id']} {_clip(shown['next']['title'], 30)}")
    return "现在：" + "；".join(parts) if parts else ""


def _take(args: list[str], *names: str, many: bool = False, flag: bool = False) -> Any:
    """Pop `--name value` (or bare `--name` when flag) from args; repeated values when many."""
    values: list[str] = []
    found = False
    index = 0
    while index < len(args):
        if args[index] in names:
            found = True
            if flag:
                args.pop(index)
                continue
            if index + 1 >= len(args):
                raise CliError(f"{args[index]} 后面要跟内容")
            values.append(args[index + 1])
            del args[index:index + 2]
            continue
        match = next((n for n in names if args[index].startswith(n + "=")), None)
        if match and not flag:
            values.append(args[index].split("=", 1)[1])
            args.pop(index)
            found = True
            continue
        index += 1
    if flag:
        return found
    return values if many else (values[-1] if values else None)


def _need(args: list[str], count: int, usage: str) -> list[str]:
    extra = [a for a in args if a.startswith("--")]
    if extra:
        raise CliError(f"不认识的选项 {extra[0]}；用法：{usage}")
    if len(args) != count:
        raise CliError(f"用法：{usage}")
    return args


def write(verb: str, args: list[str]) -> tuple[dict[str, Any], str, Path]:
    selector = _take(args, "-p", "--project")
    project = resolve(selector, write=True)
    here = _plan_root(Path.cwd())
    p = str(project)
    note = "" if here == project else f"（注意：改的是别的项目 {project.name} 的计划）"
    if _is_qa(project):
        try:
            result, text = top_qa_cli.write(verb, args, project, _take, _need)
        except top_qa_cli.QaCliError as exc:
            raise CliError(str(exc)) from None
        return result, text + note, project
    if verb in QA_ONLY_VERBS:
        raise CliError(top_qa_cli.not_qa_hint(verb))
    if verb in ("rewrite", "migrate") and _take(list(args), "--to") == "qa":
        import top_qa_migrate  # noqa: PLC0415
        apply = _take(args, "--apply", flag=True)
        accept = _take(args, "--accept-dropped", flag=True)
        _take(args, "--to")
        (draft,) = _need(args, 1, "plan rewrite 草稿.md --to qa [--apply] [--accept-dropped]")
        result = top_qa_migrate.migrate(p, draft, apply=apply, accept_dropped=accept)
        return result, top_qa_migrate.summary_text(result) + note, project
    if verb == "add":
        target = _take(args, "--to", "--phase", "--parent")
        gates = _take(args, "--gate", many=True)
        (title,) = _need(args, 1, 'plan add "一句人话" [--to P3] [--gate "…"]')
        if not target:
            state = parse_plan(top_plan._plan_path(p)[1])
            phase = current_phase(state) if state.outline else None
            if phase is None:
                raise CliError("不知道加到哪个阶段：用 --to <阶段ID>" + ("（旧格式计划用 --to <父任务ID>）" if not state.outline else ""))
            target = phase.id
        result = top_plan.add(p, title=title, parent=target, gates=gates)
        return result, f"已加 {result['item_id']}「{title}」" + note, project
    if verb == "insert":
        reason = _take(args, "--why", "--reason")
        gates = _take(args, "--gate", many=True)
        after, title = _need(args, 2, 'plan insert P3.2 "一句人话" [--why "原因"]')
        result = top_plan.insert(p, after, title=title, gates=gates, reason=reason)
        return result, "\n".join(result.get("change_summary") or [f"已插入 {result['item_id']}"]) + note, project
    if verb == "start":
        (item_id,) = _need(args, 1, "plan start P3.2")
        result = top_plan.start(p, item_id)
        return result, f"开始 {item_id}" + note, project
    if verb in ("done", "complete"):
        evidence = _take(args, "--ev", "--evidence", many=True)
        no_artifact = _take(args, "--no-artifact", "--no-artifact-reason")
        commit = _take(args, "--commit", flag=True)
        decisions = _take(args, "--decision", many=True)
        (item_id,) = _need(args, 1, 'plan done P3.2 --ev "证据" [--commit] | --no-artifact "原因"')
        result = top_plan.complete(p, item_id, evidence, no_artifact, commit=commit, decisions=decisions)
        text = f"完成 {item_id}"
        shas = [c.get("commit") for c in (result.get("git") or {}).get("commits", []) if c.get("commit")]
        if shas:
            text += f"，已提交 {shas[0]}"
        if result.get("gate_reminder"):
            text += f"\n提醒：{result['gate_reminder']}"
        if (result.get("git") or {}).get("track_hint"):
            text += f"\n提醒：{result['git']['track_hint']}"
        return result, text + note, project
    if verb in ("block", "cancel"):
        item_id, reason = _need(args, 2, f'plan {verb} P3.2 "原因"')
        result = (top_plan.block if verb == "block" else top_plan.cancel)(p, item_id, reason)
        return result, f"{'卡住' if verb == 'block' else '取消'} {item_id}：{reason}" + note, project
    if verb == "reopen":
        (item_id,) = _need(args, 1, "plan reopen P3.2")
        result = top_plan.reopen(p, item_id)
        return result, f"重开 {item_id}" + note, project
    if verb == "replan":
        replacements = _take(args, "--with", "--replace-with", many=True)
        gates = _take(args, "--gate", many=True)
        item_id, reason = _need(args, 2, 'plan replan P3.2 "为什么换" --with "新做法" [--with …]')
        result = top_plan.replan(p, item_id, reason=reason, replace_with=replacements, gates=gates)
        return result, "\n".join(result.get("change_summary") or []) + note, project
    if verb == "rename":
        target, title = _need(args, 2, 'plan rename P3.2 "新说法"（P3 这样的阶段 ID 改阶段名）')
        if re.fullmatch(r"P\d+", target):
            result = top_plan.phase_edit(p, target, title=title)
        else:
            result = top_plan.edit(p, target, title=title)
        return result, f"改名 {target}「{title}」" + note, project
    if verb == "note":
        kind = "fail" if _take(args, "--fail", flag=True) else "learn" if _take(args, "--learn", flag=True) else "progress"
        item_id = _take(args, "--on", "--id")
        (text,) = _need(args, 1, 'plan note "一句话" [--fail|--learn] [--on P3.2]')
        result = top_plan.note(p, text, item_id=item_id, kind=kind)
        line = f"已记（{ {'fail': '失败', 'learn': '心得', 'progress': '进展'}[kind] }，{result['item_id']}）"
        if result.get("escalate"):
            line += f"\n⚠ {result['next_hint']}"
        return result, line + note, project
    if verb == "phase":
        summary = _take(args, "--summary")
        after = _take(args, "--after")
        (title,) = _need(args, 1, 'plan phase "阶段名" [--summary "为什么做"] [--after P3]')
        result = top_plan.phase_add(p, title=title, summary=summary, after=after)
        return result, f"已加阶段 {result['phase_id']}「{title}」；plan add \"…\" --to {result['phase_id']} 加步骤" + note, project
    if verb == "summary":
        phase_id, text = _need(args, 2, 'plan summary P3 "得到了什么，所以下一阶段做什么"')
        result = top_plan.phase_edit(p, phase_id, summary=text)
        return result, f"已改 {phase_id} 小结" + note, project
    if verb == "drop":
        phase_id, reason = _need(args, 2, 'plan drop P3 "原因"')
        result = top_plan.phase_cancel(p, phase_id, reason=reason)
        text = f"放弃阶段 {phase_id}（取消 {len(result.get('cancelled') or [])} 步）"
        if result.get("verdict") == "warn":
            text += f"\n提醒：{result['next_hint']}"
        return result, text + note, project
    if verb == "goal":
        (text,) = _need(args, 1, 'plan goal "一两句：做完是什么样"')
        return top_plan.set_goal(p, text), "已改目标" + note, project
    if verb == "archive":
        keep = _take(args, "--keep")
        _need(args, 0, "plan archive [--keep N]")
        result = top_plan.archive(p, keep=int(keep) if keep else 5)
        phases = result.get("archived_phases")
        return result, (f"已收起 {'、'.join(phases)}（{result['archived']} 步）" if phases
                        else result.get("next_hint") or f"已收起 {result.get('archived', 0)} 项") + note, project
    if verb in ("rewrite", "migrate"):
        apply = _take(args, "--apply", flag=True)
        accept = _take(args, "--accept-dropped", flag=True)
        (draft,) = _need(args, 1, "plan rewrite 草稿.md [--apply] [--accept-dropped]")
        result = top_plan.migrate(p, draft, apply=apply, accept_dropped=accept)
        return result, _rewrite_text(result) + note, project
    raise CliError(f"不认识的命令 {verb}；plan help 看全部")


def _rewrite_text(result: dict[str, Any]) -> str:
    if result.get("errors"):
        return "✗ 草稿有问题：\n" + "\n".join(f"  {e['code']}：{e['message']}" for e in result["errors"])
    lines = [f"{'已替换' if result.get('apply') else '预览通过'}：{result.get('phases')} 个阶段、{result.get('steps')} 步"]
    for warning in result.get("warnings") or []:
        lines.append(f"  提醒 {warning['code']}：{warning['message']}")
    if result.get("dropped_open"):
        lines.append("  旧计划里这些未完成的不在草稿里：" + "；".join(result["dropped_open"][:10]))
    lines.append(result.get("next_hint") or "")
    return "\n".join(line for line in lines if line)


def check(project: Path) -> str:
    if _is_qa(project):
        return top_qa_cli.check(project)
    result = top_plan.validate(str(project))
    lines = [f"{project.name}：" + {"ok": "没问题", "warn": "有提醒", "block": "有错误"}.get(result.get("verdict"), "?")]
    lines += [f"  ✗ {e['code']}：{e['message']}" for e in result.get("errors") or []]
    lines += [f"  提醒 {w['code']}：{w['message']}\n    → {w['hint']}" for w in result.get("warnings") or []]
    return "\n".join(lines)


# ---------- entry ----------

QA_ONLY_VERBS = {"ask", "answer", "flag", "wait", "focus", "move", "upgrade"}
WRITE_VERBS = {"add", "insert", "start", "done", "complete", "block", "cancel", "reopen", "replan", "rename",
               "note", "phase", "summary", "drop", "goal", "archive", "rewrite", "migrate"} | QA_ONLY_VERBS


def _help(args: list[str]) -> str:
    """问答格式的速查是默认；当前目录是旧格式/目录格式计划时给旧速查（plan help qa / 旧 切换）。"""
    if args and args[0] in ("旧", "old", "outline", "目录"):
        return HELP.rstrip()
    if args and args[0] in ("qa", "问答"):
        return top_qa_cli.HELP.rstrip()
    root = _plan_root(Path.cwd())
    if root is not None and not _is_qa(root):
        state = parse_plan(top_plan._plan_path(str(root))[1])
        if state.items:
            return HELP.rstrip() + "\n\n（这个项目还是旧格式/目录格式计划；问答格式的命令：plan help qa）"
    return top_qa_cli.HELP.rstrip()


def _init(args: list[str], want_json: bool) -> int:
    """plan init "目标" [-p 路径]：在没有计划（或计划是空的）的项目里建一份问答式计划。"""
    try:
        selector = _take(args, "-p", "--project")
        (goal,) = _need(args, 1, 'plan init "一两句：做完是什么样" [-p 路径]')
        # the git work tree (or the directory itself); never a parent that merely has a _wiki-methodology
        start = (Path(selector).expanduser() if selector else Path.cwd()).resolve()
        root = top_plan._main_worktree_root(top_plan.top_git.toplevel(start) or start)
        (root / "_wiki-methodology" / "_top").mkdir(parents=True, exist_ok=True)
        result = top_qa.init(str(root), goal)
    except (CliError, top_qa_cli.QaCliError, PlanError) as exc:
        print(f"✗ {exc}")
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2) if want_json
          else f"已建问答式计划：{result['task_plan']}\n下一步：{result['next_hint']}")
    return 0


def _passthrough(argv: list[str]) -> int:
    return subprocess.run([sys.executable, str(SIXONE), "plan", *argv], stdin=subprocess.DEVNULL).returncode


def main(argv: list[str]) -> int:
    want_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    if argv and argv[0] in ("help", "-h", "--help"):
        print(_help(argv[1:]))
        return 0
    verb = argv[0] if argv else ""
    if verb == "init":
        return _init(argv[1:], want_json)
    # old sixone style: a subcommand with no short form, or a project path right after the verb
    if verb in PASSTHROUGH or (verb in WRITE_VERBS - QA_ONLY_VERBS and len(argv) > 1 and _is_project_path(argv[1])):
        return _passthrough(argv if verb not in ("done",) else ["complete", *argv[1:]])
    try:
        if verb == "now":
            rest = list(argv[1:])
            project = resolve(_take(rest, "-p", "--project") or (rest.pop(0) if rest else None))
            _need(rest, 0, "plan now [-p 路径]")
            if _is_qa(project):
                if want_json:
                    print(json.dumps(top_qa.show(project), ensure_ascii=False, indent=2))
                else:
                    print(top_qa_cli.core(project, include_questions=False))
            else:
                if want_json:
                    print(json.dumps(top_plan.show(str(project), fast=True), ensure_ascii=False, indent=2))
                else:
                    print(view(project, None, details=False))
            return 0
        if verb == "ls":
            rest = argv[1:]
            show_all = _take(rest, "--all", "-a", flag=True)
            _need(rest, 0, "plan ls [--all]")
            print(ls(show_all))
            return 0
        if verb == "check":
            rest = argv[1:]
            project = resolve(_take(rest, "-p", "--project") or (rest.pop(0) if rest else None))
            if want_json:
                print(json.dumps(top_plan.validate(str(project)), ensure_ascii=False, indent=2))
                return 0
            print(check(project))
            return 0
        if verb in WRITE_VERBS:
            result, text, project = write(verb, list(argv[1:]))
            if want_json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0 if result.get("verdict") != "block" else 1
            if result.get("verdict") == "block":
                if result.get("format") == "qa":
                    print(text)
                else:
                    print(_rewrite_text(result) if verb in ("rewrite", "migrate") else f"✗ {result.get('next_hint') or result}")
                return 1
            print(text)
            if verb not in ("rewrite", "migrate", "note", "goal", "summary", "rename") or result.get("apply"):
                line = _now_line(project)
                if line:
                    print(line)
            return 0
        # reading: plan [项目] [范围] [--细节]
        rest = list(argv)
        details = any(a in DETAIL_FLAGS for a in rest)
        rest = [a for a in rest if a not in DETAIL_FLAGS]
        bad = [a for a in rest if a.startswith("-")]
        if bad:
            raise CliError(f"不认识的选项 {bad[0]}；plan help")
        tokens: list[str] = []
        while rest and (rest[-1] in SCOPES or re.fullmatch(r"[PQ]\d+(?:\.[A-Za-z0-9]+)*", rest[-1])):
            tokens.insert(0, rest.pop())
        if len(rest) > 1:
            raise CliError("看计划：plan [项目] [当前|全部|Q4 [全部]|P3] [--细节]")
        project = resolve(rest[0] if rest else None)
        if _is_qa(project):
            if want_json:
                if tokens and re.fullmatch(r"Q\d+", tokens[0]):
                    data = top_qa.question_view(project, tokens[0], full=tokens[-1] in ("全部", "all") and len(tokens) > 1)
                elif tokens and re.fullmatch(r"P\d+(?:\.[A-Za-z0-9]+)*", tokens[0]):
                    data = top_qa.resolve_alias(project, tokens[0]) or {"old": tokens[0], "hits": []}
                else:
                    data = top_qa.show(project)
                print(json.dumps(data, ensure_ascii=False, indent=2))
                return 0
            print(top_qa_cli.view(project, tokens))
            return 0
        if len(tokens) > 1:
            raise CliError("看计划：plan [项目] [当前|上一|下一|全部|P3] [--细节]")
        scope = SCOPES.get(tokens[0], tokens[0]) if tokens else None
        if scope is not None and scope not in SCOPES.values() and not re.fullmatch(r"P\d+", scope):
            raise CliError(f"{scope} 不是阶段编号；目录格式用 P3 这样的阶段编号")
        if want_json:
            print(json.dumps(top_plan.show(str(project), fast=True), ensure_ascii=False, indent=2))
            return 0
        print(view(project, scope, details=details))
        return 0
    except (CliError, top_qa_cli.QaCliError) as exc:
        print(f"✗ {exc}")
        return 1
    except PlanConflict as exc:
        print(f"✗ 计划刚被别处改过，重读后再试：{exc}")
        return 1
    except PlanError as exc:
        print(f"✗ {_plain(str(exc))}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
