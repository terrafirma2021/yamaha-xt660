"""Share the website's two connector redraws with the desktop application."""
import json
from pathlib import Path
from site_flashing import connection_data

ROOT = Path(__file__).resolve().parents[1]
data = connection_data(json.loads((ROOT/'analysis/firmware/catalog.json').read_text(encoding='utf-8')))
out = ROOT/'flasher/build'
out.mkdir(parents=True, exist_ok=True)
(out/'connections.json').write_text(json.dumps({'families':data['families'],'kkl':data['kkl']},ensure_ascii=False),encoding='utf-8')
print('Prepared both website connector drawings for the desktop app (no source photographs).')
