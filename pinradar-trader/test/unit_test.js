/* Unit tests: the entry decision (every gate), sizing, order mapping, fees, ledger tamper detection. No network, no engine. */
'use strict';
const assert = require('assert');
const os = require('os'), fs = require('fs'), path = require('path');
const { decide, sizeForBudget, walkAsks } = require('../lib/policy');
const { mkKalshi, kalshiFeeUsd } = require('../lib/kalshi');
const { mkLedger } = require('../lib/ledger');

const CFG = { maxTradeUsd: 5, maxContracts: 1000, lockMaxFlip: 0.002, minAskCents: 90, maxAskCents: 99, minEdgeCents: 0.5, minTauSec: 15,
  maxBookAgeMs: 1500, maxAttemptsPerWindow: 2, dailyLossLimitUsd: 10, maxConsecutiveLosses: 1, maxTradesPerDay: 96, maxOpenUsd: 5,
  requireWarmVol: true, requireWarmBasis: true, requireExchangeOpen: false, strikeSaneMin: 1000 };
const NOW = 1792110000000;
function goodCtx(over = {}) {
  const sig = { state: 'LOCKED', side: 'UP', pFlip: 0.0012, pFlipCons: 0.003, gates: { hard: [], soft: [] },
    warmup: { lockedAvailable: true, volEnvelope: false, fullHistoryInSec: 0, basisCold: false, basisLiveN: 40, indexHistorySec: 5000 },
    trade: { action: 'TRADE NOW', askCents: 99, evConsCents: 0.6 }, exec: { headline: 'TRADE NOW', reason: 'buy YES' }, ...(over.sig || {}) };
  return { now: NOW, ticker: 'KXBTC15M-26OCT161200-00', strike: 82000, tau: 60, exchange: { tradingActive: true, ts: NOW },
    book: { ok: true, ageMs: 300, yesAsks: [[99, 50]], noAsks: [[2, 50]] }, ...over, sig };
}
const goodSt = (over = {}) => ({ halted: [], windows: new Map(), realizedTodayUsd: 0, consecutiveLosses: 0, tradesToday: 0, openExposureUsd: 0, inFlight: false, ...over });
const results = [];
function t(name, fn) { try { fn(); results.push([true, name]); } catch (e) { results.push([false, name + ' :: ' + e.message]); } }

t('BUY when every gate passes; plan within $5 incl. fee', () => {
  const d = decide(goodCtx(), goodSt(), CFG);
  assert.strictEqual(d.action, 'BUY', d.why.join('; '));
  assert.strictEqual(d.plan.contracts, 5); assert.strictEqual(d.plan.limitCents, 99); assert.ok(d.plan.maxCostUsd <= 5);
});
const blocks = [
  ['not LOCKED (HIGH CONFIDENCE)', goodCtx({ sig: { state: 'HIGH CONFIDENCE' } }), goodSt(), /not LOCKED/],
  ['REVERSAL WARNING', goodCtx({ sig: { state: 'REVERSAL WARNING' } }), goodSt(), /not LOCKED/],
  ['flip risk above 0.2 % even if the engine says LOCKED', goodCtx({ sig: { pFlip: 0.004 } }), goodSt(), /above the trader threshold/],
  ['DATA UNRELIABLE', goodCtx({ sig: { state: 'DATA UNRELIABLE', gates: { hard: ['venue quorum'], soft: [] } } }), goodSt(), /hard gate|data unreliable/],
  ['hard gate on a LOCKED signal', goodCtx({ sig: { gates: { hard: ['stale index'], soft: [] } } }), goodSt(), /hard gate/],
  ['engine not warm (volatility envelope)', goodCtx({ sig: { warmup: { volEnvelope: true, lockedAvailable: true, fullHistoryInSec: 400, basisCold: false } } }), goodSt(), /volatility history/],
  ['engine basis cold', goodCtx({ sig: { warmup: { volEnvelope: false, lockedAvailable: true, fullHistoryInSec: 0, basisCold: true, basisLiveN: 3 } } }), goodSt(), /basis model cold/],
  ['engine says SIT OUT (no edge)', goodCtx({ sig: { trade: { action: 'LOCKED — DO NOT TRADE', askCents: 99.9 }, exec: { headline: 'SIT OUT', reason: 'no edge' } } }), goodSt(), /engine says/],
  ['engine says TOO LATE', goodCtx({ tau: 10, sig: { trade: { action: 'LOCKED — TOO LATE' }, exec: { headline: 'TOO LATE' } } }), goodSt(), /engine says|less than/],
  ['market disagrees (ask 85 c)', goodCtx({ book: { ok: true, ageMs: 200, yesAsks: [[85, 50]], noAsks: [] } }), goodSt(), /below 90/],
  ['price above 99 c', goodCtx({ book: { ok: true, ageMs: 200, yesAsks: [[99.5, 50]], noAsks: [] } }), goodSt(), /above 99/],
  ['stale book', goodCtx({ book: { ok: true, ageMs: 4000, yesAsks: [[99, 50]], noAsks: [] } }), goodSt(), /older than/],
  ['no offers', goodCtx({ book: { ok: true, ageMs: 200, yesAsks: [], noAsks: [] } }), goodSt(), /nobody is selling/],
  ['too thin for the size', goodCtx({ book: { ok: true, ageMs: 200, yesAsks: [[99, 2]], noAsks: [] } }), goodSt(), /not enough offered/],
  ['edge at the exact limit too small', goodCtx({ sig: { pFlipCons: 0.006 } }), goodSt(), /cautious edge at the limit/],
  ['already entered this window', goodCtx(), goodSt({ windows: new Map([['KXBTC15M-26OCT161200-00', { attempts: 1, filledContracts: 5, side: 'UP' }]]) }), /already entered/],
  ['other side in this window', goodCtx(), goodSt({ windows: new Map([['KXBTC15M-26OCT161200-00', { attempts: 1, filledContracts: 0, side: 'DOWN' }]]) }), /already positioned/],
  ['attempts used up', goodCtx(), goodSt({ windows: new Map([['KXBTC15M-26OCT161200-00', { attempts: 2, filledContracts: 0, side: 'UP' }]]) }), /attempts/],
  ['halted', goodCtx(), goodSt({ halted: ['manual halt'] }), /halted/],
  ['order in flight', goodCtx(), goodSt({ inFlight: true }), /in flight/],
  ['daily loss limit', goodCtx(), goodSt({ realizedTodayUsd: -10 }), /daily loss/],
  ['consecutive losses', goodCtx(), goodSt({ consecutiveLosses: 1 }), /consecutive/],
  ['daily trade count', goodCtx(), goodSt({ tradesToday: 96 }), /trade count/],
  ['open exposure', goodCtx(), goodSt({ openExposureUsd: 4 }), /open exposure/],
  ['not a KXBTC15M market', goodCtx({ ticker: 'KXETH15M-1' }), goodSt(), /no KXBTC15M/],
  ['implausible strike', goodCtx({ strike: 45 }), goodSt(), /strike/],
  ['window closed', goodCtx({ tau: -1 }), goodSt(), /window closed/],
];
for (const [name, ctx, st, re] of blocks) t('blocks: ' + name, () => { const d = decide(ctx, st, CFG); assert.strictEqual(d.action, 'SKIP'); assert.ok(d.why.some(w => re.test(w)), d.why.join('; ')); });
t('blocks: exchange not confirmed open when required', () => {
  const d = decide(goodCtx({ exchange: { tradingActive: false, ts: NOW } }), goodSt(), { ...CFG, requireExchangeOpen: true });
  assert.strictEqual(d.action, 'SKIP'); assert.ok(d.why.some(w => /exchange/.test(w)));
});
t('DOWN call buys NO from the NO asks', () => {
  const d = decide(goodCtx({ sig: { side: 'DOWN' }, book: { ok: true, ageMs: 200, yesAsks: [[2, 50]], noAsks: [[98, 50]] } }), goodSt(), CFG);
  assert.strictEqual(d.action, 'BUY', d.why.join('; ')); assert.strictEqual(d.plan.limitCents, 98);
});
t('sizing never exceeds the cap at any price 50-99.9 c', () => {
  for (let p = 50; p <= 99.9; p = Math.round((p + 0.1) * 10) / 10) { const s = sizeForBudget(p, 5); assert.ok(s.costUsd <= 5 + 1e-9, p + ' ' + JSON.stringify(s)); assert.ok(sizeForBudget(p, 5).contracts >= 1); }
});
t('sizing: fee is Kalshi ceil(0.07 C P (1-P)) to the cent', () => { assert.strictEqual(kalshiFeeUsd(99, 5), 0.01); assert.strictEqual(kalshiFeeUsd(90, 5), 0.04); assert.strictEqual(kalshiFeeUsd(50, 100), 1.75); });
t('walk: multi-level fill', () => assert.deepStrictEqual(walkAsks([[97, 1], [98, 1], [99, 10]], 5), { limitCents: 99, avgCents: 98.4 }));
t('walk: not enough depth -> null', () => assert.strictEqual(walkAsks([[99, 3]], 5), null));
t('order mapping YES / NO and refusals', () => {
  const k = mkKalshi({ base: 'https://example.invalid/trade-api/v2', keyId: '', privateKey: '' });
  const y = k.buildBuyOrder({ ticker: 'KXBTC15M-X', side: 'UP', count: 5, limitCents: 99, clientOrderId: 'c' });
  assert.deepStrictEqual([y.side, y.price, y.count, y.time_in_force, y.exchange_index, y.reduce_only], ['bid', '0.9900', '5.00', 'immediate_or_cancel', -1, false]);
  const n = k.buildBuyOrder({ ticker: 'KXBTC15M-X', side: 'DOWN', count: 4, limitCents: 99.9, clientOrderId: 'c' });
  assert.deepStrictEqual([n.side, n.price, n.count], ['ask', '0.0010', '4.00']);
  assert.throws(() => k.buildBuyOrder({ ticker: 'KXBTC15M-X', side: 'UP', count: 0, limitCents: 99, clientOrderId: 'c' }));
  assert.throws(() => k.buildBuyOrder({ ticker: 'KXBTC15M-X', side: 'UP', count: 1.5, limitCents: 99, clientOrderId: 'c' }));
  assert.throws(() => k.buildBuyOrder({ ticker: 'KXBTC15M-X', side: 'UP', count: 1, limitCents: 100, clientOrderId: 'c' }));
  assert.throws(() => k.buildBuyOrder({ ticker: 'BTCD-X', side: 'UP', count: 1, limitCents: 99, clientOrderId: 'c' }));
});
t('ledger: hash chain verifies, and an edited line is detected', () => {
  const f = path.join(os.tmpdir(), 'pr5_ledger_test_' + process.pid + '.jsonl'); try { fs.unlinkSync(f); } catch (_) { }
  const L = mkLedger(f); L.append({ ev: 'A', x: 1 }); L.append({ ev: 'B', x: 2 }); L.append({ ev: 'C', x: 3 });
  assert.strictEqual(L.verify().ok, true);
  const lines = fs.readFileSync(f, 'utf8').split('\n'); lines[1] = lines[1].replace('"x":2', '"x":20'); fs.writeFileSync(f, lines.join('\n'));
  const v = mkLedger(f).verify(); assert.strictEqual(v.ok, false); assert.strictEqual(v.badLine, 3);
  fs.unlinkSync(f);
});

t('blocks: stressed value at the limit < 0 (engine stress passed only at the walked average)', () => {
  /* asks [[97,2],[99,50]]: 5 contracts walk to an average of 98.2 but the IOC limit is 99; stressed win prob 0.9915 -> 99.15 - 99 - 0.2 < 0 */
  const ctx = goodCtx({ book: { ok: true, ageMs: 200, yesAsks: [[97, 2], [99, 50]], noAsks: [] }, sig: { pFlipCons: 0.002, trade: { action: 'TRADE NOW', askCents: 97, evConsCents: 1.2, pWinStressCons: 0.9915 } } });
  const d = decide(ctx, goodSt(), CFG); assert.strictEqual(d.action, 'SKIP'); assert.ok(d.why.some(w => /stressed value at the limit/.test(w)), d.why.join('; '));
  const ok2 = decide(goodCtx({ sig: { trade: { action: 'TRADE NOW', askCents: 99, evConsCents: 0.6, pWinStressCons: 0.9995 } } }), goodSt(), CFG);
  assert.strictEqual(ok2.action, 'BUY', ok2.why.join('; '));
});
async function asyncCases() {
  const resp = (status, body) => async () => ({ ok: status < 300, status, text: async () => JSON.stringify(body), json: async () => body });
  const { privateKey } = require('crypto').generateKeyPairSync('rsa', { modulusLength: 2048 });
  const pem = privateKey.export({ type: 'pkcs8', format: 'pem' });
  const mk = (fetchImpl, key = pem) => mkKalshi({ base: 'https://example.invalid/trade-api/v2', keyId: 'k', privateKey: key, fetchImpl });
  const intent = { ticker: 'KXBTC15M-X', side: 'UP', count: 5, limitCents: 99, clientOrderId: 'c' };
  const cases = [];
  cases.push(['order outcome: HTTP 503 / 502 / 408 are unknown (the order may exist), 400 is rejected, market_not_found is a routing miss', async () => {
    assert.strictEqual((await mk(resp(503, {})).placeBuy(intent)).kind, 'unknown');
    assert.strictEqual((await mk(resp(502, {})).placeBuy(intent)).kind, 'unknown');
    assert.strictEqual((await mk(resp(408, {})).placeBuy(intent)).kind, 'unknown');
    assert.strictEqual((await mk(resp(400, { error: { code: 'insufficient_balance' } })).placeBuy(intent)).kind, 'rejected');
    assert.strictEqual((await mk(resp(404, { error: { code: 'market_not_found' } })).placeBuy(intent)).kind, 'route-miss');
  }]);
  cases.push(['order outcome: a key that cannot sign is a rejection with no request sent', async () => {
    let called = 0; const r = await mk(async () => { called++; return resp(201, {})(); }, 'bad-key').placeBuy(intent);
    assert.strictEqual(r.kind, 'rejected'); assert.ok(/no order sent/.test(r.error)); assert.strictEqual(called, 0);
  }]);
  cases.push(['order result: CreateOrderV2Response (top-level fill_count, average_fill_price, average_fee_paid)', async () => {
    const r = await mk(resp(201, { order_id: 'o1', fill_count: '5.00', remaining_count: '0.00', average_fill_price: '0.9800', average_fee_paid: '0.0020' })).placeBuy(intent);
    assert.deepStrictEqual([r.kind, r.filled, r.avgFillDollars, r.avgFeeDollars], ['filled', 5, 0.98, 0.002]);
  }]);
  cases.push(['exchange status: reads exchange index 2 (KXBTC15M), not the top-level index 0; a missing index fails closed', async () => {
    const st = { exchange_active: true, trading_active: true, exchange_index_statuses: [{ exchange_index: 0, trading_active: true, exchange_active: true }, { exchange_index: 2, trading_active: false, exchange_active: true }] };
    assert.strictEqual((await mk(resp(200, st)).exchangeStatus()).tradingActive, false);
    st.exchange_index_statuses[1].trading_active = true; assert.strictEqual((await mk(resp(200, st)).exchangeStatus()).tradingActive, true);
    st.exchange_index_statuses = [st.exchange_index_statuses[0]]; assert.strictEqual((await mk(resp(200, st)).exchangeStatus()).tradingActive, false);
    assert.strictEqual((await mk(resp(200, { exchange_active: true, trading_active: true })).exchangeStatus()).tradingActive, true);   // no per-index breakdown
  }]);
  cases.push(['market result: a finalized market without yes/no is non-binary; an open one is not settled', async () => {
    assert.deepStrictEqual(await mk(resp(200, { market: { result: '', status: 'finalized' } })).marketResult('KXBTC15M-X'), { result: 'void', official: null, nonBinary: true });
    assert.strictEqual(await mk(resp(200, { market: { result: '', status: 'closed' } })).marketResult('KXBTC15M-X'), null);
    assert.strictEqual((await mk(resp(200, { market: { result: 'no', status: 'finalized', expiration_value: '82,001.50' } })).marketResult('KXBTC15M-X')).official, 82001.5);
  }]);
  cases.push(['findOrder: matches client_order_id in GetOrders and reads fill_count_fp and costs', async () => {
    const k = mk(resp(200, { cursor: '', orders: [{ client_order_id: 'other', fill_count_fp: '1.00' }, { client_order_id: 'c', fill_count_fp: '3.00', taker_fill_cost_dollars: '2.9400', maker_fill_cost_dollars: '0', taker_fees_dollars: '0.0100', maker_fees_dollars: '0', status: 'executed' }] }));
    const o = await k.findOrder('KXBTC15M-X', 'c'); assert.deepStrictEqual([o.ok, o.found, o.filled, o.costDollars, o.feesDollars], [true, true, 3, 2.94, 0.01]);
    assert.deepStrictEqual(await mk(resp(200, { cursor: '', orders: [] })).findOrder('KXBTC15M-X', 'c'), { ok: true, found: false, filled: 0 });
    assert.strictEqual((await mk(resp(500, {})).findOrder('KXBTC15M-X', 'c')).ok, false);
  }]);
  for (const [name, fn] of cases) { try { await fn(); results.push([true, name]); } catch (e) { results.push([false, name + ' :: ' + e.message]); } }
}

(async () => { await asyncCases();
let ok = 0;
for (const [p, n] of results) { console.log((p ? 'ok   ' : 'FAIL ') + n); if (p) ok++; }
console.log(`unit: ${ok}/${results.length} passed`);
process.exit(ok === results.length ? 0 : 1);
})();
