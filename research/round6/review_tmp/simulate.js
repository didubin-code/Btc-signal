'use strict';
/* Drive the REAL pinradarSource.tape task against a fake server that applies production's exact /tape semantics
   (samples: t > since; rows: ts > since; samples first then rows; ring of 3000 rows; samples kept from rows[0].ts - 960 s)
   fed from the real tape, with hourly pulls at every phase of the 15-min window. Counts false gaps and duplicated samples. */
const fs = require('fs');
const { pinradarSource, ndjson } = require('/home/user/btc-ai-backend/pinradar-observer/lib/sources');
const F = process.argv[2];
const all = ndjson(fs.readFileSync(F, 'utf8'));
const D = all.filter(x => x.k === 'd').sort((a, b) => a.ts - b.ts), S = all.filter(x => x.k === 's').sort((a, b) => a.t - b.t);
const t0 = S[0].t, tEnd = D[D.length - 1].ts;
function serve(nowMs, since) {           // production's ring as it would stand at nowMs
  let rows = D.filter(r => r.ts <= nowMs); if (rows.length > 3000) rows = rows.slice(rows.length - 3000);
  const keepFrom = (rows.length ? rows[0].ts : nowMs) - 960000;
  let samples = S.filter(p => p.t <= nowMs && p.t >= keepFrom); if (samples.length > 13000) samples = samples.slice(samples.length - 13000);
  const sm = samples.filter(p => p.t > since), rw = rows.filter(r => r.ts > since);
  return sm.map(p => JSON.stringify(p)).concat(rw.map(r => JSON.stringify(r))).join('\n') + '\n';
}
const results = [];
for (let phase = 0; phase < 900e3; phase += 30e3) {
  const P0 = t0 + 960e3 + 3600e3 + phase;              // first pull once the ring holds > 1 h
  if (P0 + 3600e3 > tEnd) break;
  let nowMs = P0; const em = [];
  const http = { get: async url => { const u = new URL(url); return { ok: true, status: 200, tSent: nowMs, tRecv: nowMs + 50, text: serve(nowMs, Number(u.searchParams.get('since'))) }; } };
  const pr = pinradarSource({ base: 'https://pr', http, emit: o => em.push(o), now: () => nowMs, state: {} });
  await0: { }
  const run = async () => {
    await pr.step(nowMs);                                    // pull 1 (since=0)
    nowMs = P0 + 3600e3; await pr.step(nowMs);               // pull 2, one hour later
    const recs = em.filter(o => o.kind === 'pr.tape');
    const seen1 = new Set(recs[0].rows.filter(x => x.k === 's').map(x => x.t));
    const dup = recs[1].rows.filter(x => x.k === 's' && seen1.has(x.t)).length;
    const tau = (P0 - t0) % 900e3;                                        // position of the pull inside a 15-min cycle (arbitrary origin)
    results.push({ phase: phase / 1000, gap: recs[1].gap ? Math.round(recs[1].gap.ms / 1000) : 0, dupSamples: dup, samples2: recs[1].samples, decisions2: recs[1].decisions, boots: recs[1].boots });
  };
  results.push(run);
}
(async () => {
  const out = [];
  for (const r of results) if (typeof r === 'function') await r();
  const rows = results.filter(r => typeof r !== 'function');
  const falseGaps = rows.filter(r => r.gap > 0);
  console.log('phases tried', rows.length, '| second pull records a gap in', falseGaps.length, 'of them (sizes s):', falseGaps.map(r => r.gap).join(','));
  console.log('duplicated samples per hourly pull: min', Math.min(...rows.map(r => r.dupSamples)), 'max', Math.max(...rows.map(r => r.dupSamples)), 'mean', (rows.reduce((a, r) => a + r.dupSamples, 0) / rows.length).toFixed(0), '| samples per hourly pull ~', rows[0].samples2, '| decisions per hourly pull ~', rows[0].decisions2, '| boots', rows[0].boots);
  console.log(JSON.stringify(rows.slice(0, 12)));
})();
