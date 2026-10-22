/* Kalshi order layer for Pin Radar Trader 5.0.
   REUSED from live-trader-4.17.js (archived: trader-archive/live-trader-4.17/files/live-trader-4.17.js):
     * signRequest / kalshiAuthed: RSA-PSS SHA-256 over timestamp + METHOD + path   (v4.17 lines 382-401, unchanged logic)
     * order JSON for POST /portfolio/events/orders: side 'bid' buys YES, side 'ask' sells YES (= buys NO),
       count and price as strings, immediate_or_cancel, self_trade_prevention_type, exchange_index -1 (auto-route by ticker)
       (v4.17 lines 409-423)
     * fill parsing: order.fill_count / filled_count, remaining_count                (v4.17 lines 428-430)
     * market_not_found is a per-order routing miss, not an account emergency       (v4.17 lines 440-446)
   CHANGED on purpose:
     * no +1 c slippage: the limit is exactly the price the decision was made at (the edge was computed there);
     * client_order_id is deterministic per window and attempt (a retried request cannot place a second order);
     * any other error, and any request whose outcome is unknown (timeout, HTTP 5xx / 408), latches the trader halted until a person
       resumes it; the order is then looked up by its client_order_id (findOrder) so a fill is booked, not lost;
     * the request is signed before anything is sent: a key that cannot sign is a rejection ("no order sent"), not an unknown outcome;
     * the exchange-open check reads the status of the exchange index the market trades on (KXBTC15M: 2), not the default index 0;
     * credentials never leave this module: no key material is logged or returned by any endpoint.
   Schema checked against the Kalshi Trade API spec 3.34.0 (CreateOrderV2 / CreateOrderV2Response, GetOrders, GetExchangeStatus). */
'use strict';
const crypto = require('crypto');

/* PEM normalisation, the same as the engine's normalisePem (engine/pinradar_server.js, "real multi-line PEM / literal \n /
   quoted / bare base64"), so a key the engine accepts is a key the trader can sign with */
function normalisePem(raw) {
  let k = String(raw || '');
  if (!k) return '';
  k = k.trim();
  if ((k.startsWith('"') && k.endsWith('"')) || (k.startsWith("'") && k.endsWith("'"))) k = k.slice(1, -1);
  k = k.replace(/\\n/g, '\n').replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim();
  if (k.includes('-----BEGIN')) {
    const m = k.match(/-----BEGIN ([A-Z ]+)-----([\s\S]*?)-----END \1-----/);
    if (m) { const lines = m[2].replace(/\s+/g, '').match(/.{1,64}/g) || []; k = `-----BEGIN ${m[1]}-----\n${lines.join('\n')}\n-----END ${m[1]}-----\n`; }
    return k;
  }
  const body = k.replace(/\s+/g, '');
  if (/^[A-Za-z0-9+/=]+$/.test(body) && body.length > 200) { const lines = body.match(/.{1,64}/g) || []; return `-----BEGIN PRIVATE KEY-----\n${lines.join('\n')}\n-----END PRIVATE KEY-----\n`; }
  return k;
}
/* true only for a key that can actually produce an RSA-PSS signature */
function keyUsable(pem) {
  if (!pem) return false;
  try { crypto.sign('sha256', Buffer.from('probe'), { key: crypto.createPrivateKey(pem), padding: crypto.constants.RSA_PKCS1_PSS_PADDING, saltLength: crypto.constants.RSA_PSS_SALTLEN_DIGEST }); return true; }
  catch (_) { return false; }
}

function mkKalshi({ base, keyId, privateKey, exchangeIndex = -1, statusIndex = 2, timeoutMs = 6000, fetchImpl = fetch, now = Date.now }) {
  const BASE = String(base).replace(/\/+$/, '');
  const PATH_PREFIX = new URL(BASE).pathname.replace(/\/+$/, '');          // '/trade-api/v2'
  const ready = () => !!(keyId && privateKey);

  function signRequest(method, path) {
    const ts = String(now());
    const msg = ts + method.toUpperCase() + path;
    const sig = crypto.sign('sha256', Buffer.from(msg, 'utf-8'),
      { key: privateKey, padding: crypto.constants.RSA_PKCS1_PSS_PADDING, saltLength: crypto.constants.RSA_PSS_SALTLEN_DIGEST });
    return { 'KALSHI-ACCESS-KEY': keyId, 'KALSHI-ACCESS-TIMESTAMP': ts, 'KALSHI-ACCESS-SIGNATURE': sig.toString('base64'), 'Content-Type': 'application/json' };
  }

  /* returns { ok, status, json, text } ; throws only on network failure / timeout (outcome unknown) */
  async function authed(method, path, body, headers = signRequest(method, PATH_PREFIX + path.split('?')[0])) {
    const ac = new AbortController();
    const t = setTimeout(() => { try { ac.abort(); } catch (_) { } }, timeoutMs);
    try {
      const r = await fetchImpl(BASE + path, { method, headers, signal: ac.signal, body: body ? JSON.stringify(body) : undefined });
      const text = await r.text();
      let json = null; try { json = JSON.parse(text); } catch (_) { }
      return { ok: r.ok, status: r.status, json, text: text.slice(0, 300) };
    } finally { clearTimeout(t); }
  }

  /* intent: { ticker, side: 'UP'|'DOWN', count (integer), limitCents (price of the side being bought), clientOrderId } */
  function buildBuyOrder({ ticker, side, count, limitCents, clientOrderId }) {
    if (!/^KXBTC15M-/.test(String(ticker))) throw new Error('refusing non-KXBTC15M ticker ' + ticker);
    if (!(Number.isInteger(count) && count >= 1)) throw new Error('bad count ' + count);
    if (!(limitCents > 0 && limitCents < 100)) throw new Error('bad limit ' + limitCents);
    const yes = side === 'UP';
    const yesPrice = yes ? limitCents / 100 : 1 - limitCents / 100;          // NO bought at q = YES sold at 1 - q
    return {
      ticker, client_order_id: clientOrderId,
      side: yes ? 'bid' : 'ask',
      count: Number(count).toFixed(2),
      price: yesPrice.toFixed(4),
      time_in_force: 'immediate_or_cancel',
      self_trade_prevention_type: 'taker_at_cross',
      cancel_order_on_pause: false, post_only: false, reduce_only: false, subaccount: 0, exchange_index: exchangeIndex,
    };
  }

  function parseOrderResult(json) {
    const o = json && (json.order || json);
    const filled = Number((o && (o.fill_count !== undefined ? o.fill_count : o.filled_count)) || 0);
    const remaining = Number((o && o.remaining_count) || 0);
    return { filled: Number.isFinite(filled) ? filled : 0, remaining: Number.isFinite(remaining) ? remaining : 0,
      orderId: o && (o.order_id || o.id) || null, status: o && o.status || null };
  }

  /* -> { kind: 'filled'|'nofill'|'route-miss'|'rejected'|'unknown', ... } ; never throws */
  async function placeBuy(intent) {
    const order = buildBuyOrder(intent);
    let headers;
    try { headers = signRequest('POST', PATH_PREFIX + '/portfolio/events/orders'); }
    catch (e) { return { kind: 'rejected', order, status: null, error: 'signing failed, no order sent: ' + String(e && e.message || e).slice(0, 120) }; }
    let r;
    try { r = await authed('POST', '/portfolio/events/orders', order, headers); }
    catch (e) { return { kind: 'unknown', order, error: 'no response (' + String(e && e.name === 'AbortError' ? 'timeout' : (e && e.message) || e) + '): the order may or may not exist' }; }
    if (!r.ok) {
      if (r.status >= 500 || r.status === 408) return { kind: 'unknown', order, status: r.status, error: 'HTTP ' + r.status + ' (the order may or may not exist): ' + r.text };
      if (/market_not_found/.test(r.text)) return { kind: 'route-miss', order, status: r.status, error: r.text };
      return { kind: 'rejected', order, status: r.status, error: r.text };
    }
    const p = parseOrderResult(r.json);
    const o = r.json && (r.json.order || r.json) || {};
    const avgPrice = Number(o.average_fill_price), avgFee = Number(o.average_fee_paid);
    return { kind: p.filled > 0 ? 'filled' : 'nofill', order, ...p,
      avgFillDollars: Number.isFinite(avgPrice) ? avgPrice : null, avgFeeDollars: Number.isFinite(avgFee) ? avgFee : null };
  }

  async function exchangeStatus() {
    try {
      const r = await fetchImpl(BASE + '/exchange/status', { signal: AbortSignal.timeout(timeoutMs) });
      const j = await r.json();
      /* top-level fields describe exchange index 0; KXBTC15M trades on index statusIndex (2). Missing entry -> closed (fail safe). */
      const per = j && Array.isArray(j.exchange_index_statuses) ? j.exchange_index_statuses : null;
      const s = per ? per.find(x => x && x.exchange_index === statusIndex) : j;
      return { ok: r.ok, tradingActive: !!(s && s.trading_active && j.exchange_active !== false), exchangeActive: !!(s && s.exchange_active), index: per ? statusIndex : 0,
        note: per && !s ? 'no status for exchange index ' + statusIndex : null };
    } catch (e) { return { ok: false, error: String(e && e.message || e) }; }
  }
  async function positions() { try { const r = await authed('GET', '/portfolio/positions'); return r.ok ? r.json : { error: r.status + ' ' + r.text }; } catch (e) { return { error: String(e && e.message || e) }; } }
  async function balance() { try { const r = await authed('GET', '/portfolio/balance'); return r.ok ? r.json : { error: r.status + ' ' + r.text }; } catch (e) { return { error: String(e && e.message || e) }; } }
  async function marketResult(ticker) {
    try {
      const r = await fetchImpl(BASE + '/markets/' + encodeURIComponent(ticker), { signal: AbortSignal.timeout(timeoutMs) });
      const j = await r.json(); const m = j && (j.market || j);
      const res = m && String(m.result || '').toLowerCase();
      const evRaw = String(m && m.expiration_value != null ? m.expiration_value : '').replace(/,/g, '').trim();
      const ev = evRaw === '' ? NaN : Number(evRaw);
      if (res === 'yes' || res === 'no') return { result: res, official: Number.isFinite(ev) ? ev : null };
      /* finalized without a yes/no result (void, scalar): settled, but not as a win or a loss */
      if (m && m.status === 'finalized') return { result: res || 'void', official: Number.isFinite(ev) ? ev : null, nonBinary: true };
      return null;
    } catch (_) { return null; }
  }
  /* the order with this client_order_id on this market: { ok, found, filled, status, costDollars, feesDollars } ; never throws */
  async function findOrder(ticker, clientOrderId) {
    try {
      const r = await authed('GET', '/portfolio/orders?ticker=' + encodeURIComponent(ticker) + '&limit=200');
      if (!r.ok || !r.json || !Array.isArray(r.json.orders)) return { ok: false, error: 'HTTP ' + r.status + ' ' + r.text };
      const o = r.json.orders.find(x => x && x.client_order_id === clientOrderId);
      if (!o) return { ok: true, found: false, filled: 0 };
      const n = x => { const v = Number(x); return Number.isFinite(v) ? v : 0; };
      return { ok: true, found: true, filled: n(o.fill_count_fp !== undefined ? o.fill_count_fp : o.fill_count), status: o.status || null, orderId: o.order_id || null,
        costDollars: n(o.taker_fill_cost_dollars) + n(o.maker_fill_cost_dollars), feesDollars: n(o.taker_fees_dollars) + n(o.maker_fees_dollars) };
    } catch (e) { return { ok: false, error: String(e && e.message || e) }; }
  }
  /* orders on the account since minTsSec (all markets, first page of up to 1000): { ok, orders } ; never throws */
  async function recentOrders(minTsSec) {
    try {
      const r = await authed('GET', '/portfolio/orders?min_ts=' + Math.floor(minTsSec) + '&limit=1000');
      return r.ok && r.json && Array.isArray(r.json.orders) ? { ok: true, orders: r.json.orders } : { ok: false, orders: [], error: 'HTTP ' + r.status };
    } catch (e) { return { ok: false, orders: [], error: String(e && e.message || e) }; }
  }
  return { ready, signRequest, authed, buildBuyOrder, parseOrderResult, placeBuy, exchangeStatus, positions, balance, marketResult, findOrder, recentOrders, PATH_PREFIX };
}

/* Kalshi taker fee for one order of C contracts at price p (cents): ceil(0.07 * C * P * (1 - P)) dollars, to the cent */
function kalshiFeeUsd(pCents, C, rate = 0.07) {
  const P = pCents / 100;
  return Math.ceil(rate * C * P * (1 - P) * 100 - 1e-9) / 100;
}

module.exports = { mkKalshi, kalshiFeeUsd, normalisePem, keyUsable };
