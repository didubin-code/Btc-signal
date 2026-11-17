#!/bin/bash
# Read-only verification of the deployed radar: GET /health only. Compares the served identity with the expected release.
# usage: deploy_verify.sh <expected codeSha256 (64 hex)> <expected pr11.release> <expected pr11.mode> <out dir>
# exit 0 = all expectations met; 1 = a mismatch (printed); 2 = /health unreachable
EXP_SHA=$1; EXP_REL=$2; EXP_MODE=$3; OUT=${4:-.}; mkdir -p "$OUT"; T=$(date -u +%Y%m%dT%H%M%SZ)
code=$(curl -sS --max-time 30 -o "$OUT/health_$T.json" -w '%{http_code}' https://btc-pin-radar.onrender.com/health)
if [ "$code" != "200" ]; then echo "$T VERIFY: /health HTTP $code (unreachable or failing)"; exit 2; fi
python3 -I - "$OUT/health_$T.json" "$EXP_SHA" "$EXP_REL" "$EXP_MODE" "$T" <<'PY'
import json, sys
h = json.load(open(sys.argv[1])); exp_sha, exp_rel, exp_mode, T = sys.argv[2:6]
p = h.get('pr11') or {}
v28 = h.get('v28') or {}
got = {'codeSha256': h.get('codeSha256'), 'pr11.release': p.get('release'), 'pr11.mode': p.get('mode'), 'pr11.tableSha256': p.get('tableSha256'), 'pr11.declarationSha256': p.get('declarationSha256'),
       'ingest': h.get('ingest'), 'build': h.get('build'), 'uptimeSec': h.get('uptimeSec'), 'configHash': v28.get('configHash'), 'restFallbackActive': h.get('restFallbackActive'),
       'brti.state': (h.get('brti') or {}).get('state'), 'index.ageMs': (h.get('index') or {}).get('ageMs'), 'kalshi.stale': (h.get('kalshi') or {}).get('stale'), 'ok': h.get('ok')}
checks = [('codeSha256', got['codeSha256'] == exp_sha), ('pr11.release', got['pr11.release'] == exp_rel), ('pr11.mode', got['pr11.mode'] == exp_mode),
          ('pr11.tableSha256', got['pr11.tableSha256'] == '2b1da84374755a240b076616989a217b25364f2602f1ba762c65a246686da19a'),
          ('pr11.declarationSha256', got['pr11.declarationSha256'] == '82ed0eca4e52e8a5721472cac9ff2cc47554342f0c0a1e0310473afae90003c3'), ('ok', got['ok'] is True)]
fails = [c for c, ok in checks if not ok]
print(T, 'VERIFY', 'PASS' if not fails else 'FAIL ' + ','.join(fails), '|', json.dumps(got))
sys.exit(1 if fails else 0)
PY
