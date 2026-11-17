#!/bin/bash
# One attended-window check (read-only GETs): identity via deploy_verify.sh, then the per-second rows served since the last check
# (/predictions?since=<cursor>&format=ndjson) tested for served-rule violations. Writes one line to STATUS_WINDOW.txt and, on any
# failure, the file FLAG (the attended loop exits on it). usage: window_check.sh <expected sha> <expected release> <expected mode> <build-from-ms> <out dir>
EXP_SHA=$1; EXP_REL=$2; EXP_MODE=$3; BUILD_FROM=$4; OUT=$5; mkdir -p "$OUT/live_pred"; T=$(date -u +%Y%m%dT%H%M%SZ)
V=$(bash "$(dirname "$0")/deploy_verify.sh" "$EXP_SHA" "$EXP_REL" "$EXP_MODE" "$OUT/verify_runs" 2>&1 | tail -1); vrc=$?
CUR=$(cat "$OUT/pred_cursor" 2>/dev/null || echo 0)
code=$(curl -sS --max-time 30 -o "$OUT/live_pred/pred_$T.ndjson" -w '%{http_code}' "https://btc-pin-radar.onrender.com/predictions?since=$CUR&n=5000&format=ndjson")
python3 -I - "$OUT/live_pred/pred_$T.ndjson" "$BUILD_FROM" "$OUT" "$T" "$code" "$V" <<'PY'
import json, sys, os
p, build_from, out, T, code, V = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6]
rows = []
if code == '200':
    for l in open(p):
        l = l.strip()
        if not l: continue
        try: rows.append(json.loads(l))
        except Exception: pass
rows.sort(key=lambda r: r.get('ts', 0))
c = {'rows': len(rows), 'locked120': 0, 'proven120': 0, 'withheld120': 0, 'qualified120': 0, 'C1': 0, 'C1b': 0, 'C2': 0, 'C3': 0, 'dataUnreliable': 0, 'tradeNow': 0}
ex = []
for r in rows:
    st, tau, adm, pf, act, soft = r.get('state'), r.get('tau'), r.get('pr11Admit', None), r.get('pFlip'), r.get('action'), r.get('gatesSoft')
    locked = st in ('LOCKED', 'PROVEN LOCKED')
    if st == 'DATA UNRELIABLE': c['dataUnreliable'] += 1
    if act == 'TRADE NOW':
        c['tradeNow'] += 1
        if not locked: c['C3'] += 1; ex.append(('C3', r.get('ticker'), tau, st, act))
    if tau is not None and 0 < tau <= 120:
        if locked:
            c['locked120'] += 1
            if st == 'PROVEN LOCKED': c['proven120'] += 1
            if adm is False: c['C1'] += 1; ex.append(('C1', r.get('ticker'), tau, st, adm))
            elif adm is None and r.get('ts', 0) >= build_from: c['C2'] += 1; ex.append(('C2', r.get('ticker'), tau, st))
            elif adm is True: c['qualified120'] += 1
        if st == 'HIGH CONFIDENCE' and pf is not None and pf <= 0.002:
            if adm is False: c['withheld120'] += 1
            elif adm is True and soft == 0 and r.get('ts', 0) >= build_from: c['C1b'] += 1; ex.append(('C1b', r.get('ticker'), tau, st, pf, soft))
if rows: open(os.path.join(out, 'pred_cursor'), 'w').write(str(rows[-1]['ts'] + 1))
flags = [k for k in ('C1', 'C1b', 'C2', 'C3') if c[k]]
if not V.split(' VERIFY ')[1].startswith('PASS'): flags.append('VERIFY')
if code != '200': flags.append('PRED_HTTP_' + code)
line = '%s WINDOW CHECK | %s | rows %d (locked120 %d, proven120 %d, qualified120 %d, withheld120 %d, data-unreliable %d, trade-now %d) | C1 %d C1b %d C2 %d C3 %d | %s' % (
    T, V.split(' | ')[0], c['rows'], c['locked120'], c['proven120'], c['qualified120'], c['withheld120'], c['dataUnreliable'], c['tradeNow'], c['C1'], c['C1b'], c['C2'], c['C3'], ('FLAGS ' + ','.join(flags)) if flags else 'clean')
open(os.path.join(out, 'STATUS_WINDOW.txt'), 'a').write(line + '\n'); print(line)
if ex: print('EXAMPLES', json.dumps(ex[:5]))
if flags:
    open(os.path.join(out, 'FLAG'), 'a').write(line + '\n' + json.dumps(ex[:10]) + '\n'); sys.exit(3)
PY
