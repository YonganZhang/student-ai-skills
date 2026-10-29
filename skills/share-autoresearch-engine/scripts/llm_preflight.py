#!/usr/bin/env python3
"""Validate LLM sidecar contracts before a native CLI; never trains or authorizes."""
import argparse,hashlib,json
from pathlib import Path

SPLITS={'fit','select','evaluate','test','calibration'}
def read(path):return json.loads(Path(path).read_text())
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def check(contract_path):
 p=Path(contract_path).resolve();c=read(p);root=p.parent
 def bind(ref):
  q=(root/ref['path']).resolve()
  if digest(q)!=ref['sha256']:raise ValueError('Bound file changed: '+q.name)
  return q
 if c.get('status')!='READY_FOR_PREFLIGHT':raise ValueError('Contract not ready')
 if not c.get('authorization_reference','').strip() or c['authorization_reference'].startswith('SET_'):raise ValueError('Missing real authorization reference')
 b=c.get('budget',{})
 if not all(type(b.get(k)) is int and b[k]>0 for k in ['max_steps','max_wall_seconds','max_gpus']):raise ValueError('Explicit positive budget required')
 cfg=read(bind(c['native_config']));m=read(bind(c['data_manifest']));q=read(bind(c['quantization_decision']))
 for key in ['cached_dataset','eval_dataset','test_dataset','calibration_dataset','quant_dataset']:
  if cfg.get(key):raise ValueError('Unbound data override: '+key)
 records=m.get('records',[])
 if not records:raise ValueError('No data identity records')
 ids=set();clusters={};per_split={s:set() for s in SPLITS}
 for r in records:
  if set(r)-{'sample_id','source_cluster_id','split'}:raise ValueError('Identity manifest must not contain answers')
  sid=r['sample_id'];cluster=r['source_cluster_id'];split=r['split']
  if not sid or sid in ids or not cluster or split not in SPLITS:raise ValueError('Invalid/duplicate data identity')
  ids.add(sid);per_split[split].add(sid)
  if cluster in clusters and clusters[cluster]!=split:raise ValueError('Source cluster crosses split')
  clusters[cluster]=split
 for field in ['training_quantization','deployment_quantization']:
  d=q[field]
  if d.get('decision') not in ['use','skip','defer'] or not d.get('reason','').strip() or d['reason'].startswith('SET_'):raise ValueError('Unresolved quantization decision')
  if d['decision']=='use' and not d.get('method'):raise ValueError('Quantization method missing')
 dep=q['deployment_quantization']
 if dep.get('calibration_required'):
  if dep.get('calibration_split') not in ['fit','select','calibration']:raise ValueError('Calibration cannot consume evaluate/test')
  declared=set(m.get('calibration_ids',[]))
  if not declared or not declared <= per_split[dep['calibration_split']]:raise ValueError('Calibration identities not bound to allowed split')
 for ref in m.get('input_files',[]):
  if ref['split'] not in ['fit','select','calibration']:raise ValueError('Only permitted training/select/calibration inputs may be opened')
  if ref.get('license_status')!='accepted' or ref.get('quality_status')!='accepted':raise ValueError('Missing data acceptance evidence')
  bind(ref)
 if c.get('operation')=='sft':
  if not per_split['fit'] or not per_split['select']:raise ValueError('SFT needs distinct fit/select identities')
  if cfg.get('split_dataset_ratio')!=0:raise ValueError('Implicit random split disabled')
  files={s:set() for s in ['fit','select','calibration']}
  for ref in m['input_files']:files[ref['split']].add(str((root/ref['path']).resolve()))
  if files['fit'] & files['select']:raise ValueError('Input file shared by fit/select')
  hashes={s:{r['sha256'] for r in m['input_files'] if r['split']==s} for s in ['fit','select']}
  if hashes['fit'] & hashes['select']:raise ValueError('Exact input content duplicated across fit/select')
  for key,split in [('dataset','fit'),('val_dataset','select')]:
   values=cfg.get(key,[]);values=[values] if isinstance(values,str) else values
   if not values or {str((root/v).resolve()) for v in values}!=files[split]:raise ValueError('Native data paths disagree with accepted manifest')
  if not 0<cfg.get('max_steps',0)<=b['max_steps']:raise ValueError('Training steps exceed scope')
  train=q['training_quantization']
  if train['decision']=='use' and not cfg.get('quant_method'):raise ValueError('Selected training quantization missing from config')
  if cfg.get('quant_method') and train['decision']!='use':raise ValueError('Quantized training contradicts decision')
  if cfg.get('quant_method') and train.get('method')!=cfg['quant_method']:raise ValueError('Training quantization method mismatch')
 elif c.get('operation')=='quantize':
  if dep['decision']!='use' or dep.get('method')!=cfg.get('quant_method'):raise ValueError('Deployment quantization not selected')
  if str(cfg.get('model'))!=str((root/c['source_checkpoint']).resolve()):raise ValueError('Quantization source checkpoint mismatch')
  if not c.get('source_identity_reference'):raise ValueError('Missing selected/merged source provenance')
  source=Path(cfg['model']).resolve();identity=read(bind(c['source_identity_reference']))
  declared={r['path'] for r in identity.get('files',[])}
  actual={str(p.relative_to(source)) for p in source.rglob('*') if p.is_file()}
  if not declared or declared!=actual:raise ValueError('Source checkpoint file inventory changed')
  for item in identity['files']:
   rel=Path(item['path'])
   if rel.is_absolute() or '..' in rel.parts or digest(source/rel)!=item['sha256']:raise ValueError('Source checkpoint changed')
  if cfg.get('adapters'):raise ValueError('Quantize an explicitly selected/merged source, not an unbound adapter')
  if cfg['quant_method']=='bnb':
   if dep.get('calibration_required') or cfg.get('dataset') or cfg.get('val_dataset'):raise ValueError('BNB weight-only export has no calibration input')
  else:
   if not dep.get('calibration_required'):raise ValueError('Unreviewed non-BNB quantization contract')
   calibration_files={str((root/r['path']).resolve()) for r in m['input_files'] if r['split']==dep['calibration_split']}
   native_files=cfg.get('dataset',[]);native_files=[native_files] if isinstance(native_files,str) else native_files
   if not native_files or {str((root/v).resolve()) for v in native_files}!=calibration_files:raise ValueError('Native calibration paths disagree with manifest')
 else:raise ValueError('Unsupported native-operation contract; extend only after review')
 return {'status':'PREFLIGHT_PASS_NOT_EXECUTION_AUTHORIZATION','operation':c['operation'],'records':len(records),'split_counts':{s:len(v) for s,v in per_split.items()},'test_answers_read':False,'limitation':'Checks supplied metadata/hashes, not real permission, semantic duplication, data correctness or GPU runtime.'}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('contract');a=p.parse_args()
 try:print(json.dumps(check(a.contract),ensure_ascii=False))
 except (ValueError,KeyError,TypeError,OSError) as exc:p.exit(2,str(exc)+'\n')
if __name__=='__main__':main()
