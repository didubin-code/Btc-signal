/* Chronological own-memory replay: one engine file, the three capture tapes in time order. Each market's decisions are
   replayed in order; the engine keeps ITS OWN lock memory (LOCK25) between decisions. Only the first recorded decision of a
   market is seeded with the recorded lock memory (disclosed in the output). All other inputs (index ring from samples, live
   index, book, official feed state, skew, quality, previous settlement) are restored from the record exactly as in
   tools/replay_tape28.js. Output: one NDJSON row per recorded decision with the engine's own result, its PR11 fields, the
   served state (rec.out) and the recorded lock memory, plus a summary JSON.
   usage: node chrono_replay.js <server.js> <replay_tape28.js> <out prefix> <tape.ndjson>...   (PR11_MODE from env; unset = gate) */
'use strict'; process.env.PINRADAR_REPLAY = '1'; process.env.ENABLE_WS = '0';
const fs = require('fs'), path = require('path');
const S = require(path.resolve(process.argv[2])); const RT = require(path.resolve(process.argv[3])); const OUTP = process.argv[4];
const sm = new Map(), rm = new Map(), bm = new Set();
for (const t of process.argv.slice(5)) for (const l of fs.readFileSync(t, 'utf8').split('\n').filter(Boolean)) { const o = JSON.parse(l); if (o.k === 's') sm.set(o.t, [o.t, o.v]); else if (o.k === 'd' && o.kal) rm.set(o.kal.ticker + '|' + o.ts, o); else if (o.k === 'boot') bm.add(o.ts); }
const samples = [...sm.values()].sort((a, b) => a[0] - b[0]), boots = [...bm].sort((a, b) => a - b), recs = [...rm.values()].sort((a, b) => a.ts - b.ts);
const own = new Map(), initial = [], gaps = [], lastTs = new Map(); const out = fs.openSync(OUTP + '.ndjson', 'w'); let n = 0;
for (const original of recs) {
  const r = JSON.parse(JSON.stringify(original)), tk = r.kal.ticker, tau = (r.kal.closeMs - r.ts) / 1000;
  if (own.has(tk)) r.lock25 = own.get(tk); else initial.push({ ticker: tk, tau: +tau.toFixed(3), seededLockedSide: r.lock25 && r.lock25.lockedSide, seededHist: r.lock25 ? r.lock25.hist.length : 0 });
  if (lastTs.has(tk) && r.ts - lastTs.get(tk) > 1600) gaps.push({ ticker: tk, fromTs: lastTs.get(tk), toTs: r.ts, gapMs: r.ts - lastTs.get(tk) }); lastTs.set(tk, r.ts);
  const snap = RT.restoreAndDecide(S, r, samples, boots); const sg = snap.signal || {}, g = snap.geo || {}, st = snap.settle || {}, gates = snap.gates || { soft: [], hard: [] };
  own.set(tk, { ticker: S.LOCK25.ticker, hist: S.LOCK25.hist.map(h => ({ t: h.t, pUp: h.pUp })), lockedSide: S.LOCK25.lockedSide, lockedAtTau: S.LOCK25.lockedAtTau, revNoted: S.LOCK25.revNoted });
  const row = { ts: r.ts, ticker: tk, closeMs: r.kal.closeMs, tau: +tau.toFixed(3), strike: r.kal.strike, liveIdx: r.liveIdx ? r.liveIdx.value : null, obTs: r.obTs,
    state: sg.state, side: sg.side, pWin: sg.pWin, pFlip: sg.pFlip, pFlipCons: sg.pFlipCons, status: sg.status, action: sg.trade ? sg.trade.action : null, askCents: sg.trade ? sg.trade.askCents : null, depth: sg.trade ? sg.trade.depth : null,
    ownLockedSide: S.LOCK25.lockedSide, ownLockedAtTau: S.LOCK25.lockedAtTau, recLockedSide: original.lock25 && original.lock25.lockedSide, recLockedAtTau: original.lock25 && original.lock25.lockedAtTau,
    served: original.out || null, geo: { gap: g.gapUsd, index: g.index, n: g.n, nLock: g.nLock, lobs: g.lockedObserved, filledLive: g.lockedFilledLive == null ? null : g.lockedFilledLive, cov: g.lockedCoverage, sigma: g.sigmaBps, regime: g.regime ? g.regime.bucket : null },
    ref: st.reference, gatesSoft: (gates.soft || []).length, gatesHard: (gates.hard || []).length, soft: gates.soft || [], pr11: sg.pr11 || null };
  fs.writeSync(out, JSON.stringify(row) + '\n'); n++;
}
fs.closeSync(out);
const summary = { server: path.basename(process.argv[2]), mode: S.PR11_MODE || 'n/a(base)', rows: n, markets: initial.length, samples: samples.length, boots: boots.length, initial, gapsOver1600ms: gaps.length, gaps: gaps.slice(0, 50) };
fs.writeFileSync(OUTP + '.summary.json', JSON.stringify(summary, null, 1)); console.log(JSON.stringify({ server: summary.server, mode: summary.mode, rows: n, markets: initial.length, seededNonNull: initial.filter(i => i.seededLockedSide).length, gaps: gaps.length }));
process.exit(0);
