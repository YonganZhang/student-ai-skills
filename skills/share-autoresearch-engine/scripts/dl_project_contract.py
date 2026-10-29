#!/usr/bin/env python3
"""Create and check a project-level deep-learning contract (stdlib only).

  dl_project_contract.py init  --project ROOT [--path REL] [--add-pointer]
  dl_project_contract.py check --project ROOT [--path REL]

init  writes assets/project-contract.template.md to the project (default
      _wiki-methodology/_wiki/_methods/dl-project-contract.md when _wiki-methodology/ exists, else
      docs/dl-project-contract.md); refuses to overwrite; prints the AGENTS.md pointer line, or appends it with
      --add-pointer when no line in AGENTS.md mentions the contract path yet.
check verifies: the contract exists; all numbered sections of the template are present; no '<<填写' placeholder is
      left; every marked project path exists; AGENTS.md mentions the contract path.

Path markers -- the only spans check treats as paths (other backticked text such as `TP/(TP+FP)`, `fit/select/evaluate`
or commands is never checked):
  `path:REL`        REL relative to the project root, e.g. `path:src/train.py`, `path:train.py`; must exist.
  `path:/abs/...`   absolute, `~/...` or URL: listed under external_not_checked (informational, never a finding).
  `path:<...>`      text with < or > is a placeholder/example and is skipped.
  [text](REL)       relative Markdown links/images outside code spans/fences, resolved from the contract's own
                    directory (#anchor stripped; <dest with spaces> and one level of balanced parentheses supported);
                    URLs, mailto: and pure #anchors are skipped, absolute targets go to external_not_checked.
Exit codes: 0 ok, 1 findings (printed as JSON), 2 bad arguments / missing project.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / 'assets' / 'project-contract.template.md'
PLACEHOLDER = '<<填写'
SECTION = re.compile(r'^## (\d+)\. ', re.M)
PATH_MARKER = re.compile(r'`path:([^`\n]+)`')
# [text](dest "title"), dest either <with spaces> or without spaces with at most one level of balanced parentheses
LINK = re.compile(r'\[[^\]\n]*\]\((?:<([^>\n]+)>|((?:[^()\s]|\([^()\s]*\))+))(?:\s+"[^"\n]*")?\)')
CODE = re.compile(r'```.*?```|`[^`\n]*`', re.S)          # code fences and spans: commands, never links
URL = re.compile(r'^[A-Za-z][A-Za-z0-9+.-]*:')            # http:, https:, mailto:, file:, ...


def default_path(project: Path) -> str:
    if (project / '_wiki-methodology').is_dir():
        return '_wiki-methodology/_wiki/_methods/dl-project-contract.md'
    return 'docs/dl-project-contract.md'


def pointer_line(rel: str) -> str:
    return (f'- 做深度学习训练、调参、改结构、移植论文模块或模型比较前，先读 `{rel}`（项目深度学习合同）；'
            f'通用流程见 `~/.claude/skills/share-autoresearch-engine/references/workflow/standard-flow.md`。')


def cmd_init(project: Path, rel: str, add_pointer: bool) -> int:
    target = project / rel
    if target.exists():
        print(json.dumps(dict(status='exists', path=str(target)), ensure_ascii=False))
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('x', encoding='utf-8') as f:
        f.write(TEMPLATE.read_text(encoding='utf-8'))
    line = pointer_line(rel)
    agents = project / 'AGENTS.md'
    added = False
    if add_pointer:
        text = agents.read_text(encoding='utf-8') if agents.exists() else ''
        if rel not in text:
            with agents.open('a', encoding='utf-8') as f:
                f.write(('' if text.endswith('\n') or not text else '\n') + line + '\n')
            added = True
    print(json.dumps(dict(status='created', path=str(target), pointer=line, pointer_added=added), ensure_ascii=False))
    return 0


def is_external(path: str) -> bool:
    return path.startswith(('/', '~', '\\')) or bool(re.match(r'^[A-Za-z]:[\\/]', path))


def check_paths(project: Path, target: Path, text: str) -> tuple[list, list]:
    """(findings, external_not_checked) for `path:` markers and relative Markdown links; see the module docstring."""
    findings, external = [], []
    for raw in sorted(set(PATH_MARKER.findall(text))):
        token = raw.strip()
        if not token or '<' in token or '>' in token:
            continue
        if is_external(token) or URL.match(token):
            external.append(token)
        elif not (project / token).exists():
            findings.append(f'path not found: {token}')
    for raw in sorted({a or b for a, b in LINK.findall(CODE.sub('', text))}):
        dest = unquote(raw.split('#', 1)[0])
        if not dest or URL.match(raw):
            continue
        if is_external(dest):
            external.append(dest)
        elif not (target.parent / dest).exists():
            findings.append(f'link not found: {raw}')
    return findings, sorted(set(external))


def cmd_check(project: Path, rel: str) -> int:
    target = project / rel
    findings = []
    if not target.is_file():
        print(json.dumps(dict(status='missing', path=str(target)), ensure_ascii=False))
        return 1
    text = target.read_text(encoding='utf-8')
    want = set(SECTION.findall(TEMPLATE.read_text(encoding='utf-8')))
    have = set(SECTION.findall(text))
    for n in sorted(want - have, key=int):
        findings.append(f'section {n} missing')
    for i, line in enumerate(text.splitlines(), 1):
        if PLACEHOLDER in line:
            findings.append(f'line {i}: unfilled placeholder')
    path_findings, external = check_paths(project, target, text)
    findings += path_findings
    agents = project / 'AGENTS.md'
    if not agents.exists() or rel not in agents.read_text(encoding='utf-8'):
        findings.append('AGENTS.md has no pointer to the contract')
    print(json.dumps(dict(status='ok' if not findings else 'findings', path=str(target), findings=findings,
                          external_not_checked=external), ensure_ascii=False, indent=1))
    return 0 if not findings else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('command', choices=('init', 'check'))
    ap.add_argument('--project', required=True, type=Path)
    ap.add_argument('--path')
    ap.add_argument('--add-pointer', action='store_true')
    a = ap.parse_args(argv)
    if not a.project.is_dir():
        print(f'not a directory: {a.project}', file=sys.stderr)
        return 2
    rel = a.path or default_path(a.project)
    if a.command == 'init':
        return cmd_init(a.project, rel, a.add_pointer)
    return cmd_check(a.project, rel)


if __name__ == '__main__':
    raise SystemExit(main())
