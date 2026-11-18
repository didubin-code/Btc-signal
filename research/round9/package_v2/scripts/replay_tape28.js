#!/usr/bin/env node
/* Replay a Pin Radar 2.8 record/replay tape through the UNMODIFIED production function
   computeLockSnapshot (the same function /radar and the background classifier call), restoring
   exactly the state each recorded decision saw, and compare every output with what the live
   server recorded at the time. 0 mismatches = LIVE and REPLAY made identical decisions.

   usage: node tools/replay_tape28.js <pinradar_server.js> <tape.ndjson> [out.json]
          (tape from GET /tape?format=ndjson, or the TAPE_FILE the server appends to)          */
'use strict';
const KEEP_MS = 960 * 1000;                 // RING_KEEP_SEC in the server

function outKey(o) {
  if (!o) return 'null';
  const r = x => (x == null || !Number.isFinite(x)) ? null : +Number(x).toPrecision(10);
  return [o.state, o.side, r(o.pWin), r(o.pFlip), r(o.pFlipCons), o.action, r(o.ev)].join('|');
}
/* samples: [[ts, value], ...] sorted ascending; boots: process start times (TAPE_FILE 'boot' lines), ascending.
   A process starts with an empty ring: samples written before the latest boot at or before ts were not in its memory. */
function ringAt(samples, ts, boots = []) {
  let hi = samples.length - 1, lo = 0, last = -1;
  while (lo <= hi) { const m = (lo + hi) >> 1; if (samples[m][0] <= ts) { last = m; lo = m + 1; } else hi = m - 1; }
  if (last < 0) return [];
  let bootTs = -Infinity; for (const b of boots) if (b <= ts) bootTs = b;
  const L = samples[last][0], out = [];
  for (let i = last; i >= 0 && samples[i][0] >= L - KEEP_MS && samples[i][0] >= bootTs; i--) out.push([samples[i][0], samples[i][1]]);
  return out.reverse();
}
let FEE_DEFAULT = null;
function restoreAndDecide(S, rec, samples, boots = []) {
  /* the fee schedule in force at the decision (recorded only when it is not the default) */
  if (S.FEE28) { if (!FEE_DEFAULT) FEE_DEFAULT = JSON.parse(JSON.stringify(S.FEE28.cfg)); S.FEE28.cfg = rec.fee && rec.fee.cfg ? { ...rec.fee.cfg } : { ...FEE_DEFAULT }; S.fee28Recompute(); }
  const ring = ringAt(samples, rec.ts, boots);
  S.IDX.ring.length = 0; for (const p of ring) S.IDX.ring.push(p);
  if (rec.idx) Object.assign(S.IDX, { value: rec.idx.value, ts: rec.idx.ts, venuesUsed: rec.idx.venuesUsed.slice(), dispersionBps: rec.idx.dispersionBps, lastReason: rec.idx.lastReason });
  S.KAL.ob = rec.ob ? { ticker: rec.ob.ticker, yes: rec.ob.yes, no: rec.ob.no } : null; S.KAL.obTs = rec.obTs;
  S.SKEW.samples.length = 0; for (let i = 0; i < rec.skew.n; i++) S.SKEW.samples.push(rec.skew.est); S.SKEW.estMs = rec.skew.est;
  S.RESTF.active = !!rec.rest;
  Object.assign(S.LOCK25, { ticker: rec.lock25.ticker, hist: rec.lock25.hist.map(h => ({ t: h.t, pUp: h.pUp })), lockedSide: rec.lock25.lockedSide,
    lockedAtTau: rec.lock25.lockedAtTau, revNoted: rec.lock25.revNoted });
  Object.assign(S.BRTI, { enabled: rec.brti.enabled, last: rec.brti.last, last5: rec.brti.last5, win: rec.brti.win });
  S.SETTLE.done.length = 0;
  if (rec.prevSettled) S.SETTLE.done.push({ ticker: rec.prevSettled.ticker, closeMs: rec.prevSettled.closeMs, status: 'SETTLED', official: rec.prevSettled.official });
  return S.computeLockSnapshot({ now: rec.ts, kal: rec.kal, strike: rec.kal.strike, strikeIssue: rec.strikeIssue, overrides: [], quality: rec.quality,
    liveIdx: rec.liveIdx, liveIndexAgeMs: rec.ageMs == null ? Infinity : rec.ageMs, side: null, mutate: true, basisMu: rec.basisMu });
}
function replayTape(S, lines) {
  const samples = [], recs = [], boots = [];
  for (const o of lines) { if (o.k === 's') samples.push([o.t, o.v]); else if (o.k === 'd') recs.push(o); else if (o.k === 'boot') boots.push(o.ts); }
  samples.sort((a, b) => a[0] - b[0]); boots.sort((a, b) => a - b);
  for (let i = samples.length - 1; i > 0; i--) if (samples[i][0] === samples[i - 1][0]) samples.splice(i, 1);   // a rotated file repeats its ring history
  const res = { records: recs.length, samples: samples.length, mismatches: 0, examples: [], byState: {} };
  for (const rec of recs) {
    const snap = restoreAndDecide(S, rec, samples, boots);
    const s = snap.signal;
    const got = { state: s.state, side: s.side, pWin: s.pWin, pFlip: s.pFlip, pFlipCons: s.pFlipCons, action: s.trade ? s.trade.action : null, ev: s.trade ? s.trade.evConsCents : null };
    res.byState[got.state] = (res.byState[got.state] || 0) + 1;
    if (outKey(got) !== outKey(rec.out)) { res.mismatches++; if (res.examples.length < 10) res.examples.push({ ts: rec.ts, ticker: rec.kal && rec.kal.ticker, live: outKey(rec.out), replay: outKey(got) }); }
  }
  return res;
}
module.exports = { replayTape, restoreAndDecide, ringAt, outKey };

if (require.main === module) {
  process.env.ENABLE_WS = '0'; process.env.PINRADAR_REPLAY = '1';
  const fs = require('fs'), path = require('path');
  const S = require(path.resolve(process.argv[2]));
  const lines = fs.readFileSync(process.argv[3], 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l));
  const res = replayTape(S, lines);
  if (process.argv[4]) fs.writeFileSync(process.argv[4], JSON.stringify(res, null, 1));
  console.log(JSON.stringify(res));
  process.exit(res.mismatches ? 1 : 0);
}
