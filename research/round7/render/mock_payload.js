/* Build a /radar-shaped payload from the PR11 engine's exact restore-and-decide of one recorded tape second, for rendering the
   published page offline. The lock signal (state, headline, guarantee, projection, validation, trade, pr11, display27, geometry) is the
   engine's own output; the surrounding top-level fields are filled from the tape record (price, strike, index, quality, market).
   usage: PR11_MODE=gate node mock_payload.js <server.js> <tape.ndjson> <RT> <ticker> <tau> <out.json> */
'use strict'; process.env.ENABLE_WS = '0'; process.env.PINRADAR_REPLAY = '1';
const fs = require('fs'), path = require('path');
const S = require(path.resolve(process.argv[2])); const RT = require(path.resolve(process.argv[4]));
const lines = fs.readFileSync(process.argv[3], 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l));
const samples = [], recs = [], boots = [];
for (const o of lines) { if (o.k === 's') samples.push([o.t, o.v]); else if (o.k === 'd') recs.push(o); else if (o.k === 'boot') boots.push(o.ts); }
samples.sort((a, b) => a[0] - b[0]); for (let i = samples.length - 1; i > 0; i--) if (samples[i][0] === samples[i - 1][0]) samples.splice(i, 1);
const tk = process.argv[5], want = Number(process.argv[6]);
let best = null;
for (const rec of recs) { if (!rec.kal || rec.kal.ticker !== tk) continue; const tau = (rec.kal.closeMs - rec.ts) / 1000; if (!best || Math.abs(tau - want) < Math.abs(best.tau - want)) best = { rec, tau }; }
const snap = RT.restoreAndDecide(S, best.rec, samples, boots); const sig = snap.signal; const rec = best.rec;
const geo = snap.geo || {};
const payload = {
  ts: rec.ts, version: S.SERVER_VERSION || sig.serverVersion, modelVersion: sig.modelVersion, signal: sig, lastWindow: null, v28: { prereg: 'replay', configHash: 'replay', ledgerHead: null, scoredWindows: 0 },
  price: rec.liveIdx ? rec.liveIdx.value : null, strike: rec.kal.strike, strikeSource: 'kalshi:' + tk, strikeOverridden: false, kalshiStrike: rec.kal.strike, strikeMismatchUsd: null, strikeImplausible: false,
  secondsLeft: Math.round(best.tau), pinPressure: 0, level: 'GREEN', verdict: 'CLEAR', stale: false, gated: false,
  gapUsd: geo.gapUsd, gapBps: geo.gapPct != null ? geo.gapPct * 100 : null, sigmasOfCushion: geo.cushionSigma, cushionUsd: geo.gapUsd, requiredIndexMoveUsd: geo.requiredMoveUsd,
  impulse: null, pAdverseGeometry: null, pAdverseReach: null, pCrossBeforeExpiry: null, etaTouchSec: null, impliedAdverse: null, disagreementPP: null, mySide: null, naturalSide: sig.side,
  components: { geometry: 0, flow: 0, kalshi: 0, sentinel: 0 }, notes: [], reasons: ['offline render from the recorded tape second (' + new Date(rec.ts).toISOString() + ')'], ai: null, drift: 0, vol: geo.sigmaBps,
  settlement: { gapUsd: geo.gapUsd, sigmasOfCushion: geo.cushionSigma, cushionUsd: geo.gapUsd, requiredIndexMoveUsd: geo.requiredMoveUsd },
  market: { ticker: tk, strike: rec.kal.strike, strikeType: 'greater', closeMs: rec.kal.closeMs, openMs: rec.kal.openMs, secondsToClose: best.tau, yesBid: null, yesAsk: null, impliedAbove: null, rules: null },
  tauSource: 'kalshi-close_time', priceSource: 'index',
  index: { value: rec.liveIdx ? rec.liveIdx.value : null, liveAgeMs: rec.ageMs, ringValue: rec.idx ? rec.idx.value : null, ageMs: rec.ageMs, venuesUsed: rec.liveIdx ? rec.liveIdx.used : [], venuesRejected: [], dispersionBps: rec.liveIdx ? rec.liveIdx.dispersionBps : null, ringSamples: 900, single: false },
  quality: rec.quality || { grade: 'GOOD', problems: [], warnings: [] },
  sources: { spotFlow: 'offline (render)', kalshi: tk, sentinel: 'offline (render)', index: (rec.liveIdx ? rec.liveIdx.used : []).join('+') },
  spotFlow: null, kalshi: null, sentinel: null, legacy: null
};
fs.writeFileSync(process.argv[7], JSON.stringify(payload));
console.log(tk, 'tau', best.tau.toFixed(1), 'state', sig.state, '| headline', sig.headline, '| d27', sig.display27 && sig.display27.headline, '| action', sig.trade && sig.trade.action, '| pr11', JSON.stringify(sig.pr11));
