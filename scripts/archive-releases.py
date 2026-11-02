"""Explicit private-GitHub archive workflow; cleanup requires download verification.

Archives complete old release folders (including App permissions/symlinks via
macOS ditto). Never includes personal source/data roots. Run prepare, upload,
then cleanup only after the new release has passed. No implicit deletion.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY = Path('/Users/czy/ProjectManagement/课间归档/历史版本')
SPEC = importlib.util.spec_from_file_location('release_macos', PROJECT/'scripts/release-macos.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def digest(path):
    return release.sha256(path)


def private_name(name):
    p=Path(name)
    return (p.name in {'.env','model.env','campus.db','agent.db'} or
            p.suffix.lower() in {'.db','.sqlite','.sqlite3'} or
            '.connector-secrets' in p.parts or p.is_absolute() or '..' in p.parts)


def audit_zip(path, secrets, depth=0):
    if depth > 4:
        raise RuntimeError('Nested archive exceeds audit depth')
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if info.is_dir(): continue
            if private_name(info.filename):
                raise RuntimeError('Private/unsafe archive member found')
            with z.open(info) as stream: release.check_stream(stream,secrets)
            if info.filename.lower().endswith('.zip'):
                with tempfile.TemporaryFile() as temporary:
                    with z.open(info) as stream: shutil.copyfileobj(stream,temporary)
                    temporary.seek(0)
                    # Source trees include deliberately invalid .zip test fixtures.
                    # Their bytes were scanned above; recurse only into real ZIPs.
                    if temporary.read(4) == b'PK\x03\x04':
                        temporary.seek(0); audit_zip(temporary,secrets,depth+1)
        if z.testzip() is not None: raise RuntimeError('ZIP CRC failed')


def tree_inventory(root, secrets):
    root=Path(root)
    if root.is_symlink() or not root.is_dir(): raise RuntimeError('Expected a real archive directory')
    inventory={}
    for p in sorted(root.rglob('*')):
        relative=p.relative_to(root).as_posix()
        if private_name(relative): raise RuntimeError('Private file in historical release')
        mode=stat.S_IMODE(p.lstat().st_mode)
        if p.is_symlink():
            target=p.readlink()
            if not p.resolve().is_relative_to(root.resolve()): raise RuntimeError('Archive link escapes its root')
            inventory[relative]={'link':str(target),'mode':mode}
        elif p.is_file():
            with p.open('rb') as stream: release.check_stream(stream,secrets)
            if p.suffix.lower()=='.zip': audit_zip(p,secrets)
            inventory[relative]={'sha256':digest(p),'bytes':p.stat().st_size,'mode':mode}
        elif not p.is_dir(): raise RuntimeError('Unexpected archive object')
    return inventory


def save(path, body):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)


def check_private_repo(repo):
    result=json.loads(subprocess.check_output(['gh','repo','view',repo,'--json','nameWithOwner,isPrivate']))
    if result.get('nameWithOwner')!=repo or result.get('isPrivate') is not True:
        raise RuntimeError('Only the explicitly named private repository is allowed')


def prepare(history, staging, plan, secrets):
    history=history.resolve()
    if history!=DEFAULT_HISTORY.resolve(): raise RuntimeError('Unexpected history root')
    if plan.exists(): raise RuntimeError('Existing archive plan is never overwritten')
    staging.mkdir(parents=True,exist_ok=True)
    records=[]
    for root in sorted(history.iterdir()):
        if not root.is_dir() or not re.fullmatch(r'Demo\d+(?:\.\d+){1,3}',root.name):
            raise RuntimeError('Unexpected item in history root')
        manifest=json.loads((root/'manifest.json').read_text())
        if manifest.get('credentials_and_personal_data_in_package') is not False:
            raise RuntimeError('Historical privacy declaration missing')
        tree=tree_inventory(root,secrets)
        # Keep original validation claims; do not manufacture new acceptance.
        for line in (root/'SHA256SUMS.txt').read_text().splitlines():
            sha,name=line.split('  ',1)
            if name not in tree or tree[name].get('sha256')!=sha:
                raise RuntimeError('Historical release SHA mismatch: '+root.name)
        archive=staging/(root.name+'-完整归档.zip')
        if archive.exists(): raise RuntimeError('Staging archive already exists')
        subprocess.run(['ditto','-c','-k','--sequesterRsrc','--keepParent',str(root),str(archive)],check=True)
        audit_zip(archive,secrets)
        records.append({'release':root.name,'local_root':str(root),'archive':str(archive),
                        'sha256':digest(archive),'bytes':archive.stat().st_size,
                        'tree':tree,'original_manifest':manifest,'remote_verified':False})
        print('prepared '+root.name,flush=True)
    save(plan,{'schema':'private-release-archive-v1','records':records})


def upload(plan, repo, target):
    check_private_repo(repo)
    body=json.loads(plan.read_text())
    for row in body['records']:
        path=Path(row['archive'])
        if digest(path)!=row['sha256']: raise RuntimeError('Staged archive changed')
        tag='archive/'+row['release'].lower()+'-20261102'
        view=subprocess.run(['gh','release','view',tag,'--repo',repo,'--json','assets'],capture_output=True)
        if view.returncode:
            note=path.with_suffix('.md')
            note.write_text('历史版本完整归档，供恢复使用。当前推荐使用最新修复版本。\n\n'
                +'原版本与验证范围以归档内manifest及说明为准；不将历史报告视为本次重新验收。\n'
                +'包含原App、安装包、源码快照、说明和验证材料；无个人配置、数据库或密钥。\n\n'
                +'SHA256: `'+row['sha256']+'`\n')
            subprocess.run(['gh','release','create',tag,str(path),'--repo',repo,'--target',target,
                            '--title',row['release']+' 历史归档','--notes-file',str(note),'--prerelease','--latest=false'],check=True)
        else:
            assets=json.loads(view.stdout)['assets']
            if not any(a.get('digest')=='sha256:'+row['sha256'] and a['size']==row['bytes'] for a in assets):
                subprocess.run(['gh','release','upload',tag,str(path),'--repo',repo],check=True)
        # GitHub normalizes non-ASCII filenames. Bind the actual asset by digest
        # and byte length, then download that name rather than guessing it.
        assets=json.loads(subprocess.check_output(['gh','release','view',tag,'--repo',repo,'--json','assets']))['assets']
        matches=[a for a in assets if a.get('digest')=='sha256:'+row['sha256'] and a['size']==row['bytes']]
        if len(matches)!=1: raise RuntimeError('Remote archive asset is missing or ambiguous')
        remote_name=matches[0]['name']
        # Do not trust metadata alone: download the stored bytes and hash them.
        with tempfile.TemporaryDirectory(prefix='campus-cloud-verify-') as temporary:
            subprocess.run(['gh','release','download',tag,'--repo',repo,'--pattern',remote_name,'--dir',temporary],check=True)
            if digest(Path(temporary)/remote_name)!=row['sha256']: raise RuntimeError('Remote download hash mismatch')
        row.update(remote_verified=True,repo=repo,tag=tag,
                   url='https://github.com/'+repo+'/releases/tag/'+tag,asset=remote_name)
        save(plan,body); print('remote verified '+row['release'],flush=True)


def cleanup(plan, new_release, secrets):
    body=json.loads(plan.read_text())
    checks=json.loads((new_release/'验证结果.json').read_text())
    if checks.get('passed') is not True: raise RuntimeError('Latest release has not passed')
    if not (new_release/'课间桌宠.app').is_dir(): raise RuntimeError('Latest App missing')
    # Preflight every directory before any destructive step; bind to exact tree.
    for row in body['records']:
        root=Path(row['local_root'])
        if row.get('local_removed'): continue
        if not row.get('remote_verified') or root.parent.resolve()!=DEFAULT_HISTORY.resolve():
            raise RuntimeError('Unverified/unexpected local archive')
        if root.resolve()==new_release.resolve() or root.is_symlink(): raise RuntimeError('Refusing latest or linked release')
        if tree_inventory(root,secrets)!=row['tree']: raise RuntimeError('Local archive changed since upload')
    for row in body['records']:
        if row.get('local_removed'): continue
        shutil.rmtree(row['local_root']); row['local_removed']=True; save(plan,body)
        print('removed verified historical copy '+row['release'],flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','upload','cleanup'])
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--staging',type=Path,default=Path('/private/tmp/campus-cloud-releases'))
    p.add_argument('--history',type=Path,default=DEFAULT_HISTORY)
    p.add_argument('--repo',default='ZeeyeC/scut-student-private-assistant')
    p.add_argument('--target',default='574117314878b982430e93e570806cfca972603d')
    p.add_argument('--new-release',type=Path)
    a=p.parse_args();secrets=set()
    for root in [PROJECT,Path('/Users/czy/ProjectManagement/agentbuild'),Path.home()/'Library/Application Support/CampusCompanion']:
        secrets.update(release.private_values(root))
    if a.action=='prepare': prepare(a.history,a.staging,a.plan,secrets)
    elif a.action=='upload': upload(a.plan,a.repo,a.target)
    else:
        if a.new_release is None:p.error('cleanup requires --new-release')
        cleanup(a.plan,a.new_release,secrets)

if __name__=='__main__':main()
