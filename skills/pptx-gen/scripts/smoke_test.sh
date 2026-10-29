#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PPTX_PYTHON:-python3}"
"$PYTHON_BIN" - "$SCRIPT_DIR" <<'PY'
import json, tempfile, subprocess, sys
from pathlib import Path
from PIL import Image
script=Path(sys.argv[1])
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp); images=root/'slides'; images.mkdir()
    Image.new('RGB',(1600,900),'white').save(images/'01.png')
    notes='本页解释测试图片，并承接下一页。'
    (root/'content.json').write_text(json.dumps({'title':'Smoke','pages':[{'n':1,'question':'测试','notes':notes}]},ensure_ascii=False))
    subprocess.run([sys.executable,str(script/'images_to_pptx.py'),str(images),str(root/'content.json'),str(root/'test.pptx'),'--report',str(root/'report.json')],check=True)
    result=json.loads((root/'report.json').read_text())
    assert result['slides']==result['speaker_notes']==1 and result['image_bytes_preserved']
    subprocess.run([sys.executable,str(script/'package_slide_images.py'),str(images),str(root/'images.zip'),'--expected-count','1'],check=True,capture_output=True)
    strict=subprocess.run([sys.executable,str(script/'package_slide_images.py'),str(images),str(root/'strict.zip'),'--expected-count','1','--require-4k'],capture_output=True)
    assert strict.returncode!=0 and not (root/'strict.zip').exists()
    blocked=subprocess.run([sys.executable,str(script/'generate_pptx.py')],capture_output=True,text=True)
    assert blocked.returncode==2 and 'no image or network request' in blocked.stderr
    (root/'content.json').write_text(json.dumps({'pages':[{'n':1,'notes':''}]}))
    missing=subprocess.run([sys.executable,str(script/'images_to_pptx.py'),str(images),str(root/'content.json'),str(root/'bad.pptx')],capture_output=True,text=True)
    assert missing.returncode!=0 and not (root/'bad.pptx').exists()
print('PASS: image/notes mapping, PPTX round trip, missing notes rejected, FAL disabled.')
PY
