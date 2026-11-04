"""Compare the WebAssembly execution suite with the recorded Windows reference."""
import argparse
import json
import subprocess
from pathlib import Path
from test_native import compare

HERE=Path(__file__).resolve().parent

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle',type=Path,default=HERE.parent/'dist/xt660-wasm')
    p.add_argument('--report',type=Path,default=HERE/'.runs/wasm-full.json')
    p.add_argument('--reuse',action='store_true')
    a=p.parse_args();a.report.parent.mkdir(parents=True,exist_ok=True)
    if not a.reuse:
        with a.report.with_suffix('.log').open('w') as log:
            subprocess.run(['node',str(HERE/'test_wasm.mjs'),str(a.bundle),str(a.report)],stdout=log,stderr=subprocess.STDOUT,check=True)
    actual=json.loads(a.report.read_text());expected={'images':json.loads((HERE/'native-validation.json').read_text())['execution']}
    assert actual['full'] and not actual['reference']
    matched=compare(actual,expected)
    extras=['active_faults','holds','menu','history','cleared_history','coil_test','coil_rises','coil_falls','normal_after_diag']
    for result,reference in zip(actual['images'],expected['images']):
        for key in extras:assert result.get(key)==reference.get(key),(result['image'],key)
    print(f'{matched} execution checkpoints match Windows; fault history, diagnostic holds, menus and actuator traces match.')
