"""Local inventory and approved, guarded file operations. Python >=3.11; stdlib only."""
from __future__ import annotations
import argparse
import hashlib
import heapq
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import tomllib

VERSION = 2
SKIP = {'.git', '.venv', 'node_modules', '__pycache__', 'sessions', 'archived_sessions',
        'memories', 'memories_v2', 'memories_extensions', 'memories_extensions',
        'plugins', 'runtimes', 'skills', 'browser', '.sandbox', '.sandbox-secrets'}
SENSITIVE = {'auth.json', 'cap_sid', 'credentials.json', 'secrets.json', '.env', '火山key.txt'}
DEPENDENCIES = {'.git', '.venv', 'node_modules', 'backups', '恢复资料'}
ENTRY_DOCS = {'AGENTS.md','项目状态.md','项目规则.md',
              '项目状态.md','操作规则.md','学习状态.md','学习进度.md','学习约定.md','工作流与方法.md'}

class GuardError(ValueError):
    pass

def require(ok, message):
    if not ok:
        raise GuardError(message)

def linked(p):
    return p.is_symlink() or bool(getattr(p, 'is_junction', lambda:False)()) or bool(
        p.exists() and getattr(p.stat(follow_symlinks=False),'st_file_attributes',0) & 0x400)

def no_links(p):
    for part in (p,*p.parents):
        require(not linked(part), 'Linked path refused: '+str(part))

def boundary(value):
    p = Path(value)
    require(p.is_absolute(), 'Root must be absolute')
    no_links(p)
    p = p.resolve()
    require(p.is_dir() and p.parent != p, 'Root must be an existing non-drive directory')
    return p

def within(root, relative):
    require(isinstance(relative,str) and relative.strip(), 'Empty relative path')
    p = Path(relative)
    require(not p.is_absolute() and not p.drive and '..' not in p.parts and ':' not in relative,
            'Absolute, parent traversal or alternate stream refused')
    target = root/p
    no_links(target)
    target = target.resolve()
    require(target != root and target.is_relative_to(root), 'Path must be below approved root')
    return target

def codex_scope(root, mode):
    require(mode in {'auto','project','codex'}, 'Invalid mode')
    actual = Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex').resolve()
    # An explicit project mode cannot bypass an actual Codex data scope.
    return mode == 'codex' or root.is_relative_to(actual) or '.codex' in [x.lower() for x in root.parts]

def codex_relative(root,p):
    actual=Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex').resolve()
    if p.is_relative_to(actual): return p.relative_to(actual)
    for ancestor in (root,*root.parents):
        if ancestor.name.lower()=='.codex': return p.relative_to(ancestor)
    return p.relative_to(root)

def sensitive(p):
    name = p.name.lower()
    return (name in SENSITIVE or name.endswith(('.key','.pem','.p12','.pfx','.sqlite','.db','-wal','-shm','.lock'))
            or '.sqlite' in name or name.startswith('.env.') and not name.endswith('.example')
            or bool(re.search(r'(^|[-_.])(api[-_]?)?(key|token|secret)([-_.]|$)',name))
            or any(x.lower() in {'credentials','secrets','.sandbox-secrets'} for x in p.parts))

def active_paths(root,mode='auto'):
    """Extract only file locations. Never return config/env/credential values."""
    root=Path(root)
    if codex_scope(root,mode):
        actual=Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex').resolve()
        anchor=actual if root.is_relative_to(actual) else next(
            (p for p in (root,*root.parents) if p.name.lower()=='.codex'),root)
        config=anchor/'config.toml'
    else:
        config=root/'.codex/config.toml'
    if not config.exists():
        return []
    no_links(config)
    data = tomllib.loads(config.read_text(encoding='utf-8-sig'))
    result = set()
    for item in data.get('mcp_servers',{}).values():
        if not isinstance(item,dict): continue
        for value in [item.get('command'),item.get('cwd'),*item.get('args',[])]:
            if not isinstance(value,str): continue
            value = value.split('=',1)[-1] if value.startswith('--') and '=' in value else value
            p = Path(value)
            if p.is_absolute() and p.exists():
                # Preserve sibling dependencies of configured scripts/interpreters.
                candidates=[p if p.is_dir() else p.parent]
                if p.parent.name.lower() in {'scripts','bin'}: candidates.append(p.parent.parent)
                result.update(str(x) for x in candidates if x.is_relative_to(root) or root.is_relative_to(x))
    return sorted(result)

def leaves(p):
    if p.is_file():
        yield p; return
    require(p.is_dir(), 'Missing or special source: '+str(p))
    for base,dirs,files in os.walk(p,followlinks=False):
        for name in dirs+files:
            item = Path(base)/name
            require(not linked(item), 'Linked descendant refused: '+str(item))
        for name in files:
            yield Path(base)/name

def webpack_cache(root,p,op):
    if not op or op.get('cache_kind') != 'webpack' or op.get('method') != 'filewise': return False
    parts = [x.lower() for x in p.relative_to(root).parts]
    return any(parts[i:i+3] == ['node_modules','.cache','webpack'] for i in range(len(parts)-2))

def protected(root,p,action,mode,active,op=None):
    rel = p.relative_to(root)
    require(not sensitive(p), 'Sensitive/state file refused: '+str(rel))
    require('.codex' not in [x.lower() for x in rel.parts], 'Nested Codex configuration refused')
    require(not any(p.is_relative_to(Path(x)) or Path(x).is_relative_to(p) for x in active),
            'Currently configured runtime path refused: '+str(rel))
    if codex_scope(root,mode):
        require(action == 'delete' and codex_relative(root,p).parts[0].lower() in {'tmp','.tmp','cache'},
                'Codex data layout protected; only reviewed tmp/cache deletion supported')
        relative=codex_relative(root,p)
        roles=SKIP|{'attachments','generated_images','visualizations','outputs','backups','sqlite'}
        require(not any(x.lower() in roles for x in relative.parts),'Managed Codex material refused')
        require(p.name.lower() not in {'config.toml','agents.md','runtime-config.json','session_index.jsonl',
                '.codex-global-state.json','.codex-global-state.json.bak'} and not
                p.name.lower().startswith('.codex-global-state.json.tmp'), 'Codex state/config refused')
        require(p.suffix.lower() not in {'.exe','.dll','.pyd','.so','.dylib'},'Executable runtime material refused')
    elif action != 'move':
        require(not any(x.lower() in DEPENDENCIES for x in rel.parts) or
                action == 'delete' and webpack_cache(root,p,op), 'Dependency/recovery material refused')
    else:
        require(p.name.lower() not in DEPENDENCIES, 'Direct dependency/recovery relocation refused')

def guard_tree(root,p,action,mode,active,op=None):
    protected(root,p,action,mode,active,op)
    for f in leaves(p):
        require(stat.S_ISREG(f.stat().st_mode) and f.stat().st_nlink <= 1, 'Special or hard-linked file refused')
        protected(root,f,action,mode,active,op)
        if webpack_cache(root,p,op):
            require(bool(re.fullmatch(r'(?:\d+|index)\.pack(?:\.old|\.gz)?',f.name)),
                    'Unrecognized file inside webpack cache: '+str(f))

def sha(p):
    with p.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def snapshot(p):
    data = {}
    for f in leaves(p):
        s = f.stat()
        data['.' if f == p else f.relative_to(p).as_posix()] = {
            'sha256':sha(f),'bytes':s.st_size,'mtime_ns':s.st_mtime_ns}
    dirs = sorted(x.relative_to(p).as_posix() for x in p.rglob('*') if x.is_dir()) if p.is_dir() else []
    return {'type':'directory' if p.is_dir() else 'file','files':data,'directories':dirs}

def contents_equal(a,b):
    def compact(s):
        return {'type':s['type'],'directories':s['directories'],
                'files':{k:(v['sha256'],v['bytes']) for k,v in s['files'].items()}}
    return compact(a) == compact(b)

def remaining_matches(current,original):
    return (current['type']==original['type'] and set(current['directories'])<=set(original['directories'])
            and set(current['files'])<=set(original['files']) and all(
                (v['sha256'],v['bytes'])==(original['files'][k]['sha256'],original['files'][k]['bytes'])
                for k,v in current['files'].items()))

def encoded(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')

def save(p,obj):
    atomic_text(p,(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))

def load(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def audit(root,mode='auto',depth=2,limit=40):
    root = boundary(root)
    codex = codex_scope(root,mode)
    require(0 <= depth <= 8 and 1 <= limit <= 1000,'Invalid audit depth/limit')
    entries = []; omitted = []; count = 0; size = 0; metrics = {}; largest = []
    directories = {}; candidates = {}; details_omitted = set(); hardlinks = 0
    pending = [(root,0)]
    while pending:
        parent,level = pending.pop()
        try: children = sorted(parent.iterdir(),key=lambda x:x.name.lower())
        except OSError as exc:
            omitted.append({'path':parent.relative_to(root).as_posix(),'reason':type(exc).__name__}); continue
        for p in children:
            rel = p.relative_to(root).as_posix()
            try:
                if linked(p):
                    omitted.append({'path':rel,'reason':'linked'}); continue
                if p.is_dir():
                    if codex and p.name in SKIP:
                        omitted.append({'path':rel,'reason':'managed/dependency'}); continue
                    if level >= depth or any(x in SKIP for x in p.relative_to(root).parts): details_omitted.add(rel)
                    pending.append((p,level+1)); continue
                st = p.stat(follow_symlinks=False)
                if not stat.S_ISREG(st.st_mode):
                    omitted.append({'path':rel,'reason':'special'}); continue
                n = st.st_size; count += 1; size += n; hardlinks += st.st_nlink > 1
                parts = p.relative_to(root).parts
                for i in range(1,len(parts)):
                    name = '/'.join(parts[:i]); row = directories.setdefault(name,{'path':name,'files':0,'bytes':0})
                    row['files'] += 1; row['bytes'] += n
                # Hints only: no age/extension/size rule makes a deletion decision.
                for i,name in enumerate(parts[:-1]):
                    role = ('webpack_cache' if name == 'webpack' and i >= 2 and parts[i-2:i] == ('node_modules','.cache') else
                            'generated_directory_review' if name.lower() in {'frames','render_frames','渲染','bundle','tmp','.tmp','.cache','预览','历史预览'} else None)
                    if role:
                        key='/'.join(parts[:i+1]); row=candidates.setdefault(key,{'path':key,'hint':role,'files':0,'bytes':0,'review_required':True})
                        row['files'] += 1; row['bytes'] += n
                heapq.heappush(largest,(n,rel))
                if len(largest)>limit: heapq.heappop(largest)
                visible = level <= depth and not any(x in SKIP for x in parts)
                if visible and len(entries)<limit: entries.append({'path':rel,'bytes':n,'protected_name':sensitive(p)})
                if visible and not codex and p.name in ENTRY_DOCS and not sensitive(p):
                    try: metrics[rel] = {'characters':len(p.read_text(encoding='utf-8-sig')),'bytes':n}
                    except (OSError,UnicodeError): metrics[rel] = {'bytes':n,'text_metric':'unavailable'}
            except OSError as exc: omitted.append({'path':rel,'reason':type(exc).__name__})
    ranked = sorted(directories.values(),key=lambda x:(-x['bytes'],x['path']))
    return {'root':str(root),'mode':'codex' if codex else 'project','read_only':True,
            'counted_files':count,'counted_logical_bytes':size,'complete':not omitted,
            'entries':entries,'entries_truncated':count>len(entries),'omitted':omitted[:limit],'omitted_count':len(omitted),
            'detail_depth':depth,'detail_omitted_count':len(details_omitted),
            'top_level_bytes':[r for r in ranked if '/' not in r['path']],
            'largest_directories':ranked[:10],
            'largest_files':[{'path':p,'bytes':n} for n,p in sorted(largest,reverse=True)],
            'generated_candidates':sorted(candidates.values(),key=lambda x:(-x['bytes'],x['path']))[:10],
            'hardlinked_files':hardlinks,'physical_free_space_delta_measured':False,
            'size_scope':'recursive metadata only; directory rows overlap; links excluded; Codex managed branches excluded',
            'entry_text_metrics':metrics,'configured_runtime_paths':active_paths(root,mode)}

def prepare(spec,version=VERSION):
    root = boundary(spec['root']); mode = spec.get('mode','auto'); active = active_paths(root,mode)
    preserve=spec.get('preserve',[])
    require(isinstance(preserve,list),'Preserve must be a list of root-relative paths')
    active+= [str(within(root,p)) for p in preserve]
    require(bool(spec.get('purpose')),'Purpose required')
    ops = spec.get('operations'); require(isinstance(ops,list) and ops,'Operations required')
    result = []; paths = []; keepers = []
    for raw in ops:
        op = dict(raw); action = op['action']; require(action in {'move','edit','delete'},'Unknown action')
        p = within(root,op['source']); require(p.exists(),'Missing source')
        guard_tree(root,p,action,mode,active,op); paths.append(p)
        op['source'] = p.relative_to(root).as_posix(); op['before'] = snapshot(p)
        if action == 'move':
            dest = within(root,op['target']); protected(root,dest,'move',mode,active)
            require(not dest.exists(),'Occupied target'); paths.append(dest)
            op['target'] = dest.relative_to(root).as_posix()
        if action == 'edit':
            require(p.is_file() and isinstance(op.get('text'),str),'UTF-8 file edit required')
            p.read_text(encoding='utf-8-sig')
        if action == 'delete':
            require(op.get('category') in {'regenerable_cache','obsolete_temporary','redundant_copy'},'Deletion category required')
            require(all(isinstance(op.get(k),str) and op[k].strip() for k in ('reason','evidence','regeneration')),
                    'Deletion reason, evidence and recovery/regeneration required')
            require(op.get('method','staged') in {'staged','filewise'},'Unknown deletion method')
            if version >= 2:
                require(op.get('lifecycle') in {'temporary','ended_test'},
                        'Only reviewed temporary material or ended tests may be deleted; preserve active/formal/recovery/unknown')
            if op.get('lifecycle') == 'ended_test':
                require(isinstance(op.get('retained'),list) and op['retained'] and isinstance(op.get('policy'),str),
                        'Ended test needs retained results and an existing project policy')
                policy=within(root,op['policy']); require(policy.is_file(),'Missing project policy')
                guard_tree(root,policy,'move',mode,active); policy.read_text(encoding='utf-8-sig')
                op['policy_before']=snapshot(policy); keepers.append(policy)
                op['retained_before']={}
                for name in op['retained']:
                    kept=within(root,name); require(kept.exists(),'Missing retained result')
                    guard_tree(root,kept,'move',mode,active)
                    op['retained_before'][name]=snapshot(kept); keepers.append(kept)
            if 'cache_kind' in op:
                require(op['cache_kind']=='webpack' and not codex_scope(root,mode) and webpack_cache(root,p,op),
                        'Only explicit project-local webpack data cache supported')
            if op['category'] == 'redundant_copy':
                keeper = within(root,op['keeper']); require(keeper.exists(),'Missing keeper')
                guard_tree(root,keeper,'move',mode,active)
                require(contents_equal(snapshot(p),snapshot(keeper)),'Copy differs from keeper')
                keepers.append(keeper); op['keeper_before'] = snapshot(keeper)
        result.append(op)
    for i,a in enumerate(paths):
        for b in paths[i+1:]:
            require(not (a.is_relative_to(b) or b.is_relative_to(a)), 'Overlapping operations refused')
    for p in keepers:
        require(not any(p.is_relative_to(x) or x.is_relative_to(p) for x in paths),'Keeper overlaps operation')
    if any(op.get('method')=='filewise' for op in result):
        require(all(op['action']=='delete' and op.get('method')=='filewise' for op in result),
                'Filewise deletion must be a separate all-deletion plan')
    result_plan={'version':version,'root':str(root),'mode':mode,'purpose':spec['purpose'],'operations':result}
    if preserve: result_plan['preserve']=preserve
    return result_plan

def preflight(plan):
    require(plan.get('version') in {1,VERSION},'Unknown plan version')
    raw = {k:v for k,v in plan.items() if k != 'operations'}
    raw['operations'] = [{k:v for k,v in op.items() if k not in {'before','keeper_before','retained_before','policy_before'}} for op in plan['operations']]
    current = prepare(raw,plan['version'])
    require(current == plan,'Plan sources, targets or keeper changed; review again')
    return boundary(plan['root'])

def atomic_text(path,data):
    fd,name = tempfile.mkstemp(prefix='.file-organization-',dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd,'wb') as f: f.write(data)
        if path.exists(): shutil.copymode(path,temporary)
        os.replace(temporary,path)
    finally:
        if temporary.exists(): temporary.unlink()

def local_links(text):
    text = re.sub(r'(?s)```.*?```','',text)
    return {x for x in re.findall(r'\]\(([^)]+)\)',text)
            if not x.startswith(('http:','https:','mailto:','codex:','#'))}

def retained_evidence(root,item):
    for name,before in item.get('retained_before',{}).items():
        kept=within(root,name); require(kept.exists() and contents_equal(snapshot(kept),before),'Retained result changed: '+name)
    if 'policy_before' in item:
        policy=within(root,item['policy'])
        require(policy.exists() and contents_equal(snapshot(policy),item['policy_before']),'Project retention policy changed')

def verify(receipt_path):
    receipt = load(receipt_path); root = boundary(receipt['root']); journal = Path(receipt_path).resolve().parent
    no_links(Path(receipt_path)); require(journal != root and journal.is_relative_to(root),'Journal outside root')
    require(receipt.get('version') in {1,VERSION},'Unknown receipt version')
    failures = []
    for item in receipt['actions']:
        p = within(root,item['target'] if item['action'] == 'move' else item['source'])
        protected(root,p,item['action'],receipt.get('mode','auto'),active_paths(root,receipt.get('mode','auto')),item)
        retained_evidence(root,item)
        if item['action'] == 'delete':
            if p.exists(): failures.append(item['source'])
        elif not p.exists() or not contents_equal(snapshot(p),item['after']):
            failures.append(str(p))
        elif item['action'] == 'edit' and p.suffix.lower() == '.md':
            require(re.fullmatch(r'backup/\d+',item['backup']),'Invalid backup path')
            before = (journal/item['backup']).read_text(encoding='utf-8-sig')
            for link in local_links(p.read_text(encoding='utf-8-sig'))-local_links(before):
                target = link.split('#',1)[0].strip('<>')
                if target and not (p.parent/target).exists(): failures.append('New broken link: '+link)
    return {'passed':not failures,'failures':failures,'scope':'operation contents and new local Markdown links'}

def undo(receipt_path):
    receipt = load(receipt_path); root = boundary(receipt['root']); journal = Path(receipt_path).parent
    no_links(journal); require(journal.is_relative_to(root) and journal != root,'Journal outside root')
    require(not receipt.get('filewise'),'Filewise deletion is irreversible; resume the same receipt or regenerate material')
    restored=[]; unavailable=[]; conflicts=[]
    for item in reversed(receipt['actions']):
        try:
            source = within(root,item['source'])
            protected(root,source,item['action'],receipt.get('mode','auto'),active_paths(root,receipt.get('mode','auto')))
            if item['action'] == 'move':
                dest = within(root,item['target'])
                if source.exists() and not dest.exists() and contents_equal(snapshot(source),item['before']): continue
                require(not source.exists() and contents_equal(snapshot(dest),item['after']),'Changed rollback target')
                source.parent.mkdir(parents=True,exist_ok=True); os.replace(dest,source)
            elif item['action'] == 'edit':
                if contents_equal(snapshot(source),item['before']): continue
                require(re.fullmatch(r'backup/\d+',item['backup']),'Invalid backup path')
                no_links(journal/item['backup'])
                require(contents_equal(snapshot(source),item['after']),'Independent edit; rollback refused')
                atomic_text(source,(journal/item['backup']).read_bytes())
            else:
                require(re.fullmatch(r'trash/\d+',item['staged']),'Invalid staging path')
                staged = within(root,str((journal/item['staged']).relative_to(root)))
                if not staged.exists():
                    if source.exists() and contents_equal(snapshot(source),item['before']): continue
                    unavailable.append(item['source']); continue
                require(not source.exists() and contents_equal(snapshot(staged),item['before']),'Changed deletion staging')
                source.parent.mkdir(parents=True,exist_ok=True); os.replace(staged,source)
            restored.append(item['source'])
        except (OSError,ValueError) as e: conflicts.append(str(e))
    receipt['rollback']={'restored':restored,'cache_requires_regeneration':unavailable,'conflicts':conflicts}
    receipt['status']='rolled_back' if not conflicts and not unavailable else 'partial_rollback'
    save(Path(receipt_path),receipt)
    return receipt['rollback']

def finalize(receipt_path):
    receipt_path=Path(receipt_path); receipt=load(receipt_path); root=boundary(receipt['root'])
    journal=receipt_path.parent; no_links(journal)
    require(journal != root and journal.is_relative_to(root),'Journal outside root')
    require(receipt['status'] in {'verified','cleanup_pending'},'Receipt not ready for cache finalization')
    require(verify(receipt_path)['passed'],'Verify contents before finalization')
    released=0
    for item in receipt['actions']:
        if item['action']!='delete': continue
        staged=within(root,str((journal/item['staged']).relative_to(root)))
        require(staged.is_relative_to(journal/'trash'),'Staging outside transaction trash')
        if staged.exists():
            guard_tree(root,staged,'delete',receipt.get('mode','auto'),active_paths(root,receipt.get('mode','auto')))
            require(remaining_matches(snapshot(staged),item['before']),'Staging contains changed or additional content')
            if staged.is_dir(): shutil.rmtree(staged)
            else: staged.unlink()
        released+=sum(v['bytes'] for v in item['before']['files'].values())
    receipt.update(status='completed',deleted_logical_bytes=released,
                   physical_free_space_delta_measured=False)
    save(receipt_path,receipt)
    return {'status':'completed','deleted_logical_bytes':released,'receipt':str(receipt_path)}

def resume(receipt_path):
    """Continue the same irreversible filewise plan; never move a locked directory."""
    receipt_path=Path(receipt_path); no_links(receipt_path)
    receipt=load(receipt_path); root=boundary(receipt['root']); journal=receipt_path.parent.resolve()
    require(journal != root and journal.is_relative_to(root),'Journal outside root'); no_links(journal)
    require(receipt.get('version')==VERSION and receipt.get('filewise') and
            receipt['status'] in {'running','deletion_pending','completed'},'Not a resumable filewise receipt')
    if receipt['status']=='completed':
        return {k:receipt[k] for k in ('status','deleted_files','deleted_logical_bytes')}
    lock=journal/'.execution.lock'; no_links(lock)
    with lock.open('x'): pass
    progress=journal/'deletions.jsonl'; no_links(progress)
    events={}
    try:
        if progress.exists():
            for line in progress.read_text(encoding='utf-8').splitlines():
                event=json.loads(line); require(event['state'] in {'staging','staged','deleted'},'Unknown deletion progress')
                require(isinstance(event['operation'],int) and 0 <= event['operation'] < len(receipt['actions']) and
                        event['file'] in receipt['actions'][event['operation']]['before']['files'],'Invalid deletion progress entry')
                events[(event['operation'],event['file'])]=event['state']
        def record(index,key,state):
            with progress.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps({'operation':index,'file':key,'state':state},ensure_ascii=False)+'\n')
                stream.flush(); os.fsync(stream.fileno())
            events[(index,key)]=state
        active=active_paths(root,receipt['mode'])+[str(within(root,p)) for p in receipt.get('preserve',[])]
        for index,item in enumerate(receipt['actions']):
            require(item['action']=='delete' and item.get('method')=='filewise' and
                    item.get('lifecycle') in {'temporary','ended_test'},'Invalid filewise operation')
            source=within(root,item['source'])
            require(not (source.is_relative_to(journal) or journal.is_relative_to(source)),'Journal overlaps deletion')
            protected(root,source,'delete',receipt['mode'],active,item); retained_evidence(root,item)
            keys=sorted(item['before']['files'])
            # Reject added/changed/recreated content before this operation resumes.
            expected={k:v for k,v in item['before']['files'].items() if (index,k) not in events or
                      events[(index,k)]=='staging' and (source if k=='.' else source/k).exists()}
            if source.exists():
                guard_tree(root,source,'delete',receipt['mode'],active,item)
                current=snapshot(source)
                require(current['files']==expected,'Remaining deletion source changed; review required')
            else: require(not expected,'Unjournalled missing deletion source')
            for number,key in enumerate(keys):
                original=source if key=='.' else within(root,(source/key).relative_to(root).as_posix())
                staged=within(root,(journal/'trash'/f'{index}-{number}').relative_to(root).as_posix())
                before=item['before']['files'][key]; state=events.get((index,key))
                if state=='deleted':
                    require(not original.exists() and not staged.exists(),'Deleted file recreated; review required'); continue
                if state is None or state=='staging' and original.exists():
                    guard_tree(root,original,'delete',receipt['mode'],active,item)
                    require(snapshot(original)['files']['.']==before,'Source file changed before deletion')
                    require(not staged.exists(),'Occupied filewise staging path')
                    # Stage individual files on the same volume; no directory rename or copy.
                    record(index,key,'staging')
                    os.replace(original,staged)
                    record(index,key,'staged')
                else:
                    require(not original.exists(),'Staged source recreated; review required')
                    if state=='staging':
                        require(staged.exists(),'Unconfirmed staging outcome; review required')
                        record(index,key,'staged')
                if staged.exists():
                    guard_tree(root,staged,'delete',receipt['mode'],active)
                    require(snapshot(staged)['files']['.']==before,'Staged file changed; review required')
                    staged.unlink()
                # A staged event plus absence reconciles interruption after unlink.
                record(index,key,'deleted')
            if item['before']['type']=='directory':
                for name in sorted(item['before']['directories'],key=lambda s:len(Path(s).parts),reverse=True):
                    directory=within(root,(source/name).relative_to(root).as_posix())
                    if directory.exists(): directory.rmdir()
                if source.exists(): source.rmdir()
        checked=verify(receipt_path); require(checked['passed'],str(checked['failures']))
        receipt.update(status='completed',verification=checked); receipt.pop('error',None)
    except Exception as exc:
        receipt.update(status='deletion_pending',error=str(exc))
        raise
    finally:
        deleted=[(i,k) for (i,k),state in events.items() if state=='deleted']
        receipt.update(deleted_files=len(deleted),
            deleted_logical_bytes=sum(receipt['actions'][i]['before']['files'][k]['bytes'] for i,k in deleted),
            physical_free_space_delta_measured=False)
        try: save(receipt_path,receipt)
        finally: lock.unlink()
    return {k:receipt[k] for k in ('status','deleted_files','deleted_logical_bytes')}

def apply(plan,approved,journal):
    require(hashlib.sha256(encoded(plan)).hexdigest()==approved,'Approved plan digest mismatch')
    root=preflight(plan); journal=Path(journal)
    require(journal.is_absolute(),'Journal must be absolute'); no_links(journal)
    journal=journal.resolve()
    require(journal != root and journal.is_relative_to(root) and not journal.exists(),'Fresh root-contained journal required')
    if codex_scope(root,plan['mode']):
        require(codex_relative(root,journal).parts[0].lower() in {'tmp','.tmp'},'Codex journal must be inside tmp')
    for op in plan['operations']:
        for key in ('source','target','keeper'):
            if key not in op: continue
            p=within(root,op[key])
            require(not (p.is_relative_to(journal) or journal.is_relative_to(p)),'Journal overlaps operation')
    journal.mkdir(parents=True); (journal/'backup').mkdir(); (journal/'trash').mkdir()
    receipt={'version':plan['version'],'root':str(root),'mode':plan['mode'],'plan_sha256':approved,'status':'running','actions':[]}
    receipt_path=journal/'receipt.json'; save(receipt_path,receipt)
    if plan['operations'][0].get('method')=='filewise':
        receipt.update(filewise=True,actions=plan['operations'],preserve=plan.get('preserve',[]))
        save(receipt_path,receipt)
        return resume(receipt_path)
    try:
        for i,op in enumerate(plan['operations']):
            source=within(root,op['source'])
            guard_tree(root,source,op['action'],plan['mode'],active_paths(root,plan['mode'])+
                       [str(within(root,p)) for p in plan.get('preserve',[])],op)
            require(snapshot(source)==op['before'],'Source changed before operation')
            item=dict(op)
            if op['action']=='move':
                dest=within(root,op['target']); require(not dest.exists(),'Target occupied during execution')
                item['after']=op['before']
            elif op['action']=='edit':
                backup=journal/'backup'/str(i); shutil.copy2(source,backup); item['backup']=backup.relative_to(journal).as_posix()
                payload=op['text'].encode('utf-8')
                item['after']={'type':'file','directories':[],'files':{'.':{
                    'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)}}}
            else:
                staged=journal/'trash'/str(i); item['staged']=staged.relative_to(journal).as_posix()
            receipt['actions'].append(item); save(receipt_path,receipt)
            if op['action']=='move':
                dest.parent.mkdir(parents=True,exist_ok=True); os.replace(source,dest)
            elif op['action']=='edit': atomic_text(source,payload)
            else: os.replace(source,staged)
        report=verify(receipt_path); require(report['passed'],str(report['failures']))
        receipt.update(status='verified',verification=report); save(receipt_path,receipt)
    except Exception:
        undo(receipt_path)
        raise
    try:
        return finalize(receipt_path)
    except Exception:
        receipt=load(receipt_path); receipt['status']='cleanup_pending'; save(receipt_path,receipt)
        raise

def write_output(path,data,scan_root=None):
    if path:
        p=Path(path); require(p.is_absolute(),'Output must be absolute'); no_links(p)
        require(not sensitive(p),'Sensitive output name refused')
        if scan_root: require(not p.resolve().is_relative_to(scan_root),'Read-only audit output must be outside scanned root')
        require(not p.exists(),'Output occupied; use a fresh output path')
        save(p,data)
    return data

def main():
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='action',required=True)
    a=sub.add_parser('audit'); a.add_argument('root'); a.add_argument('--mode',default='auto')
    a.add_argument('--depth',type=int,default=2); a.add_argument('--limit',type=int,default=40); a.add_argument('--output')
    p=sub.add_parser('plan'); p.add_argument('spec'); p.add_argument('--output',required=True)
    p=sub.add_parser('apply'); p.add_argument('plan'); p.add_argument('--approved-sha256',required=True); p.add_argument('--journal',required=True)
    for name in ('verify','rollback','finalize','resume'):
        p=sub.add_parser(name); p.add_argument('receipt')
    args=parser.parse_args()
    if args.action=='audit':
        result=write_output(args.output,audit(args.root,args.mode,args.depth,args.limit),boundary(args.root))
    elif args.action=='plan':
        plan=prepare(load(args.spec)); write_output(args.output,plan)
        result={'plan':args.output,'plan_sha256':hashlib.sha256(encoded(plan)).hexdigest(),
                'operations':len(plan['operations']),'source_files_changed':0}
    elif args.action=='apply':
        try: result=apply(load(args.plan),args.approved_sha256,args.journal)
        except (ValueError,OSError) as exc:
            receipt=Path(args.journal)/'receipt.json'
            if receipt.is_file() and not linked(receipt):
                state=load(receipt)
                print(json.dumps({'error':str(exc),'receipt':str(receipt),
                    **{k:state[k] for k in ('status','deleted_files','deleted_logical_bytes') if k in state},
                    'next_action':'resume' if state.get('filewise') else 'finalize' if state.get('status')=='cleanup_pending' else 'review'},ensure_ascii=False),file=sys.stderr)
                return 2
            raise
    elif args.action=='verify': result=verify(args.receipt)
    elif args.action=='rollback': result=undo(args.receipt)
    elif args.action=='resume': result=resume(args.receipt)
    else: result=finalize(args.receipt)
    print(json.dumps(result,ensure_ascii=False))
    if args.action=='verify' and not result['passed']: return 1
    return 0

if __name__=='__main__':
    try: sys.exit(main())
    except (ValueError,OSError,KeyError,UnicodeError) as e:
        print(json.dumps({'error':str(e),'executed_or_retried_automatically':False},ensure_ascii=False),file=sys.stderr)
        sys.exit(2)
