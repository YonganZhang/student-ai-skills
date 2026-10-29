"""dl_project_contract.py: init refuses overwrite, check finds placeholders/missing pointer/missing marked paths,
passes when filled."""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'dl_project_contract.py'
TEMPLATE = Path(__file__).resolve().parents[1] / 'assets' / 'project-contract.template.md'
REL = 'docs/dl-project-contract.md'


def run(*args):
    r = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout


class ContractTest(unittest.TestCase):
    def test_init_check_fill_cycle(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); (p / '_wiki-methodology').mkdir(); (p / 'AGENTS.md').write_text('# x\n')
            code, out = run('init', '--project', d)
            self.assertEqual(code, 0, out)
            rel = json.loads(out)['path']
            self.assertEqual(run('init', '--project', d)[0], 1)                      # no overwrite
            code, out = run('check', '--project', d)
            self.assertEqual(code, 1)
            f = json.loads(out)['findings']
            self.assertTrue(any('placeholder' in x for x in f) and any('AGENTS.md' in x for x in f))
            text = Path(rel).read_text().replace('<<填写', '已填').replace('>>', '')
            text += '\n见 `path:src/missing.py`\n'
            Path(rel).write_text(text)
            run('init', '--project', d, '--path', 'other.md', '--add-pointer')       # pointer mechanics on another file
            (p / 'AGENTS.md').write_text('- 读 `_wiki-methodology/_wiki/_methods/dl-project-contract.md`\n')
            code, out = run('check', '--project', d)
            self.assertEqual(code, 1)
            self.assertIn('path not found: src/missing.py', json.loads(out)['findings'])
            (p / 'src').mkdir(); (p / 'src/missing.py').write_text('')
            code, out = run('check', '--project', d)
            self.assertEqual(code, 0, out)

    def test_add_pointer_once(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'AGENTS.md').write_text('# x\n')
            run('init', '--project', d, '--add-pointer')
            text = (Path(d) / 'AGENTS.md').read_text()
            self.assertEqual(text.count('docs/dl-project-contract.md'), 1)


class PathMarkerTest(unittest.TestCase):
    """Only `path:REL` markers (project-relative) and relative Markdown links are checked; the contract body is
    built from the template's section headings only, so these tests do not depend on the template's prose."""

    def check(self, body, files=()):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / 'docs').mkdir()
            (p / 'AGENTS.md').write_text(f'- 读 `{REL}`\n')
            for f in files:
                (p / f).parent.mkdir(parents=True, exist_ok=True)
                (p / f).write_text('')
            sections = sorted(set(re.findall(r'^## (\d+)\. ', TEMPLATE.read_text(encoding='utf-8'), re.M)), key=int)
            head = ''.join(f'## {n}. 节\n\n' for n in sections)
            (p / REL).write_text(head + body + '\n', encoding='utf-8')
            code, out = run('check', '--project', d, '--path', REL)
            return code, json.loads(out)

    def test_root_level_and_nested_marked_paths_must_exist(self):
        body = '入口 `path:missing_train.py`，配置 `path:configs/a.yaml`。'
        code, out = self.check(body)
        self.assertEqual(code, 1)
        self.assertIn('path not found: missing_train.py', out['findings'])
        self.assertIn('path not found: configs/a.yaml', out['findings'])
        code, out = self.check(body, files=('missing_train.py', 'configs/a.yaml'))
        self.assertEqual((code, out['findings']), (0, []))

    def test_formulas_commands_and_unmarked_spans_are_not_paths(self):
        body = ('指标 `TP/(TP+FP)`，划分 `fit/select/evaluate`，命令 `python3 src/train.py --cfg a/b`，'
                '普通代码 `src/not_marked.py`，示例 `path:<相对项目根的路径>`。')
        code, out = self.check(body)
        self.assertEqual((code, out['findings']), (0, []), out)

    def test_absolute_paths_are_reported_external_not_failed(self):
        body = '标签 `path:/missing-data/labels.csv`，环境 `path:~/envs/x/bin/python`。'
        code, out = self.check(body)
        self.assertEqual((code, out['findings']), (0, []), out)
        self.assertEqual(out['external_not_checked'], ['/missing-data/labels.csv', '~/envs/x/bin/python'])

    def test_relative_markdown_links_resolve_from_the_contract(self):
        body = '见 [训练](../src/train.py)、[本节](#1-节)、[官网](https://example.org/a/b)、[缺](../nope.md#x)。'
        code, out = self.check(body, files=('src/train.py',))
        self.assertEqual((code, out['findings']), (1, ['link not found: ../nope.md#x']), out)


    def test_link_syntax_edges(self):
        body = ('[括号](../src/a(b).py)、命令 `echo [x](relative)`、[`代码名`](../src/train.py)、'
                '[空格](<../missing name.md>)。\n```\n[fence](nowhere.md)\n```')
        code, out = self.check(body, files=('src/a(b).py', 'src/train.py'))
        self.assertEqual((code, out['findings']), (1, ['link not found: ../missing name.md']), out)

if __name__ == '__main__':
    unittest.main()
