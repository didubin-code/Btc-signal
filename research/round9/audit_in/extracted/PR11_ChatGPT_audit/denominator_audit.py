"""Audit only. Does not modify the candidate or its data.
Usage: python3 denominator_audit.py PACKAGE_DIR OUTPUT_JSON
The package's data archives must have been unpacked per REPRODUCE.md.
"""
import json
import sys
from pathlib import Path

package = Path(sys.argv[1]).resolve()
differences = []
for path in sorted((package / 'data/unpacked/d3').glob('B9_*.ndjson')):
    for line in path.open():
        row = json.loads(line)
        geo = row.get('geo')
        pr11 = row.get('pr11') or {}
        if not (geo and pr11.get('applies') and pr11.get('admit')
                and row['state'] in ('LOCKED', 'PROVEN LOCKED')):
            continue
        scale = 60 / pr11['h'] if geo['nLock'] >= 1 and row['tau'] <= 60 else 1
        strike_r = abs(geo['gap']) / row['strike'] * 10000 * scale
        current_r = abs(geo['gap']) / geo['index'] * 10000 * scale
        if current_r < pr11['rstar'] <= strike_r:
            differences.append(dict(
                ticker=row['ticker'], ts=row['ts'], tau=row['tau'], side=row['side'],
                strike=row['strike'], index=geo['index'], R=strike_r,
                currentPriceR=current_r, floor=pr11['rstar']))
Path(sys.argv[2]).write_text(json.dumps(differences, indent=2) + '\n')
print(json.dumps(dict(rows=len(differences), windows=len({r['ticker'] for r in differences}),
                     examples=differences[:5])))
