"""Sidecar guard positive/negative tests, no trainers/models or GPU."""
import importlib.util,json,hashlib,tempfile,unittest
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'scripts/llm_preflight.py'
spec=importlib.util.spec_from_file_location('llm_preflight',p);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
class Preflight(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  (self.root/'fit.jsonl').write_text('{"messages": [{"role":"user","content":"A"}]}\n')
  (self.root/'select.jsonl').write_text('{"messages": [{"role":"user","content":"B"}]}\n')
  self.cfg={'dataset':['fit.jsonl'],'val_dataset':['select.jsonl'],'split_dataset_ratio':0,'max_steps':4}
  self.data={'records':[{'sample_id':'a','source_cluster_id':'A','split':'fit'},{'sample_id':'b','source_cluster_id':'B','split':'select'},{'sample_id':'e','source_cluster_id':'E','split':'evaluate'},{'sample_id':'t','source_cluster_id':'T','split':'test'}],'input_files':[dict(path=n+'.jsonl',sha256=hashlib.sha256((self.root/(n+'.jsonl')).read_bytes()).hexdigest(),split=n,license_status='accepted',quality_status='accepted') for n in ['fit','select']]}
  self.quant={'training_quantization':{'decision':'skip','reason':'BF16 memory fits'},'deployment_quantization':{'decision':'defer','reason':'Select production target later','calibration_required':False}}
 def tearDown(self):self.tmp.cleanup()
 def run_case(self):
  c={'status':'READY_FOR_PREFLIGHT','operation':'sft','authorization_reference':'bounded test scope','budget':{'max_steps':4,'max_wall_seconds':60,'max_gpus':1}}
  for key,obj in [('native_config',self.cfg),('data_manifest',self.data),('quantization_decision',self.quant)]:
   b=json.dumps(obj).encode();name=key+'.json';(self.root/name).write_bytes(b);c[key]={'path':name,'sha256':hashlib.sha256(b).hexdigest()}
  path=self.root/'contract.json';path.write_text(json.dumps(c));return mod.check(path)
 def test_valid(self):self.assertEqual(self.run_case()['status'],'PREFLIGHT_PASS_NOT_EXECUTION_AUTHORIZATION')
 def test_cross_split_cluster(self):
  self.data['records'][1]['source_cluster_id']='A'
  with self.assertRaisesRegex(ValueError,'cluster'):self.run_case()
 def test_test_answers_rejected(self):
  self.data['records'][-1]['answer']='forbidden'
  with self.assertRaisesRegex(ValueError,'answers'):self.run_case()
 def test_pending_decision(self):
  self.quant['training_quantization']['decision']='PENDING'
  with self.assertRaisesRegex(ValueError,'Unresolved'):self.run_case()
 def test_calibration_evaluate_rejected(self):
  self.quant['deployment_quantization'].update(calibration_required=True,calibration_split='evaluate');self.data['calibration_ids']=['e']
  with self.assertRaisesRegex(ValueError,'evaluate/test'):self.run_case()
 def test_calibration_select_allowed(self):
  self.quant['deployment_quantization'].update(calibration_required=True,calibration_split='select');self.data['calibration_ids']=['b'];self.run_case()
 def test_step_budget(self):
  self.cfg['max_steps']=5
  with self.assertRaisesRegex(ValueError,'scope'):self.run_case()
 def test_hash_change(self):
  self.data['input_files'][0]['sha256']='bad'
  with self.assertRaisesRegex(ValueError,'changed'):self.run_case()
 def test_unaccepted_data(self):
  self.data['input_files'][0]['quality_status']='pending'
  with self.assertRaisesRegex(ValueError,'acceptance'):self.run_case()
 def test_native_path_mismatch(self):
  self.cfg['dataset']=['select.jsonl']
  with self.assertRaisesRegex(ValueError,'disagree'):self.run_case()
 def test_data_random_split_disabled(self):
  self.cfg['split_dataset_ratio']=0.1
  with self.assertRaisesRegex(ValueError,'random'):self.run_case()
 def test_actual_quantization_matches_decision(self):
  self.cfg['quant_method']='bnb'
  with self.assertRaisesRegex(ValueError,'contradicts'):self.run_case()
 def test_cached_dataset_override_rejected(self):
  self.cfg['cached_dataset']=['hidden.arrow']
  with self.assertRaisesRegex(ValueError,'Unbound data'):self.run_case()
 def test_selected_quantization_must_exist(self):
  self.quant['training_quantization'].update(decision='use',method='bnb')
  with self.assertRaisesRegex(ValueError,'missing from config'):self.run_case()
 def quant_case(self,change_weight=False,calibration=False):
  model=self.root/'selected';model.mkdir();(model/'weights.bin').write_bytes(b'original')
  identity={'files':[{'path':'weights.bin','sha256':hashlib.sha256(b'original').hexdigest()}]}
  self.cfg={'model':str(model),'quant_method':'bnb','quant_bits':4}
  self.quant['deployment_quantization'].update(decision='use',method='bnb',calibration_required=calibration,calibration_split='select')
  self.data['calibration_ids']=['b']
  c={'status':'READY_FOR_PREFLIGHT','operation':'quantize','authorization_reference':'bounded quant export','budget':{'max_steps':1,'max_wall_seconds':60,'max_gpus':1},'source_checkpoint':str(model)}
  for key,obj in [('native_config',self.cfg),('data_manifest',self.data),('quantization_decision',self.quant),('source_identity_reference',identity)]:
   data=json.dumps(obj).encode();name=key+'.json';(self.root/name).write_bytes(data);c[key]={'path':name,'sha256':hashlib.sha256(data).hexdigest()}
  if change_weight:(model/'weights.bin').write_bytes(b'replaced')
  path=self.root/'quant-contract.json';path.write_text(json.dumps(c));return mod.check(path)
 def test_quant_source_bound(self):self.assertIn('PREFLIGHT_PASS',self.quant_case()['status'])
 def test_quant_source_tamper_rejected(self):
  with self.assertRaisesRegex(ValueError,'checkpoint changed'):self.quant_case(change_weight=True)
 def test_bnb_calibration_rejected(self):
  with self.assertRaisesRegex(ValueError,'no calibration'):self.quant_case(calibration=True)
if __name__=='__main__':unittest.main()
