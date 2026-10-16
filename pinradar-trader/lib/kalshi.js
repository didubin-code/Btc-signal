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
     * any other error, and any request whose outcome is unknown (timeout), latches the trader halted until a person resumes it;
     * credentials never leave this module: no key material is logged or returned by any endpoint. */
'use strict';
const crypto = require('crypto');

function mkKalshi({ base, keyId, privateKey, exchangeIndex = -1, timeoutMs = 6000, fetchImpl = fetch, now = Date.now }) {
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
  async function authed(method, path, body) {
    const headers = signRequest(method, PATH_PREFIX + path.split('?')[0]);
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
    let r;
    try { r = await authed('POST', '/portfolio/events/orders', order); }
    catch (e) { return { kind: 'unknown', order, error: 'no response (' + String(e && e.name === 'AbortError' ? 'timeout' : (e && e.message) || e) + '): the order may or may not exist' }; }
    if (!r.ok) {
      if (/market_not_found/.test(r.text)) return { kind: 'route-miss', order, status: r.status, error: r.text };
      return { kind: 'rejected', order, status: r.status, error: r.text };
    }
    const p = parseOrderResult(r.json);
    return { kind: p.filled > 0 ? 'filled' : 'nofill', order, ...p };
  }

  async function exchangeStatus() {
    try {
      const r = await fetchImpl(BASE + '/exchange/status', { signal: AbortSignal.timeout(timeoutMs) });
      const j = await r.json();
      return { ok: r.ok, tradingActive: !!(j && j.trading_active), exchangeActive: !!(j && j.exchange_active) };
    } catch (e) { return { ok: false, error: String(e && e.message || e) }; }
  }
  async function positions() { try { const r = await authed('GET', '/portfolio/positions'); return r.ok ? r.json : { error: r.status + ' ' + r.text }; } catch (e) { return { error: String(e && e.message || e) }; } }
  async function balance() { try { const r = await authed('GET', '/portfolio/balance'); return r.ok ? r.json : { error: r.status + ' ' + r.text }; } catch (e) { return { error: String(e && e.message || e) }; } }
  async function marketResult(ticker) {
    try {
      const r = await fetchImpl(BASE + '/markets/' + encodeURIComponent(ticker), { signal: AbortSignal.timeout(timeoutMs) });
      const j = await r.json(); const m = j && (j.market || j);
      const res = m && String(m.result || '').toLowerCase();
      const ev = Number(String(m && m.expiration_value || '').replace(/,/g, ''));
      return (res === 'yes' || res === 'no') ? { result: res, official: Number.isFinite(ev) ? ev : null } : null;
    } catch (_) { return null; }
  }
  return { ready, signRequest, authed, buildBuyOrder, parseOrderResult, placeBuy, exchangeStatus, positions, balance, marketResult, PATH_PREFIX };
}

/* Kalshi taker fee for one order of C contracts at price p (cents): ceil(0.07 * C * P * (1 - P)) dollars, to the cent */
function kalshiFeeUsd(pCents, C, rate = 0.07) {
  const P = pCents / 100;
  return Math.ceil(rate * C * P * (1 - P) * 100 - 1e-9) / 100;
}

module.exports = { mkKalshi, kalshiFeeUsd };
