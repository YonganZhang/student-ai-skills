"""Explicit-scope Git/content snapshots. No commits, checkout, restore or hooks.

This records files the caller declares, not automatic dependency closure or test
success. Git provenance and content identity deliberately remain separate.
"""
from __future__ import annotations
import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path
from datetime import datetime, timezone

SCHEMA = 'sixone-version/v1'
COPY_LIMIT = 16 * 1024 * 1024
TOTAL_LIMIT = 64 * 1024 * 1024

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def canonical(data) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode()

def git(root, *args, optional=False):
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
    r = subprocess.run(['git', '-C', str(root), '--literal-pathspecs', *args], capture_output=True, timeout=20, env=env)
    if r.returncode and not optional:
        raise ValueError(f'git {args[0]} failed: {r.stderr.decode(errors="replace")[:300]}')
    return r

def root_for(project):
    return Path(git(Path(project).resolve(), 'rev-parse', '--show-toplevel').stdout.decode().strip()).resolve()

def context(root):
    head = git(root, 'rev-parse', '--verify', 'HEAD', optional=True)
    branch = git(root, 'symbolic-ref', '--quiet', '--short', 'HEAD', optional=True)
    common = git(root, 'rev-parse', '--git-common-dir').stdout.decode().strip()
    dirty = git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=normal').stdout
    # Keep rename records together; no content/path listing in the compact status.
    chunks = iter(dirty.split(b'\0')); counts = {}
    for entry in chunks:
        if not entry: continue
        code = entry[:2].decode(errors='replace'); counts[code] = counts.get(code, 0) + 1
        if 'R' in code or 'C' in code: next(chunks, None)
    return dict(worktree=str(root), git_common_dir=str((root/common).resolve()),
                head=head.stdout.decode().strip() if head.returncode == 0 else None,
                branch=branch.stdout.decode().strip() if branch.returncode == 0 else None,
                dirty=bool(dirty), status_counts=counts, status_hash=digest(dirty),
                index_hash=digest(git(root, 'ls-files', '--stage', '-z').stdout))

def status(project):
    root = root_for(project)
    return dict(schema_version=SCHEMA, verdict='ok', context=context(root),
        worktrees_porcelain=git(root, '-c', 'core.quotePath=false', 'worktree', 'list', '--porcelain').stdout.decode(),
        note='Branch names locate work; only declared content is versioned by capture. No CodeGraph freshness claim.')

def safe_path(root, rel):
    p = Path(rel)
    if p.is_absolute() or not p.parts or any(x in ('.git', '..') for x in p.parts):
        raise ValueError(f'expected repository-relative file, outside .git: {rel}')
    cur = root
    for part in p.parts:
        cur = cur / part
        if cur.is_symlink(): raise ValueError(f'symlinks unsupported: {rel}')
    if not cur.resolve().is_relative_to(root): raise ValueError('path escapes repository')
    return cur

def file_record(root, rel, role):
    p = safe_path(root, rel)
    if not p.exists():
        tracked = git(root, 'ls-files', '--error-unmatch', '--', rel, optional=True)
        in_head = git(root, 'cat-file', '-e', 'HEAD:'+rel, optional=True)
        if role != 'source' or (tracked.returncode and in_head.returncode):
            raise ValueError(f'missing input: {rel}')
        return dict(path=rel, role=role, kind='deleted')
    if not p.is_file(): raise ValueError(f'not a regular file: {rel}')
    before=p.stat()
    if role=='source' and before.st_size > COPY_LIMIT:
        raise ValueError(f'source exceeds copy limit; declare retained large asset with --artifact: {rel}')
    h=hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024), b''):h.update(block)
    after=p.stat()
    if (before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
        raise ValueError(f'input changed during capture: {rel}')
    return dict(path=rel, role=role, kind='file', hash_kind='sha256-file-bytes', sha256=h.hexdigest(), size=after.st_size,
                executable=bool(after.st_mode & stat.S_IXUSR))

def capture(project, files, artifacts, output, task=None):
    root=root_for(project);before=context(root)
    if not files: raise ValueError('declare at least one --file; no implicit whole-repository capture')
    names=[Path(p).as_posix() for p in files+artifacts]
    if len(set(names))!=len(names): raise ValueError('duplicate source/artifact declaration')
    out=Path(output).absolute()
    for ancestor in (out, *out.parents):
        if ancestor.is_symlink():raise ValueError('snapshot output cannot traverse symlinks')
    out=out.resolve()
    if out.exists(): raise ValueError('output already exists; use a new directory')
    if '.git' in out.parts or out.is_relative_to(Path(before['git_common_dir'])):
        raise ValueError('snapshot output cannot be inside Git metadata')
    records=[];payload={};total=0
    for name,role in [(p,'source') for p in files]+[(p,'artifact') for p in artifacts]:
        rel=Path(name).as_posix();rec=file_record(root,rel,role);records.append(rec)
        if role=='source' and rec['kind']=='file':
            total+=rec['size']
            if total>TOTAL_LIMIT: raise ValueError('source snapshot exceeds total copy limit')
            data=safe_path(root,rel).read_bytes()
            if digest(data)!=rec['sha256']: raise ValueError(f'input changed: {rel}')
            payload[rec['sha256']]=data
    records.sort(key=lambda r:r['path'])
    # Second observation detects ordinary concurrent edits. It cannot lock writers.
    for rec in records:
        if file_record(root,rec['path'],rec['role'])!=rec:raise ValueError('inputs changed; retry')
    if context(root)!=before:raise ValueError('Git/worktree changed during capture; retry')
    m=dict(schema_version=SCHEMA, content_id=digest(canonical(records)), content_id_kind='sha256-canonical-json-files', files=records,
           context=before, task=task, captured_at=datetime.now(timezone.utc).isoformat(),
           scope='explicit files only; dependency completeness not inferred',
           recoverability='source blobs included; artifact bytes must remain in their existing store',
           consistency='double-read observation; not a lock or an execution sandbox',
           verification='no tests executed or inferred')
    out.mkdir(parents=True,exist_ok=False)
    (out/'blobs').mkdir()
    for h,data in payload.items():
        with (out/'blobs'/h).open('xb') as f:f.write(data)
    with (out/'manifest.json').open('x') as f:json.dump(m,f,ensure_ascii=False,indent=2)
    return dict(schema_version=SCHEMA,verdict='ok',manifest=str(out/'manifest.json'),
                content_id=m['content_id'],context=before,scope=m['scope'],recoverability=m['recoverability'])

def load_snapshot(path):
    path=Path(path);m=json.loads(path.read_text())
    if m.get('schema_version')!=SCHEMA or digest(canonical(m['files']))!=m['content_id']:
        raise ValueError('invalid snapshot schema/content ID')
    if len({r['path'] for r in m['files']})!=len(m['files']):raise ValueError('duplicate snapshot paths')
    for r in m['files']:
        if r['role']=='source' and r['kind']=='file':
            h=r['sha256']
            if len(h)!=64 or any(c not in '0123456789abcdef' for c in h):raise ValueError('invalid blob hash')
            if digest((path.parent/'blobs'/h).read_bytes())!=h:raise ValueError('source snapshot blob changed')
    return m

def staged_record(root, rec):
    # Assets stay in their original store; --staged only changes source inspection.
    if rec['role']=='artifact':return file_record(root,rec['path'],rec['role'])
    info=git(root,'ls-files','--stage','-z','--',rec['path']).stdout.split(b'\0')
    info=[r for r in info if r]
    if not info:return dict(path=rec['path'],role='source',kind='deleted')
    if len(info)!=1:raise ValueError('unmerged index entry')
    meta,path=info[0].split(b'\t',1);mode,oid,stage=meta.split()
    if stage!=b'0' or mode not in (b'100644',b'100755'):raise ValueError('unsupported index entry')
    data=git(root,'cat-file','blob',oid.decode()).stdout
    return dict(path=rec['path'],role='source',kind='file',hash_kind='sha256-file-bytes',sha256=digest(data),size=len(data),executable=mode==b'100755')

def verify(project, manifest, staged=False):
    root=root_for(project);before=context(root);m=load_snapshot(manifest);changes=[]
    if before['git_common_dir']!=m['context']['git_common_dir']:
        raise ValueError('different repository; cross-clone adoption requires explicit review')
    for r in m['files']:
        safe_path(root,r['path'])
        try:actual=staged_record(root,r) if staged else file_record(root,r['path'],r['role'])
        except ValueError as e:changes.append(dict(path=r['path'],reason=str(e)));continue
        if actual!=r:changes.append(dict(path=r['path'],reason='content or mode differs'))
    if context(root)!=before:raise ValueError('Git/worktree changed during verification; retry')
    return dict(schema_version=SCHEMA,verdict='stale' if changes else 'ok',content_id=m['content_id'],
                changes=changes,checked='index sources + live assets' if staged else 'worktree files + live assets',
                provenance_changed=before['head']!=m['context']['head'] or before['branch']!=m['context']['branch'],
                captured_context=m['context'],current_context=before,
                note='Content match is not test success or permission to adopt; undeclared dependencies remain unknown.')

def compare(left,right):
    a=load_snapshot(left);b=load_snapshot(right)
    aa={r['path']:r for r in a['files']};bb={r['path']:r for r in b['files']}
    return dict(schema_version=SCHEMA,verdict='ok',same_content=a['content_id']==b['content_id'],
                changed_paths=[p for p in sorted(aa.keys()|bb.keys()) if aa.get(p)!=bb.get(p)],
                left_context=a['context'],right_context=b['context'],
                note='No automatic test transfer, merge, adoption or rollback.')
