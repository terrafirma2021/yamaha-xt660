"""Compare the WebAssembly execution suite with the recorded Windows reference."""
import argparse
import json
import math
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
        assert len(result['gearing'])==len(reference['gearing'])
        for gear,baseline in zip(result['gearing'],reference['gearing']):
            for key,value in gear.items():
                if isinstance(value,float):assert math.isclose(value,baseline[key],rel_tol=0,abs_tol=1e-8),(result['image'],key)
                else:assert value==baseline[key],(result['image'],key)
        assert len(result['dynamics'])==len(reference['dynamics'])==2
        for mode,baseline in zip(result['dynamics'],reference['dynamics']):
            assert mode.keys()==baseline.keys()
            for key,value in mode.items():
                # C++ libm differs by a few trillionths of an RPM. Firmware
                # checkpoints, cut counts and bus-cycle timing remain exact.
                if key.endswith('_rpm'):assert math.isclose(value,baseline[key],rel_tol=0,abs_tol=1e-8),(result['image'],key)
                else:assert value==baseline[key],(result['image'],key)
    print(f'{matched} execution checkpoints match Windows; diagnostics, gearing replies and limiter timing match; floating metrics agree within 1e-8.')
