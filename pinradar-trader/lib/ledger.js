/* Append-only, hash-chained JSONL ledger: every line carries the SHA-256 of the previous line, so an edited or deleted
   line is detectable (/ledger/verify). Best effort on disk (Render's disk is ephemeral unless a persistent disk is attached);
   the last 2,000 records are also kept in memory; restore reads the whole file (all()). A failed write is kept in state.err, and the
   trader treats it as a halt reason. */
'use strict';
const fs = require('fs');
const crypto = require('crypto');

function mkLedger(file) {
  const L = { file, mem: [], last: 'GENESIS', n: 0, err: null, queue: [], lastOk: true };
  if (file) {
    try {
      if (fs.existsSync(file)) {
        const raw = fs.readFileSync(file, 'utf8');
        if (raw.length && !raw.endsWith('\n')) fs.appendFileSync(file, '\n');      // a torn last write: keep it visible, start a clean line
        const lines = raw.split('\n').filter(Boolean);
        for (const l of lines.slice(-2000)) { try { L.mem.push(JSON.parse(l)); } catch (_) { } }
        if (lines.length) { L.last = crypto.createHash('sha256').update(lines[lines.length - 1]).digest('hex'); L.n = lines.length; }
      }
    } catch (e) { L.err = String(e.message || e); }
  }
  /* the chain advances in memory; lines that could not be written are queued and retried, in order, before the next record
     (state.err is set while anything is queued and clears once the queue is written) */
  function flush() {
    if (!L.file || !L.queue.length) return true;
    try { fs.appendFileSync(L.file, L.queue.join('\n') + '\n'); L.queue = []; L.err = null; return true; }
    catch (e) { L.err = String(e.message || e); return false; }
  }
  function append(rec) {
    const row = { seq: L.n + 1, ts: Date.now(), prev: L.last, ...rec };
    const line = JSON.stringify(row);
    L.last = crypto.createHash('sha256').update(line).digest('hex'); L.n++;
    L.mem.push(row); if (L.mem.length > 2000) L.mem.shift();
    if (L.file) { L.queue.push(line); L.lastOk = flush(); }
    return row;
  }
  function verify() {
    if (!L.file || !fs.existsSync(L.file)) return { ok: null, note: 'no ledger file (in-memory only)' };
    const lines = fs.readFileSync(L.file, 'utf8').split('\n').filter(Boolean);
    let prev = 'GENESIS';
    for (let i = 0; i < lines.length; i++) {
      let r; try { r = JSON.parse(lines[i]); } catch (_) { return { ok: false, badLine: i + 1, why: 'not JSON' }; }
      if (r.prev !== prev) return { ok: false, badLine: i + 1, why: 'chain broken' };
      prev = crypto.createHash('sha256').update(lines[i]).digest('hex');
    }
    return { ok: true, lines: lines.length, head: prev };
  }
  /* every record, from the file when there is one (restore must see halts and positions older than the in-memory tail) */
  function all() {
    if (!L.file || !fs.existsSync(L.file)) return L.mem.slice();
    let raw; try { raw = fs.readFileSync(L.file, 'utf8'); } catch (e) { L.err = String(e.message || e); return L.mem.slice(); }
    const out = [];
    for (const l of raw.split('\n')) { if (!l) continue; try { out.push(JSON.parse(l)); } catch (_) { } }
    return out;
  }
  return { append, flush, verify, all, tail: n => L.mem.slice(-n), state: L };
}
module.exports = { mkLedger };
