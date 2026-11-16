"""Tests for respond_v2 (python3 -I respond_v2_tests.py). Cases: (1) the recorded 12:31Z Nov 15 finding from the real copies: v1 REVERT R7,
v2 HOLD H1; (2) a synthetic identity storm (+400 in the same interval): v2 REVERT R7; (3) a stated wait: REVERT R7; (4) missing counters: R7u;
(5) hold already used: R5; (6) no episode: NONE; (7) still being lost now: R6."""
import json, sys, os, copy, importlib.util, time
HERE = os.path.dirname(os.path.abspath(__file__)); SC = '/tmp/claude-0/-home-user/97d7fe1d-a1f3-5240-8215-edf8d0a9a961/scratchpad'
spec = importlib.util.spec_from_file_location('respond_v2', os.path.join(HERE, 'respond_v2.py')); v2 = importlib.util.module_from_spec(spec); spec.loader.exec_module(v2); v1 = v2.v1
prev = json.load(open(SC + '/r30/live/health/health_20261115T0632Z.json')); cur = json.load(open(SC + '/r30/live/health/health_20261115T1232Z.json'))
snaps = v2.load_snapshots([SC + '/r30/live/health/health_2026111[345]T*.json'])   # the 6-hourly and hourly copies up to the finding (no later information)
snaps = [s for s in snaps if s['t'] <= cur['ts'] / 1000.0]
samples = []; now = cur['ts'] / 1000.0 + 300
fails = 0
def check(name, cond, info=''):
    global fails
    print(('ok   ' if cond else 'FAIL ') + name + (': ' + str(info) if info not in ('', None) else ''))
    if not cond: fails += 1
r1 = v1.decide_past(prev, cur, samples, now); check('v1 recorded result reproduced: REVERT R7', r1['action'] == 'REVERT' and r1['code'] == 'R7', r1['reasons'][0][:80])
r2 = v2.decide_past_v2(prev, cur, samples, now, snaps=snaps); check('v2 on the same copies: HOLD H1 (identity at background rate)', r2['action'] == 'HOLD' and r2['code'] == 'H1', json.dumps(r2['evidence'].get('identity')))
cur2 = copy.deepcopy(cur); cur2['kalshi']['marketRecord']['rejected']['identity'] = prev['kalshi']['marketRecord']['rejected']['identity'] + 400
r3 = v2.decide_past_v2(prev, cur2, samples, now, snaps=snaps); check('v2 identity storm (+400 in 6 h): REVERT R7', r3['action'] == 'REVERT' and r3['code'] == 'R7', r3['evidence'].get('identity', {}).get('excessSE'))
cur3 = copy.deepcopy(cur); cur3['kalshi']['refusals']['statedWait']['count'] = 1
r4 = v2.decide_past_v2(prev, cur3, samples, now, snaps=snaps); check('v2 stated wait obeyed: REVERT R7', r4['action'] == 'REVERT' and r4['code'] == 'R7')
cur4 = copy.deepcopy(cur); del cur4['kalshi']['marketRecord']['rejected']['identity']
r5 = v2.decide_past_v2(prev, cur4, samples, now, snaps=snaps); check('v2 identity counter missing: REVERT R7u', r5['action'] == 'REVERT' and r5['code'] == 'R7u')
r6 = v2.decide_past_v2(prev, cur, samples, now, hold_used=True, snaps=snaps); check('v2 hold already used: REVERT R5', r6['action'] == 'REVERT' and r6['code'] == 'R5')
r7 = v2.decide_past_v2(prev, prev, samples, now, snaps=snaps); check('v2 no new episode: NONE', r7['action'] == 'NONE')
bad = [{'t': now - 50 + i * 5, 'ok': True, 'elig': True, 'lost': 5.0, 'dt': 5.0} for i in range(10)]
r8 = v2.decide_past_v2(prev, cur, bad, now, snaps=snaps); check('v2 decisions still being lost now: REVERT R6', r8['action'] == 'REVERT' and r8['code'] == 'R6', r8['evidence'].get('continuingWhy'))
# v2 with only the two 6-hourly copies and no other intervals: attribution cannot be estimated -> R7u (conservative when information is missing)
r9 = v2.decide_past_v2(prev, cur, samples, now, snaps=[]); check('v2 without background intervals: REVERT R7u', r9['action'] == 'REVERT' and r9['code'] == 'R7u', r9['reasons'][0][-90:])
print('FAILS', fails); sys.exit(1 if fails else 0)
