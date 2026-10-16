/* npm test: every suite in its own process (no shared state), each must exit 0.
     unit          the entry decision (every gate), sizing, order mapping, fees, ledger tamper detection
     selftest      the trader's /selftest (engine hash, threshold, sizing, orders, the engine's own self-test)
     live_mock     execution and safety against a local mock Kalshi API (signatures, fills, rejections, timeouts, halts, no key leaks)
     engine_replay the real engine + the trader's main loop over one day of real history (SKIPPED when the data is absent)  */
'use strict';
const { spawnSync } = require('child_process');
const path = require('path'), os = require('os'), fs = require('fs');
const ROOT = path.join(__dirname, '..');
const SELFTEST = "const T=require('./trader.js');T.loadEngine();const r=T.selfTest();for(const c of r.checks)console.log((c.pass?'ok   ':'FAIL ')+c.name+(c.pass?'':' :: '+JSON.stringify(c.got)));console.log('selftest: '+r.passed+'/'+r.total+' passed');process.exit(r.ok?0:1)";
const suites = [
  ['unit', ['test/unit_test.js']],
  ['selftest', ['-e', SELFTEST]],
  ['live_mock', ['test/live_mock_test.js']],
  ['engine_replay', ['test/engine_replay_test.js']],
];
const LEDGER = path.join(os.tmpdir(), 'pr5_runall_' + process.pid + '.jsonl');
const env = { ...process.env, ENABLE_WS: '0', TRADER_LEDGER_FILE: LEDGER };
for (const k of ['LIVE', 'TRADER_LIVE_ARM', 'KALSHI_KEY_ID', 'KALSHI_PRIVATE_KEY']) delete env[k];
let failed = 0;
for (const [name, args] of suites) {
  const t = Date.now();
  const r = spawnSync(process.execPath, args, { cwd: ROOT, env, encoding: 'utf8', maxBuffer: 64 << 20, timeout: 30 * 60 * 1000 });
  const out = (r.stdout || '') + (r.stderr || '');
  const last = out.trim().split('\n').filter(l => /passed|SKIPPED/.test(l)).pop() || '(no summary line)';
  const pass = r.status === 0;
  if (!pass) { failed++; console.log(out); }
  console.log((pass ? 'PASS ' : 'FAIL ') + name.padEnd(14) + last + '  (' + ((Date.now() - t) / 1000).toFixed(1) + ' s)');
}
try { fs.unlinkSync(LEDGER); } catch (_) { }
console.log(failed ? failed + ' suite(s) FAILED' : 'all suites passed');
process.exit(failed ? 1 : 0);
