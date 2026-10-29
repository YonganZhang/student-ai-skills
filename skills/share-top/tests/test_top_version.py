"""Behavior tests in disposable Git repositories, never the user's branches."""
import json
import subprocess
import sys
from pathlib import Path
import pytest

SKILL=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SKILL/'scripts'))
import top_version as v

def git(root,*args):
    return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True,text=True).stdout.strip()

@pytest.fixture
def repo(tmp_path):
    p=tmp_path/'repo';p.mkdir();git(p,'init','-b','main')
    git(p,'config','user.email','test@example.invalid');git(p,'config','user.name','Test')
    (p/'code.py').write_text('baseline\n');(p/'.gitignore').write_text('weights.bin\n')
    git(p,'add','code.py','.gitignore');git(p,'commit','-m','base')
    return p

def capture(repo,tmp_path,files=None,artifacts=None,name='snapshot'):
    out=tmp_path/name
    v.capture(repo,files or ['code.py'],artifacts or [],out,task='T1')
    return out/'manifest.json'

def test_dirty_and_untracked_are_copied_without_commit(repo,tmp_path):
    head=git(repo,'rev-parse','HEAD');(repo/'code.py').write_text('dirty\n')
    (repo/'extra.py').write_text('untracked\n')
    p=capture(repo,tmp_path,['code.py','extra.py']);m=v.load_snapshot(p)
    assert m['context']['dirty'] and len(m['files'])==2
    assert git(repo,'rev-parse','HEAD')==head
    assert git(repo,'diff','--cached','--name-only')==''
    assert v.verify(repo,p)['verdict']=='ok'
    (repo/'extra.py').write_text('changed')
    assert v.verify(repo,p)['verdict']=='stale'

def test_index_and_worktree_are_distinct(repo,tmp_path):
    (repo/'code.py').write_text('stage\n');git(repo,'add','code.py')
    (repo/'code.py').write_text('worktree\n');p=capture(repo,tmp_path)
    assert v.verify(repo,p)['verdict']=='ok'
    assert v.verify(repo,p,staged=True)['verdict']=='stale'
    git(repo,'add','code.py');assert v.verify(repo,p,staged=True)['verdict']=='ok'

def test_artifact_drift_is_not_hidden_by_same_commit(repo,tmp_path):
    (repo/'weights.bin').write_bytes(b'old');p=capture(repo,tmp_path,artifacts=['weights.bin'])
    (repo/'weights.bin').write_bytes(b'new')
    assert v.verify(repo,p)['verdict']=='stale'
    assert len(list((p.parent/'blobs').iterdir()))==1

def test_different_worktrees_do_not_share_uncommitted_content(repo,tmp_path):
    other=tmp_path/'other';git(repo,'worktree','add','-b','candidate',str(other))
    (repo/'code.py').write_text('only-main\n');p=capture(repo,tmp_path)
    assert v.verify(other,p)['verdict']=='stale'
    (other/'code.py').write_text('only-main\n')
    result=v.verify(other,p);assert result['verdict']=='ok' and result['provenance_changed']
    assert result['current_context']['worktree']!=result['captured_context']['worktree']

def test_commit_change_does_not_forge_test_success(repo,tmp_path):
    p=capture(repo,tmp_path)
    git(repo,'commit','--allow-empty','-m','unrelated provenance')
    result=v.verify(repo,p)
    assert result['verdict']=='ok' and result['provenance_changed']
    assert 'not test success' in result['note']

def test_deleted_source_and_detached_head(repo,tmp_path):
    git(repo,'checkout','--detach');(repo/'code.py').unlink()
    p=capture(repo,tmp_path);assert v.load_snapshot(p)['context']['branch'] is None
    assert v.verify(repo,p)['verdict']=='ok'
    assert v.verify(repo,p,staged=True)['verdict']=='stale'
    git(repo,'add','-u');assert v.verify(repo,p,staged=True)['verdict']=='ok'

def test_immutable_output_and_corruption(repo,tmp_path):
    p=capture(repo,tmp_path)
    with pytest.raises(ValueError,match='exists'):capture(repo,tmp_path)
    blob=next((p.parent/'blobs').iterdir());blob.write_bytes(b'corrupted')
    with pytest.raises(ValueError,match='blob changed'):v.verify(repo,p)

def test_reject_escape_symlink_and_git_metadata(repo,tmp_path):
    (repo/'link').symlink_to(repo/'code.py')
    for path in ['../outside','.git/config','link']:
        with pytest.raises(ValueError):capture(repo,tmp_path,[path])
    with pytest.raises(ValueError,match='metadata'):
        v.capture(repo,['code.py'],[],repo/'.git'/'snapshot')

def test_capture_detects_change_between_observations(repo,tmp_path,monkeypatch):
    original=v.file_record;calls=0
    def changed(*args):
        nonlocal calls
        calls+=1
        if calls==2:(repo/'code.py').write_text('concurrent edit\n')
        return original(*args)
    monkeypatch.setattr(v,'file_record',changed)
    with pytest.raises(ValueError,match='changed'):capture(repo,tmp_path)
    assert not (tmp_path/'snapshot').exists()

def test_compare_declared_content_only(repo,tmp_path):
    a=capture(repo,tmp_path,name='a');(repo/'code.py').write_text('new\n')
    b=capture(repo,tmp_path,name='b');r=v.compare(a,b)
    assert not r['same_content'] and r['changed_paths']==['code.py']

def test_other_repository_blocked(repo,tmp_path):
    p=capture(repo,tmp_path);other=tmp_path/'clone'
    git(tmp_path,'clone',str(repo),str(other))
    with pytest.raises(ValueError,match='different repository'):v.verify(other,p)

def test_cli_reports_stale_with_nonzero_exit(repo,tmp_path):
    p=capture(repo,tmp_path);(repo/'code.py').write_text('drift')
    r=subprocess.run([sys.executable,str(SKILL/'scripts/sixone-cli.py'),'version','verify',str(repo),str(p)],capture_output=True,text=True)
    assert r.returncode==1 and json.loads(r.stdout)['verdict']=='stale'

def test_unborn_repository(repo,tmp_path):
    other=tmp_path/'unborn';other.mkdir();git(other,'init')
    (other/'draft.txt').write_text('new')
    p=capture(other,tmp_path,['draft.txt']);assert v.load_snapshot(p)['context']['head'] is None
    assert v.verify(other,p)['verdict']=='ok'

def test_executable_mode_bound(repo,tmp_path):
    p=capture(repo,tmp_path);(repo/'code.py').chmod(0o755)
    assert v.verify(repo,p)['verdict']=='stale'

def test_output_alias_cannot_write_git_metadata(repo):
    (repo/'alias').symlink_to(repo/'.git',target_is_directory=True)
    with pytest.raises(ValueError,match='symlinks'):
        v.capture(repo,['code.py'],[],repo/'alias'/'injected')
    assert not (repo/'.git'/'injected').exists()

def test_staged_deletion_captured(repo,tmp_path):
    git(repo,'rm','code.py')
    p=capture(repo,tmp_path)
    assert v.load_snapshot(p)['files'][0]['kind']=='deleted'
    assert v.verify(repo,p,staged=True)['verdict']=='ok'

def test_literal_filename_is_not_a_git_pathspec(repo,tmp_path):
    (repo/'a*.py').write_text('literal');(repo/'alpha.py').write_text('other')
    git(repo,'add','--','a*.py','alpha.py');git(repo,'commit','-m','literal paths')
    p=capture(repo,tmp_path,['a*.py'])
    assert v.verify(repo,p,staged=True)['verdict']=='ok'

def test_rebase_retains_content_but_reports_new_provenance(repo,tmp_path):
    git(repo,'checkout','-b','candidate')
    (repo/'code.py').write_text('candidate');git(repo,'add','code.py');git(repo,'commit','-m','candidate')
    p=capture(repo,tmp_path)
    git(repo,'checkout','main');(repo/'README.md').write_text('main change')
    git(repo,'add','README.md');git(repo,'commit','-m','advance main')
    git(repo,'checkout','candidate');git(repo,'rebase','main')
    result=v.verify(repo,p)
    assert result['verdict']=='ok' and result['provenance_changed']
    assert 'undeclared dependencies remain unknown' in result['note']

def test_merge_result_changes_captured_input(repo,tmp_path):
    p=capture(repo,tmp_path)
    git(repo,'checkout','-b','candidate');(repo/'code.py').write_text('new behavior')
    git(repo,'add','code.py');git(repo,'commit','-m','candidate')
    git(repo,'checkout','main');git(repo,'merge','--no-ff','candidate','-m','integrate')
    assert v.verify(repo,p)['verdict']=='stale'
