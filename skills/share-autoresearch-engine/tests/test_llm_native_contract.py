"""Static native recipe/provenance contract checks; never GPU or model downloads."""
from pathlib import Path
import hashlib,json,unittest

SKILL=Path(__file__).resolve().parents[1]
ASSETS=SKILL/'assets/llm-native/ms-swift'

class NativeRecipeContract(unittest.TestCase):
    def test_parent_routes_to_llm_subprocess(self):
        self.assertIn('references/llm-finetuning/README.md',(SKILL/'SKILL.md').read_text())
    def test_reference_links_resolve(self):
        import re
        for p in (SKILL/'references/llm-finetuning').glob('*.md'):
            for rel in re.findall(r'\]\(([^)]+)\)',p.read_text()):
                if '://' not in rel:
                    self.assertTrue((p.parent/rel.split('#')[0]).exists(),(p,rel))
    def test_upstream_content_unchanged(self):
        rows=json.loads((ASSETS/'UPSTREAM.json').read_text())['sources']
        self.assertEqual(len(rows),6)
        for r in rows:
            self.assertNotIn('error',r)
            self.assertEqual(hashlib.sha256((ASSETS/r['snapshot']).read_bytes()).hexdigest(),r['sha256'])
        self.assertTrue((ASSETS/'upstream/LICENSE').exists())
    def test_fit_and_select_are_explicit(self):
        for name in ['sft-bf16.json','sft-qlora.json']:
            d=json.loads((ASSETS/name).read_text())
            self.assertEqual(d['split_dataset_ratio'],0)
            self.assertEqual(d['dataset'],['SET_FIT_JSONL'])
            self.assertEqual(d['val_dataset'],['SET_SELECT_JSONL'])
            self.assertFalse(d['save_only_model'])
            self.assertEqual(d['output_dir'],'SET_NEW_OUTPUT_DIR')
    def test_qlora_preserves_adapter_training_and_bf16_compute(self):
        d=json.loads((ASSETS/'sft-qlora.json').read_text())
        self.assertEqual((d['tuner_type'],d['quant_method'],d['quant_bits']),('lora','bnb',4))
        self.assertEqual(d['bnb_4bit_compute_dtype'],'bfloat16')
        self.assertFalse(d['packing'])
    def test_nonquantized_and_quantized_recipes_distinct(self):
        b=json.loads((ASSETS/'sft-bf16.json').read_text())
        self.assertNotIn('quant_method',b)
        m=json.loads((ASSETS/'merge.json').read_text())
        self.assertIn('NONQUANTIZED',m['model'])
        self.assertEqual(m['model_type'],'SET_NATIVE_MODEL_TYPE')
        self.assertEqual(m['template'],'SET_NATIVE_TEMPLATE')
        q=json.loads((ASSETS/'quantize-bnb4.json').read_text())
        self.assertNotIn('dataset',q)  # BNB on-the-fly export is not calibrated AWQ/GPTQ.
    def test_quantization_decision_is_pending_and_separate(self):
        d=json.loads((ASSETS/'quantization-decision.template.json').read_text())
        for section in ['training_quantization','deployment_quantization']:
            self.assertEqual(d[section]['decision'],'PENDING')
            self.assertTrue(d[section]['reason'].startswith('SET_'))
        self.assertEqual(d['data_boundary'],'CALIBRATION_FIT_SELECT_OR_DEDICATED_CALIBRATION_ONLY')
    def test_parent_stage_and_limitations_are_preserved(self):
        s=(SKILL/'references/llm-finetuning/README.md').read_text()
        for term in ['S0','S1','S2','S3','S4','S5','S6','S7','S8','S9','fit/select/evaluate/test']:
            self.assertIn(term,s)
        for term in ['QLoRA','PTQ','QAT']:
            self.assertIn(term,(SKILL/'references/llm-finetuning/quantization-and-release.md').read_text())
    def test_routing_cases_include_near_misses(self):
        d=json.loads((SKILL/'evals/llm-finetuning.json').read_text())
        self.assertEqual(len(d['cases']),8)
        self.assertTrue(all(c.get('request') and c.get('expected') and c.get('avoid') for c in d['cases']))

if __name__=='__main__':unittest.main()
