#!/usr/bin/env python3
"""doctree — optional knowledge tree: derived topic navigation over a project's existing docs.

Docs stay where they are and are never edited. Enabled only when the project has
_meta/_doc_tree.yml (nodes, scan scope, mount rules, outputs); per-doc topics and summaries live in
_meta/_doc_summaries.yml. TREE.md, the node pages and CATALOG.md are generated, byte-deterministic.

Commands
  build                 write the generated pages listed in the output manifest; deletes only stale managed pages
  check                 structure (block) / generated-page staleness (block) / summary drift (warn)
  place FILE | --title  candidate nodes for a doc; never writes; "uncertain" when unsure
  show [NODE] [--doc P] outline, one node, or where one doc sits and where each field comes from
  summaries stamp P...  after reviewing a doc's summary, record reviewed_sha (dry run unless --write)

Examples
  python3 doctree.py check --format json
  python3 doctree.py build
  python3 doctree.py place drafts/new-finding.md
  python3 doctree.py summaries stamp _wiki-methodology/_wiki/entities/login.md --write

Paths on the command line are relative to the current directory; paths inside the config are
relative to the project root (found from --project like topic-brief).
Exit codes: 0 ok (warnings allowed; also check/show when not enabled) · 1 blocked: check found
block issues, build refused to overwrite a hand-written file, stamp rejected its inputs (nothing
written) · 2 usage or config error, or build/place/stamp when not enabled · 3 runtime error
(I/O, missing PyYAML; build may be partial — the JSON lists written/failed). Diagnostics go to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import doctree_summaries  # noqa: E402  (module attribute calls keep stamp_text patchable in tests)
from doctree_check import STRUCTURAL, run_check, verdict  # noqa: E402
from doctree_model import DEFAULT_TREE, ConfigError, MissingDependency, content_sha, load_config, read_text_strict  # noqa: E402
from doctree_scan import load_docs  # noqa: E402
from doctree_summaries import load_summaries  # noqa: E402
from doctree_place import place  # noqa: E402
from doctree_render import ancestry, children, depth_first, docs_by_topic, plan_writes, render_all, short  # noqa: E402

EXIT_OK, EXIT_BLOCK, EXIT_USAGE, EXIT_RUNTIME = 0, 1, 2, 3


def wants_json(argv: list[str]) -> bool:
    return "--json" in argv or any(a == "--format=json" for a in argv) or any(
        a == "--format" and i + 1 < len(argv) and argv[i + 1] == "json" for i, a in enumerate(argv))


class Fail(Exception):
    def __init__(self, code: int, kind: str, message: str, enabled: bool | None = None):
        super().__init__(message)
        self.code, self.kind, self.message, self.enabled = code, kind, message, enabled


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # usage errors: same exit 2, JSON when asked
        raise Fail(EXIT_USAGE, "usage", f"{self.prog}: {message}")


def emit(obj: dict, as_json: bool, text: str = "") -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    elif text:
        print(text)


def find_root(start: Path) -> Path:
    try:
        from topic_brief import find_project_root
    except Exception:  # pragma: no cover - copied without topic-brief: the given path is the root
        return start.resolve()
    return find_project_root(start)


def context(args):
    root = find_root(Path(args.project))
    tree = Path(args.tree).resolve() if args.tree else root / DEFAULT_TREE
    if not tree.is_file():
        if args.tree:
            raise Fail(EXIT_USAGE, "usage", f"tree config not found: {args.tree}")
        return root, None, None
    summaries = Path(args.summaries).resolve() if args.summaries else None
    out = Path(args.out).resolve() if getattr(args, "out", None) else None
    cfg = load_config(root, tree, out, summaries)
    if args.summaries and not cfg.summaries_path.is_file():
        raise Fail(EXIT_USAGE, "usage", f"summaries file not found: {args.summaries}")
    return root, cfg, load_summaries(cfg.summaries_path)


def atomic_write(path: Path, text: str) -> None:
    from top_qa import atomic_write as replace_file  # unique temp name, fsync, keeps the file mode

    replace_file(path, text)


# --------------------------------------------------------------------------- commands


def cmd_check(cfg, entries, args, as_json: bool) -> int:
    issues = run_check(cfg, entries, load_docs(cfg, entries))
    v = verdict(issues)
    counts = {s: sum(1 for i in issues if i.severity == s) for s in ("block", "warn", "info")}
    if as_json:
        emit({"schema_version": "doctree-check/v1", "enabled": True, "verdict": v, "summary": counts,
              "issues": [i.as_dict() for i in issues]}, True)
    elif args.format == "tsv":
        for i in issues:
            print(f"{i.severity}\t{i.code}\t{i.where}\t{i.message}")
    else:
        per: dict[str, int] = {}
        for i in issues:
            per[i.code] = per.get(i.code, 0) + 1
        for i in issues:
            if i.severity == "info":
                print(f"[info] {i.code} {i.message}")
            elif args.verbose or per[i.code] <= 5:
                print(f"[{i.severity}] {i.code} {i.where} — {i.message}")
        for code, n in sorted(per.items()):
            sev = next(i.severity for i in issues if i.code == code)
            if n > 5 and not args.verbose and sev != "info":
                print(f"[{sev}] {code} ×{n} (use -v to list)")
        print(f"doctree check: {v} (block={counts['block']} warn={counts['warn']})")
    return EXIT_BLOCK if v == "block" else EXIT_OK


def cmd_build(cfg, entries, args, as_json: bool) -> int:
    docs = load_docs(cfg, entries)
    blocking = [i for i in run_check(cfg, entries, docs) if i.severity == "block" and i.code in STRUCTURAL]
    result = {"schema_version": "doctree-build/v1", "enabled": True, "written": [], "unchanged": [],
              "deleted": [], "failed": [], "refused": [], "blocking": [i.as_dict() for i in blocking]}
    if blocking:
        for i in blocking:
            print(f"doctree build: [block] {i.code} {i.where} — {i.message}", file=sys.stderr)
        emit(result, as_json, "doctree build: refused, fix the tree structure first (see stderr)")
        return EXIT_BLOCK
    wp = plan_writes(cfg, render_all(cfg, docs))
    if wp.unmanaged_targets:
        result["refused"] = [cfg.rel(p) for p in wp.unmanaged_targets]
        for p in wp.unmanaged_targets:
            print(f"doctree build: {cfg.rel(p)} exists and is not a generated page; not overwriting", file=sys.stderr)
        emit(result, as_json, "doctree build: refused, nothing written")
        return EXIT_BLOCK
    for p, text in wp.write.items():
        try:
            atomic_write(p, text)
            result["written"].append(cfg.rel(p))
        except OSError as exc:
            result["failed"].append({"path": cfg.rel(p), "error": f"{type(exc).__name__}: {exc.strerror or exc}"})
    for p in wp.delete:
        try:
            p.unlink()
            result["deleted"].append(cfg.rel(p))
        except OSError as exc:
            result["failed"].append({"path": cfg.rel(p), "error": f"{type(exc).__name__}: {exc.strerror or exc}"})
    result["unchanged"] = [cfg.rel(p) for p in wp.unchanged]
    for f in result["failed"]:
        print(f"doctree build: failed {f['path']}: {f['error']}", file=sys.stderr)
    on_tree = sum(1 for d in docs if d.topics)
    emit(result, as_json, f"doctree build: written={len(result['written'])} unchanged={len(result['unchanged'])} "
                          f"deleted={len(result['deleted'])} failed={len(result['failed'])}; "
                          f"{on_tree} of {len(docs)} docs on {len(cfg.nodes)} nodes")
    return EXIT_RUNTIME if result["failed"] else EXIT_OK


def cmd_place(cfg, entries, args, as_json: bool) -> int:
    if not (args.file or args.title or args.summary):
        raise Fail(EXIT_USAGE, "usage", "doctree place: give a file or --title/--summary")
    file = Path(args.file) if args.file else None
    if file is not None and not file.is_file():
        raise Fail(EXIT_USAGE, "usage", f"doctree place: no such file {file}")
    r = place(cfg, load_docs(cfg, entries), file, args.title or "", args.summary or "")
    label = {"rule": "挂载规则命中", "confident": "建议", "uncertain": "不确定",
             "new-node": "不确定（可能需要新节点）"}[r["verdict"]]
    lines = [f"{label}: {r['title'] or r['file']}"]
    if r["mount_rule"]:
        lines.append(f"  路径命中整组挂载规则 → {', '.join(r['mount_rule'])}（不需要写 topics）")
    if not r["calibrated"]:
        lines.append("  判定线未校准（_doc_tree.yml 的 place.min_score/min_margin），只给候选")
    for i, c in enumerate(r["candidates"], 1):
        lines.append(f"  {i}. {c['node']} ({c['path']}) score={c['score']:.3f} 依据: {' '.join(c['why'])}")
    if r["verdict"] == "confident":
        lines.append(f"  登记：在 {cfg.rel(cfg.summaries_path)} 加 topics: [{r['candidates'][0]['node']}] 和 summary")
    if "suggest_new_node" in r:
        lines.append(f"  建议新节点，父节点 `{r['suggest_new_node']['parent']}`；新节点由维护者审核后写进 {cfg.rel(cfg.tree_path)}")
    emit(r, as_json, "\n".join(lines))
    return EXIT_OK


def cmd_show(cfg, entries, args, as_json: bool) -> int:
    docs = load_docs(cfg, entries)
    primary, secondary = docs_by_topic([d for d in docs if d.topics])
    if args.doc:
        rel = cfg.rel(Path(args.doc).resolve())
        hit = next((d for d in docs if d.path == rel), None)
        if hit is None:
            raise Fail(EXIT_USAGE, "usage", f"{args.doc}: not in the scan scope")
        e = entries.get(rel)
        review = "none" if e is None or not e.summary else ("auto" if e.source == "auto" else (
            "fresh" if e.reviewed_sha and e.reviewed_sha == content_sha(cfg.root / rel) else "stale"))
        obj = {"schema_version": "doctree-show/v1", "enabled": True, "doc": rel, "title": hit.title,
               "topics": hit.topics, "topics_from": hit.topic_src, "summary": hit.summary,
               "summary_from": hit.summary_src, "review": review,
               "paths": [" › ".join(ancestry(cfg, t)) for t in hit.topics]}
        text = (f"{hit.title}\n  topics: {', '.join(hit.topics) or '-'} (from {hit.topic_src})\n"
                f"  summary ({hit.summary_src}, review={review}): {hit.summary}\n"
                + "".join(f"  path: {p}\n" for p in obj["paths"]))
        emit(obj, as_json, text.rstrip("\n"))
        return EXIT_OK
    if args.node:
        if args.node not in cfg.nodes:
            raise Fail(EXIT_USAGE, "usage", f"unknown node {args.node}")
        n = cfg.nodes[args.node]
        obj = {"schema_version": "doctree-show/v1", "enabled": True, "node": n.id, "path": " › ".join(ancestry(cfg, n.id)),
               "one_line": n.one_line, "children": children(cfg, n.id),
               "docs": [d.path for d in sorted(primary.get(n.id, []), key=lambda d: d.path)],
               "also": [d.path for d in sorted(secondary.get(n.id, []), key=lambda d: d.path)]}
        lines = [obj["path"], n.one_line] + [f"  + {c}: {cfg.nodes[c].title}" for c in obj["children"]]
        lines += [f"  - {d.path} — {short(d.summary, 90)}" for d in sorted(primary.get(n.id, []), key=lambda d: d.path)]
        lines += [f"  ~ {p}" for p in obj["also"]]
        emit(obj, as_json, "\n".join(lines))
        return EXIT_OK
    outline = [{"node": nid, "depth": depth, "title": cfg.nodes[nid].title, "docs": len(primary.get(nid, []))}
               for nid, depth in depth_first(cfg)]
    emit({"schema_version": "doctree-show/v1", "enabled": True, "outline": outline}, as_json,
         "\n".join(f"{'  ' * o['depth']}{o['node']}  {o['title']} ({o['docs']})" for o in outline))
    return EXIT_OK


def cmd_stamp(cfg, _entries, args, as_json: bool) -> int:
    """Lock (shared with every tool writer of this table) -> re-read -> edit only the target entries ->
    refuse if the file changed meanwhile -> atomic replace. Editors outside the tool are not locked out;
    the re-read check catches most of their saves, not all."""
    from top_common import PlanConflict
    from top_qa import project_lock

    path = cfg.summaries_path
    result = {"schema_version": "doctree-summaries/v1", "enabled": True, "file": cfg.rel(path), "written": False,
              "changed": [], "unchanged": [], "failed": []}

    def reject(failed: list[dict]) -> int:
        result["failed"] = failed
        for f in failed:
            print(f"doctree summaries stamp: {f['path']}: {f['error']}", file=sys.stderr)
        emit(result, as_json, "doctree summaries stamp: rejected, nothing written")
        return EXIT_BLOCK

    targets, failed = {}, []
    for given in args.paths:
        rel = cfg.rel(Path(given).resolve())
        if (cfg.root / rel).is_file():
            targets[rel] = content_sha(cfg.root / rel)
        else:
            failed.append({"path": given, "error": "file not found inside the project"})
    if not path.is_file():
        failed.append({"path": cfg.rel(path), "error": "no summaries table"})
    if failed:
        return reject(failed)
    try:
        with project_lock(path):
            raw = read_text_strict(path)
            entries = doctree_summaries.parse_summaries(raw, path)
            for rel, sha in targets.items():
                e = entries.get(rel)
                if e is None or not e.summary:
                    failed.append({"path": rel, "error": "no entry with a summary; write the entry first"})
                elif e.problems:
                    failed.append({"path": rel, "error": "entry is malformed (" + "; ".join(e.problems) + "); fix it by hand"})
                elif e.source == "reviewed" and e.reviewed_sha == sha:
                    result["unchanged"].append(rel)
                else:
                    result["changed"].append(rel)
            if failed:
                return reject(failed)
            try:
                new = doctree_summaries.stamp_text(raw, {rel: targets[rel] for rel in result["changed"]}, path)
            except doctree_summaries.StampRefused as exc:
                return reject(exc.failures)
            if args.write and result["changed"]:
                if path.read_bytes() != raw.encode("utf-8"):
                    raise Fail(EXIT_RUNTIME, "conflict", f"{cfg.rel(path)} was changed by someone else while stamping; nothing written, run again")
                try:
                    atomic_write(path, new)
                except OSError as exc:
                    raise Fail(EXIT_RUNTIME, "runtime", f"cannot write {cfg.rel(path)}: {exc}") from exc
                result["written"] = True
    except PlanConflict as exc:
        raise Fail(EXIT_RUNTIME, "conflict", f"doctree summaries stamp: {exc}") from exc
    changed = result["changed"]
    mode = "written" if result["written"] else ("would change (dry run; --write to apply)" if changed else "nothing to change")
    emit(result, as_json, f"doctree summaries stamp: {len(changed)} {mode}; unchanged={len(result['unchanged'])}")
    return EXIT_OK


# --------------------------------------------------------------------------- entry


def build_parser() -> Parser:
    ap = Parser(prog="doctree", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=".", help="any path inside the project (default: current directory)")
    ap.add_argument("--tree", help=f"tree config (default <root>/{DEFAULT_TREE})")
    ap.add_argument("--summaries", help="summaries table (default: `summaries:` in the config, else <root>/_meta/_doc_summaries.yml)")
    fmt = Parser(add_help=False)
    fmt.add_argument("--format", choices=["text", "json"], default="text")
    fmt.add_argument("--json", action="store_const", const="json", dest="format", help="= --format json")
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    b = sub.add_parser("build", parents=[fmt], help="write the generated pages")
    b.add_argument("--out", help="verification output dir instead of the configured paths")
    c = sub.add_parser("check", help="health check (exit 1 on block issues)")
    c.add_argument("--format", choices=["text", "tsv", "json"], default="text")
    c.add_argument("--json", action="store_const", const="json", dest="format", help="= --format json")
    c.add_argument("--out", help="check a verification output dir instead of the configured paths")
    c.add_argument("-v", "--verbose", action="store_true", help="list every issue (text format)")
    p = sub.add_parser("place", parents=[fmt], help="candidate nodes for a doc (read-only)")
    p.add_argument("file", nargs="?")
    p.add_argument("--title")
    p.add_argument("--summary")
    s = sub.add_parser("show", parents=[fmt], help="outline, one node, or one doc")
    s.add_argument("node", nargs="?")
    s.add_argument("--doc", help="doc path: topics, summary and where each comes from")
    sm = sub.add_parser("summaries", help="maintain the summaries table")
    smsub = sm.add_subparsers(dest="action", required=True, parser_class=Parser)
    st = smsub.add_parser("stamp", parents=[fmt], help="record reviewed_sha after reviewing summaries")
    st.add_argument("paths", nargs="+")
    st.add_argument("--write", action="store_true", help="write the table (default: dry run)")
    return ap


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    as_json = wants_json(argv)
    enabled: bool | None = None
    try:
        args = build_parser().parse_args(argv)
        as_json = args.format == "json"
        _root, cfg, entries = context(args)
        enabled = cfg is not None
        if cfg is None:
            msg = f"doctree: not enabled (no {DEFAULT_TREE})"
            if args.cmd in ("check", "show"):
                schema = "doctree-check/v1" if args.cmd == "check" else "doctree-show/v1"
                emit({"schema_version": schema, "enabled": False, "verdict": "ok", "issues": []}, as_json, msg)
                return EXIT_OK
            raise Fail(EXIT_USAGE, "not-enabled", msg, enabled=False)
        cmd = {"build": cmd_build, "check": cmd_check, "place": cmd_place, "show": cmd_show,
               "summaries": cmd_stamp}[args.cmd]
        return cmd(cfg, entries, args, as_json)
    except ConfigError as exc:
        err = Fail(EXIT_USAGE, "config", f"doctree: config error: {exc}", enabled=True)
    except Fail as exc:
        err = exc
    except MissingDependency as exc:
        err = Fail(EXIT_RUNTIME, "runtime", f"doctree: {exc}", enabled=enabled)
    except OSError as exc:
        err = Fail(EXIT_RUNTIME, "runtime", f"doctree: {type(exc).__name__}: {exc}", enabled=enabled)
    print(err.message, file=sys.stderr)
    if as_json:
        emit({"schema_version": "doctree-error/v1", "ok": False,
              "enabled": err.enabled if err.enabled is not None else enabled,
              "error": {"kind": err.kind, "exit": err.code, "message": err.message}}, True)
    return err.code


if __name__ == "__main__":
    raise SystemExit(main())
