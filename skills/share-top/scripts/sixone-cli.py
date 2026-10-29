#!/usr/bin/env python3
"""sixone CLI — 本地命令行壳(薄)。逻辑全在 core/sixone_core(可单测)。

六合一已脚本化:进项目跑 plan show;改文件前 record for-file 查相关决策;完成用 plan complete --commit。
代码结构交给 CodeGraph(实时、零维护)+ `_codemap.md`(一页纸入口);CodeBook 已退役,deposit 只提示不盖章。

用法:
    python3 sixone-cli.py brief   <id|path>
    python3 sixone-cli.py doctor  <id|path> [--no-links]
    python3 sixone-cli.py deposit <id|path> <node_rel>          # 已退役:只提示,不再盖章
    python3 sixone-cli.py verify-pipeline <id|path> <name>      # 改完 step 代码后盖 pipeline 印记
    python3 sixone-cli.py affected <id|path> [--since <commit>] # 改动→该回写哪些节点/线(codegraph 顾问)
    python3 sixone-cli.py plan show <id|path>                   # 当前坐标+下一步(“我在哪”唯一入口)
    python3 sixone-cli.py plan next <id|path>                   # 依赖已完成、未阻塞的待办
    python3 sixone-cli.py plan add|edit|start|complete|...      # 受控任务 CRUD
    python3 sixone-cli.py plan insert <id|path> <AFTER_ID> --title … [--rewire]   # 插一步(ID=<AFTER_ID>a)
    python3 sixone-cli.py plan replan <id|path> <ID> --reason … --replace-with …  # 换路线:取消+替代+改依赖
    python3 sixone-cli.py plan compact <id|path> [--apply]      # 流水段移到 _logs/(默认预览)
    python3 sixone-cli.py plan handoff <id|path> <交接文档>       # 交接文档随提交带 Handoff: trailer
    python3 sixone-cli.py plan milestone <id|path> <phase>      # annotated tag top/<phase>
    python3 sixone-cli.py record for-file <id|path> <文件> [--symbol X]  # 与该文件相关的决策/经验
    python3 sixone-cli.py track <repo> [--write-gitignore] [--markdown]   # Git 追踪分拣:写出来的进,算出来的忽略
                                                                # complete/block/cancel/reopen 自动追加 _logs/<日期>-plan.md(--no-log 关)

退出码:error=2;doctor/deposit/verify-pipeline 非 ok/warn(block/broken/stale)=1;ok/warn=0(stale 也 fail-loud)。
"""
from __future__ import annotations

import argparse
import json
import sys
import subprocess
from pathlib import Path

# CLI 不依赖 MCP/fastmcp,只 import 纯逻辑层。
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
import sixone_core as core  # noqa: E402
import top_owner  # noqa: E402
import top_plan  # noqa: E402
import top_qa  # noqa: E402
import top_record  # noqa: E402
import top_track  # noqa: E402
import top_version  # noqa: E402


def _emit(result: dict) -> int:
    """打印 JSON envelope + 派生退出码(error/阻断 fail-loud)。"""
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.flush()
    # Tier3 行动尾注(2026-06-15 · 近因效应): 把"该回写啥"放在 AI 上下文最末尾,服从度比埋
    # 在全局规则里高。走 stderr 不污染 stdout JSON(| jq 不破),但 AI 仍能看到、且在最后。
    hint = result.get("next_hint")
    verdict = result.get("verdict")
    actionable = (verdict in ("block", "broken", "stale")
                  or result.get("pipelines_affected") or result.get("escalate"))
    if hint and actionable:
        print(f"\n[→ AI 行动] {hint}", file=sys.stderr)
    if "error" in result:
        return 2
    # stale 也算硬信号: 治理陈旧不能静默当成功(fail-loud)
    if verdict in ("block", "broken", "stale"):
        return 1
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("brief", help="冷启动握手: whole picture + codebook/pipelines/gates + next_hint")
    b.add_argument("project", help="注册 id 或本地路径")

    d = sub.add_parser("doctor", help="只查: 死链、登记路径存在、plan validate、未记录改动(+已启用的 CodeBook/pipeline 印记)")
    d.add_argument("project", help="注册 id 或本地路径")
    d.add_argument("--no-links", action="store_true", help="跳过死链检查")
    d.add_argument("--full", action="store_true", help="旧版全量体检(state drift/SSDO/wiki/tests/根目录杂物等),可选")

    dep = sub.add_parser("deposit", help="已退役:CodeBook 不再盖章,只输出迁移提示(兼容旧调用)")
    dep.add_argument("project", help="注册 id 或本地路径")
    dep.add_argument("node", help="_codebook 下相对路径, 如 _codebook/x.md")

    vp = sub.add_parser("verify-pipeline", help="改完 pipeline step 代码/接线后唯一盖印记(verified_steps_hash)")
    vp.add_argument("project", help="注册 id 或本地路径")
    vp.add_argument("name", help="pipeline id / manifest 文件名 stem")

    af = sub.add_parser("affected", help="改动→反查该回写哪些 CodeBook 节点/pipeline(codegraph 顾问)")
    af.add_argument("project", help="注册 id 或本地路径")
    af.add_argument("--since", default=None, help="基线 commit(默认: 工作区 vs HEAD)")
    af.add_argument("--task", default=None, help="从 Active Work 读取 scope/gate 并联动影响面")

    plan = sub.add_parser("plan", help="_task_plan.md 当前坐标、校验与原子 CRUD")
    plan_sub = plan.add_subparsers(dest="plan_cmd", required=True)

    plan_show = plan_sub.add_parser("show", help="30 秒恢复卡:目标/当前/下一步/阻塞/任务笔记/未记录改动")
    plan_show.add_argument("project", nargs="?", default=".")
    plan_show.add_argument("--fast", action="store_true", help="跳过 git 统计(unrecorded/task_git)")

    plan_list = plan_sub.add_parser("list", help="列 Active Work 任务")
    plan_list.add_argument("project", nargs="?", default=".")
    plan_list.add_argument("--state", choices=sorted(top_plan.PLAN_STATES) if hasattr(top_plan, "PLAN_STATES") else None)

    plan_validate = plan_sub.add_parser("validate", help="校验 ID、状态、镜像、依赖和证据 + 体积预算警告")
    plan_validate.add_argument("project", nargs="?", default=".")

    plan_upgrade = plan_sub.add_parser("upgrade", help="问答格式:检查/升级计划版本(无版本先检查内容)")
    plan_upgrade.add_argument("project", nargs="?", default=".")
    plan_upgrade.add_argument("--apply", action="store_true", help="真正写入(默认只预览)")
    plan_upgrade.add_argument("--expect", default=None, help="调用方看到的 revision;变了就报冲突")

    plan_question = plan_sub.add_parser("question", help="问答格式:一个问题的工作本(答案修订、尝试、笔记),JSON")
    plan_question.add_argument("project")
    plan_question.add_argument("id", help="问题编号 Q<n>")
    plan_question.add_argument("--full", action="store_true", help="全部尝试(默认:开放的 + 最近 8 个做完的)")

    plan_next = plan_sub.add_parser("next", help="列依赖都已完成、未阻塞的待办任务(计划顺序)")
    plan_next.add_argument("project", nargs="?", default=".")

    plan_compact = plan_sub.add_parser("compact", help="把按日期的流水段/超长历史移到 _logs/<日期>-journal-archive.md")
    plan_compact.add_argument("project", nargs="?", default=".")
    plan_compact.add_argument("--apply", action="store_true", help="真正写入(默认只预览)")

    plan_inspect = plan_sub.add_parser("inspect", help="查看一个任务的 scope/gate/evidence")
    plan_inspect.add_argument("project")
    plan_inspect.add_argument("id")

    plan_add = plan_sub.add_parser("add", help="新增步骤:目录格式用 --parent <阶段ID或步骤ID>(ID 自动编号);旧格式 root task 或 parent child")
    plan_add.add_argument("project")
    add_id = plan_add.add_mutually_exclusive_group(required=True)
    add_id.add_argument("--id")
    add_id.add_argument("--parent")
    plan_add.add_argument("--title", required=True)
    plan_add.add_argument("--dep", action="append", default=[])
    plan_add.add_argument("--depends-on", action="append", default=[],
                          help="逗号分隔的前置任务 ID,写成 depends_on=A,B")
    plan_add.add_argument("--scope", action="append", default=[])
    plan_add.add_argument("--gate", action="append", default=[],
                          help="开工时写清的验收标准或验证命令;complete 时提示把其结果作为证据")

    plan_edit = plan_sub.add_parser("edit", help="修改开放任务的标题/依赖/scope/gate")
    plan_edit.add_argument("project")
    plan_edit.add_argument("id")
    plan_edit.add_argument("--title")
    plan_edit.add_argument("--add-dep", action="append", default=[])
    plan_edit.add_argument("--remove-dep", action="append", default=[])
    plan_edit.add_argument("--add-scope", action="append", default=[])
    plan_edit.add_argument("--remove-scope", action="append", default=[])
    plan_edit.add_argument("--add-gate", action="append", default=[])
    plan_edit.add_argument("--remove-gate", action="append", default=[])

    no_log_help = "不追加 _top/_logs/<日期>-plan.md 留痕行"
    plan_start = plan_sub.add_parser("start", help="start 一个任务")
    plan_start.add_argument("project")
    plan_start.add_argument("id")
    plan_start.add_argument("--worktree", action="store_true",
                            help="在 .worktrees/<ID> 建任务分支 task/<ID>(开 worktree 前须经用户同意)")
    plan_reopen = plan_sub.add_parser("reopen", help="reopen 一个任务")
    plan_reopen.add_argument("project")
    plan_reopen.add_argument("id")
    plan_reopen.add_argument("--no-log", action="store_true", help=no_log_help)

    plan_complete = plan_sub.add_parser("complete", help="带 evidence 完成任务")
    plan_complete.add_argument("project")
    plan_complete.add_argument("id")
    plan_complete.add_argument("--evidence", action="append", default=[])
    plan_complete.add_argument("--no-artifact-reason")
    plan_complete.add_argument("--no-log", action="store_true", help=no_log_help)
    plan_complete.add_argument("--commit", action="store_true",
                               help="本地提交该任务 scope/gate/证据路径里的改动 + 计划与日志(不 push)")
    plan_complete.add_argument("--merge", action="store_true",
                               help="把 task/<ID> 分支合回主 worktree 当前分支并清理 worktree")
    plan_complete.add_argument("--decision", action="append", default=[],
                               help="相关决策记录路径(可多次);--commit 时写 Decision: trailer 并一并提交")

    plan_note = plan_sub.add_parser("note", help="任务中途记一行:进展/失败/心得(写入当日计划日志)")
    plan_note.add_argument("project")
    plan_note.add_argument("text")
    plan_note.add_argument("--id", help="默认当前进行中任务;没有则记为整个计划")
    plan_note.add_argument("--kind", choices=top_plan.NOTE_KINDS, default="progress")

    plan_insert = plan_sub.add_parser("insert", help="在某任务(含其子树)之后插入同级新任务;新 ID 为 <AFTER_ID>a/b…,不改已有 ID")
    plan_insert.add_argument("project")
    plan_insert.add_argument("after_id", help="插在这个任务(及其子任务)之后")
    plan_insert.add_argument("--title", required=True)
    plan_insert.add_argument("--gate", action="append", default=[], help="新任务的验收标准或验证命令")
    plan_insert.add_argument("--reason", help="为什么插入(写进日志和 change_summary,不写进计划行)")
    plan_insert.add_argument("--rewire", action="store_true",
                             help="新任务依赖 AFTER_ID;原来依赖 AFTER_ID 的待办/阻塞任务改为依赖新任务")
    plan_insert.add_argument("--no-log", action="store_true", help=no_log_help)

    plan_replan = plan_sub.add_parser("replan", help="换路线:取消任务,在原位置插入串联的替代任务,依赖它的待办改依赖最后一个替代任务")
    plan_replan.add_argument("project")
    plan_replan.add_argument("id")
    plan_replan.add_argument("--reason", required=True, help="为什么换路线(取消原因写成“换路线:…”,并记一条 fail 笔记)")
    plan_replan.add_argument("--replace-with", action="append", required=True,
                             help="替代任务标题,可多次,按顺序串联依赖")
    plan_replan.add_argument("--gate", action="append", default=[],
                             help="最后一个替代任务的验收(默认沿用原任务的 gate)")
    plan_replan.add_argument("--no-log", action="store_true", help=no_log_help)

    plan_merge = plan_sub.add_parser("merge", help="把 task/<ID> 分支合回主线(先 ff,否则 merge commit;冲突则中止)")
    plan_merge.add_argument("project")
    plan_merge.add_argument("id")

    plan_handoff = plan_sub.add_parser("handoff", help="交接文档 + 计划日志一起提交,带 Handoff: trailer")
    plan_handoff.add_argument("project")
    plan_handoff.add_argument("doc", help="交接文档路径(相对项目根或绝对)")
    plan_handoff.add_argument("--no-commit", action="store_true", help="只记日志,不提交")

    plan_milestone = plan_sub.add_parser("milestone", help="阶段里程碑:打 annotated tag top/<phase>,消息为完成任务摘要")
    plan_milestone.add_argument("project")
    plan_milestone.add_argument("phase", help="阶段 ID,如 P1 或 P1.0")
    plan_milestone.add_argument("--allow-open", action="store_true", help="阶段仍有未关闭任务也打 tag")

    plan_phase = plan_sub.add_parser("phase", help="目录格式计划的阶段:新建/改名或改小结/整段放弃")
    phase_sub = plan_phase.add_subparsers(dest="phase_cmd", required=True)
    phase_add = phase_sub.add_parser("add", help="新建阶段 ### P<n>(编号自动取未用过的下一个)")
    phase_add.add_argument("project")
    phase_add.add_argument("--title", required=True, help="阶段名:一句人话,≤24 字")
    phase_add.add_argument("--summary", help="一两句承上启下的小结:为什么做这一阶段/它要回答什么")
    phase_add.add_argument("--after", help="插在这个阶段之后(默认放在最后)")
    phase_edit = phase_sub.add_parser("edit", help="改阶段名或小结")
    phase_edit.add_argument("project")
    phase_edit.add_argument("id", help="阶段 ID,如 P3")
    phase_edit.add_argument("--title")
    phase_edit.add_argument("--summary", help="完成的阶段写得到了什么、对下一阶段意味着什么")
    phase_cancel = phase_sub.add_parser("cancel", help="整段放弃:取消该阶段所有未关闭步骤并写原因")
    phase_cancel.add_argument("project")
    phase_cancel.add_argument("id")
    phase_cancel.add_argument("--reason", required=True)

    plan_goal = plan_sub.add_parser("goal", help="改 ## 目标(一两句人话:整件事做完是什么样)")
    plan_goal.add_argument("project")
    plan_goal.add_argument("text")

    plan_migrate = plan_sub.add_parser("migrate", help="用 AI 写好的目录格式草稿替换计划(默认预览;旧原文存 _logs/plan-history)")
    plan_migrate.add_argument("project")
    plan_migrate.add_argument("draft", help="草稿文件路径(相对项目根或绝对)")
    plan_migrate.add_argument("--apply", action="store_true", help="真正替换(默认只预览)")
    plan_migrate.add_argument("--accept-dropped", action="store_true",
                              help="确认放弃旧计划里、草稿没列出的未关闭任务")

    plan_archive = plan_sub.add_parser("archive", help="把已关闭任务移出 Active Work 到 _logs/plan-archive.md;目录格式:收起已完成阶段的步骤")
    plan_archive.add_argument("project")
    plan_archive.add_argument("--keep", type=int, default=5, help="保留最近 N 组已关闭任务(默认 5)")

    for command in ("block", "cancel"):
        parser = plan_sub.add_parser(command, help=f"{command} 一个任务并保留原因")
        parser.add_argument("project")
        parser.add_argument("id")
        parser.add_argument("--reason", required=True)
        parser.add_argument("--no-log", action="store_true", help=no_log_help)

    owner = sub.add_parser("owner", help="六合一六列 owner 定位与 typed-ref 解析(只读)")
    owner_sub = owner.add_subparsers(dest="owner_cmd", required=True)
    owner_list = owner_sub.add_parser("list", help="列六列 owner")
    owner_list.add_argument("project", nargs="?", default=".")
    owner_show = owner_sub.add_parser("show", help="显示一列候选 owner 路径")
    owner_show.add_argument("project")
    owner_show.add_argument("column", choices=sorted(top_owner.OWNER_PATHS))
    owner_resolve = owner_sub.add_parser("resolve", help="解析 registry:/pipeline:/gate:/path:/symbol: 等引用")
    owner_resolve.add_argument("project")
    owner_resolve.add_argument("ref")

    record = sub.add_parser("record", help="结构化 TOP finding/decision/review/log")
    record_sub = record.add_subparsers(dest="record_cmd", required=True)
    record_add = record_sub.add_parser("add", help="复用 top-update 创建结构化记录")
    record_add.add_argument("kind", choices=sorted(top_record.KIND_DIR))
    record_add.add_argument("project")
    record_add.add_argument("--title", required=True)
    record_add.add_argument("--summary", required=True)
    record_add.add_argument("--phase")
    record_add.add_argument("--evidence", action="append", default=[])
    record_add.add_argument("--rationale")
    record_add.add_argument("--request")
    record_add.add_argument("--commit")
    record_add.add_argument("--follow-up")
    for flag in ("alternative", "file", "test", "source", "supersedes"):
        record_add.add_argument(f"--{flag}", action="append", default=[])
    record_search = record_sub.add_parser("search", help="本地关键词查决策；默认至多 3 条摘要，不调用模型")
    record_search.add_argument("project")
    record_search.add_argument("query")
    record_search.add_argument("--kind", choices=[*sorted(top_record.KIND_DIR), "all"], default="decision")
    record_search.add_argument("--limit", type=int, default=3)
    record_for_file = record_sub.add_parser("for-file", help="与某文件相关的决策/经验(正文/涉及代码 + git Decision trailer)")
    record_for_file.add_argument("project")
    record_for_file.add_argument("path", help="文件路径(相对项目根、相对仓库根或绝对)")
    record_for_file.add_argument("--symbol", help="函数/类等符号名")
    record_for_file.add_argument("--limit", type=int, default=3)
    record_list = record_sub.add_parser("list", help="有界列出记录")
    record_list.add_argument("kind", choices=sorted(top_record.KIND_DIR))
    record_list.add_argument("project", nargs="?", default=".")
    record_show = record_sub.add_parser("show", help="有界读取一个 TOP 记录")
    record_show.add_argument("project")
    record_show.add_argument("ref")

    version = sub.add_parser("version", help="Git上下文与显式范围内容快照；不提交/切分支/推送")
    versions = version.add_subparsers(dest="version_cmd", required=True)
    vs = versions.add_parser("status", help="只读工作区、分支、commit及脏状态")
    vs.add_argument("project", nargs="?", default=".")
    vc = versions.add_parser("capture", help="保存显式源文件内容及外部资产hash")
    vc.add_argument("project")
    vc.add_argument("--file", action="append", required=True)
    vc.add_argument("--artifact", action="append", default=[])
    vc.add_argument("--output", required=True)
    vc.add_argument("--task")
    vv = versions.add_parser("verify", help="核验当前内容；--staged核验暂存源文件")
    vv.add_argument("project")
    vv.add_argument("manifest")
    vv.add_argument("--staged", action="store_true")
    vd = versions.add_parser("compare", help="比较两个显式范围快照")
    vd.add_argument("left")
    vd.add_argument("right")

    tr = sub.add_parser("track", help="Git 追踪分拣:未提交/未追踪文件分 commit/ignore/review,并查已追踪的缓存/凭证")
    tr.add_argument("repo", nargs="?", default=".", help="仓库路径(任一子目录均可)")
    tr.add_argument("--write-gitignore", action="store_true",
                    help="把忽略建议幂等写进根 .gitignore 的 '# >>> top track (auto) >>>' 标记块(不 add/commit/rm)")
    tr.add_argument("--markdown", action="store_true", help="输出人类可读摘要而不是 JSON")

    args = p.parse_args()
    if args.cmd == "track":
        result = top_track.track(args.repo, write=args.write_gitignore)
        if args.markdown:
            print(top_track.render_markdown(result))
            return 2 if "error" in result else 0
        return _emit(result)
    if args.cmd == "version":
        try:
            if args.version_cmd == "status":
                return _emit(top_version.status(args.project))
            if args.version_cmd == "capture":
                return _emit(top_version.capture(args.project, args.file, args.artifact, args.output, args.task))
            if args.version_cmd == "verify":
                return _emit(top_version.verify(args.project, args.manifest, args.staged))
            return _emit(top_version.compare(args.left, args.right))
        except (ValueError, OSError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
            return _emit({"verdict": "block", "errors": [str(exc)], "next_hint": "检查范围、文件与Git状态；不自动覆盖或改历史"})
    if args.cmd == "brief":
        return _emit(core.topic_brief(args.project))
    if args.cmd == "doctor":
        return _emit(core.topic_doctor(args.project, links=not args.no_links, full=args.full))
    if args.cmd == "deposit":
        return _emit({
            "tool": "deposit", "verdict": "ok", "retired": True, "node": args.node, "stamped": False,
            "message": "CodeBook 已退役（2026-09-24）：deposit 不再写 last_verified_hash；已有 _codebook/ 按普通文档只读参考。",
            "next_hint": "代码结构用 CodeGraph（codegraph explore / affected），入口写 _codemap.md（≤5KB，入口变了才更新），"
                         "理由写 record add decision --file <路径::符号>；改文件前 record for-file 查相关决策",
        })
    if args.cmd == "verify-pipeline":
        return _emit(core.verify_pipeline(args.project, args.name))
    if args.cmd == "affected":
        scopes: list[str] = []
        gates: list[str] = []
        if args.task:
            inspected = top_plan.inspect(args.project, args.task)
            if "error" in inspected:
                return _emit(inspected)
            scopes = inspected["item"].get("scopes") or []
            gates = inspected["item"].get("gates") or []
        return _emit(core.affected(
            args.project, since=args.since, task_id=args.task,
            task_scopes=scopes, task_gates=gates,
        ))
    if args.cmd == "plan":
        try:
            if args.plan_cmd == "show":
                return _emit(top_plan.show(args.project, fast=args.fast))
            if args.plan_cmd == "list":
                return _emit(top_plan.list_items(args.project, state_filter=args.state))
            if args.plan_cmd == "validate":
                return _emit(top_plan.validate(args.project))
            if args.plan_cmd == "upgrade":
                if not top_qa.is_qa(top_plan._plan_path(args.project)[1]):
                    return _emit({"error": "不是问答格式的计划；先 plan rewrite 草稿.md --to qa 迁移"})
                return _emit(top_qa.upgrade(args.project, apply=args.apply, expect=args.expect))
            if args.plan_cmd == "question":
                if not top_qa.is_qa(top_plan._plan_path(args.project)[1]):
                    return _emit({"error": "不是问答格式的计划（plan question 只用于问答格式）"})
                return _emit(top_qa.question_view(args.project, args.id, full=args.full))
            if args.plan_cmd == "next":
                return _emit(top_plan.next_tasks(args.project))
            if args.plan_cmd == "compact":
                return _emit(top_plan.compact(args.project, apply=args.apply))
            if args.plan_cmd == "inspect":
                return _emit(top_plan.inspect(args.project, args.id))
            if args.plan_cmd == "add":
                return _emit(top_plan.add(
                    args.project, title=args.title, item_id=args.id,
                    parent=args.parent, deps=args.dep, scopes=args.scope, gates=args.gate,
                    depends_on=args.depends_on,
                ))
            if args.plan_cmd == "edit":
                return _emit(top_plan.edit(
                    args.project, args.id, title=args.title,
                    add_deps=args.add_dep, remove_deps=args.remove_dep,
                    add_scopes=args.add_scope, remove_scopes=args.remove_scope,
                    add_gates=args.add_gate, remove_gates=args.remove_gate,
                ))
            if args.plan_cmd == "start":
                return _emit(top_plan.start(args.project, args.id, worktree=args.worktree))
            if args.plan_cmd == "complete":
                return _emit(top_plan.complete(
                    args.project, args.id, args.evidence, args.no_artifact_reason,
                    log=not args.no_log, commit=args.commit, merge=args.merge,
                    decisions=args.decision,
                ))
            if args.plan_cmd == "note":
                return _emit(top_plan.note(args.project, args.text, item_id=args.id, kind=args.kind))
            if args.plan_cmd == "insert":
                return _emit(top_plan.insert(
                    args.project, args.after_id, title=args.title, gates=args.gate,
                    reason=args.reason, rewire=args.rewire, log=not args.no_log,
                ))
            if args.plan_cmd == "replan":
                return _emit(top_plan.replan(
                    args.project, args.id, reason=args.reason, replace_with=args.replace_with,
                    gates=args.gate, log=not args.no_log,
                ))
            if args.plan_cmd == "merge":
                return _emit(top_plan.merge(args.project, args.id))
            if args.plan_cmd == "handoff":
                return _emit(top_plan.handoff(args.project, args.doc, commit=not args.no_commit))
            if args.plan_cmd == "milestone":
                return _emit(top_plan.milestone(args.project, args.phase, allow_open=args.allow_open))
            if args.plan_cmd == "archive":
                return _emit(top_plan.archive(args.project, keep=args.keep))
            if args.plan_cmd == "phase":
                if args.phase_cmd == "add":
                    return _emit(top_plan.phase_add(args.project, title=args.title, summary=args.summary,
                                                    after=args.after))
                if args.phase_cmd == "edit":
                    return _emit(top_plan.phase_edit(args.project, args.id, title=args.title, summary=args.summary))
                return _emit(top_plan.phase_cancel(args.project, args.id, reason=args.reason))
            if args.plan_cmd == "goal":
                return _emit(top_plan.set_goal(args.project, args.text))
            if args.plan_cmd == "migrate":
                return _emit(top_plan.migrate(args.project, args.draft, apply=args.apply,
                                              accept_dropped=args.accept_dropped))
            if args.plan_cmd == "block":
                return _emit(top_plan.block(args.project, args.id, args.reason, log=not args.no_log))
            if args.plan_cmd == "reopen":
                return _emit(top_plan.reopen(args.project, args.id, log=not args.no_log))
            if args.plan_cmd == "cancel":
                return _emit(top_plan.cancel(args.project, args.id, args.reason, log=not args.no_log))
        except top_plan.PlanConflict as exc:
            return _emit({"verdict": "block", "errors": [str(exc)], "next_hint": "重读 plan 后重试"})
        except top_plan.PlanError as exc:
            return _emit({"verdict": "block", "errors": [str(exc)], "next_hint": "修正任务状态/参数后重试"})
    if args.cmd == "owner":
        if args.owner_cmd == "list":
            return _emit(top_owner.list_owners(args.project))
        if args.owner_cmd == "show":
            return _emit(top_owner.show(args.project, args.column))
        if args.owner_cmd == "resolve":
            return _emit(top_owner.resolve_ref(args.project, args.ref))
    if args.cmd == "record":
        if args.record_cmd == "add":
            return _emit(top_record.add(
                args.project, args.kind, title=args.title, summary=args.summary,
                phase=args.phase, evidence=args.evidence,
                rationale=args.rationale, alternative=args.alternative, file=args.file,
                test=args.test, request=args.request, source=args.source,
                commit=args.commit, follow_up=args.follow_up, supersedes=args.supersedes,
            ))
        if args.record_cmd == "search":
            return _emit(top_record.search(args.project, args.query, kind=args.kind, limit=args.limit))
        if args.record_cmd == "for-file":
            return _emit(top_record.for_file(args.project, args.path, symbol=args.symbol, limit=args.limit))
        if args.record_cmd == "list":
            return _emit(top_record.list_records(args.project, args.kind))
        if args.record_cmd == "show":
            return _emit(top_record.show(args.project, args.ref))
    return 2  # argparse required=True 已兜底, 防御性返回


if __name__ == "__main__":
    raise SystemExit(main())
