/* =====================================================================
   BTC LIVE TRADER v4.15 — F26 strike-poison guard (2026-08-09)
   v4.15 CHANGES:
     F26 STRIKE-POISON GUARD (parseStrike): when Kalshi omits floor_strike/
        cap_strike/strike, the old fallback trusted the ticker suffix — but for
        KXBTC15M the suffix (…-15/-30/-45/-00) is a MINUTE/BUCKET code, not a
        dollar strike. That yielded strike~45 -> settle margin~64900 (the F25
        poison) AND fair pinned ~1.0 (phantom edges, saved last session only by
        GAP_MAX). Now: tail strikes below STRIKE_SANE_MIN ($1000) are rejected
        (returns NaN); the Number.isFinite(mkt.strike) guard in tick() drops the
        window cleanly instead of trading/observing off a garbage strike.
   ---------------------------------------------------------------------
   v4.2 CHANGES: F13 VOL CEILING (VOL_MAX_ENTER=0.45); F14 DRIFT-TRUST CEILING.
   v4.1 CHANGES: F8 vol FLOOR; F9 drift-oppose; F10 NaN hardening; F12 regime.
   Zero dependencies. Start Command: node live-trader-4.15.js
   Endpoints: /health /selftest /status /report /log /halt?on=1|0 /live /livecheck /radar
   ===================================================================== */
'use strict';
const http = require('http');
const fs = require('fs');
const { URL } = require('url');
const crypto = require('crypto');

const PORT = Number(process.env.PORT || 10000);
const VERSION = 'live-trader-4.16';
const KALSHI_BASE = (process.env.KALSHI_BASE || 'https://api.elections.kalshi.com/trade-api/v2').replace(/\/+$/,'');
const LOG_PATH = process.env.LOG_PATH || '/tmp/shadow_trades.jsonl';
const STRIKE_SANE_MIN = Number(process.env.STRIKE_SANE_MIN ?? 1000); // v4.15 F26: min plausible BTC $ strike; tail-parsed strikes below this are rejected

/* ------------------------------ config ------------------------------ */
const CFG = {
  CONTRACTS: Number(process.env.CONTRACTS || 10),
  DAILY_LOSS_LIMIT: Number(process.env.DAILY_LOSS_LIMIT || 200),
  MAX_CONSEC_LOSSES: Number(process.env.MAX_CONSEC_LOSSES || 4),
  EDGE_MIN_TAKER: Number(process.env.EDGE_MIN_TAKER || 0.06),
  EDGE_MIN_TAKER_HV: Number(process.env.EDGE_MIN_TAKER_HV || 0.10),
  MAKER_EDGE_MIN: Number(process.env.MAKER_EDGE_MIN || 0.08),
  MAKER_WINDOW_S: Number(process.env.MAKER_WINDOW_S || 180),
  SENT_VETO: Number(process.env.SENT_VETO || 40),
  EXIT_SENT: Number(process.env.EXIT_SENT || 30),
  EXIT_FAIR_DROP: Number(process.env.EXIT_FAIR_DROP || 0.25),
  TAKER_FEE_K: Number(process.env.TAKER_FEE_K || 0.07),
  MAKER_FEE: Number(process.env.MAKER_FEE || 0.003),
  MIN_TAU_ENTER: Number(process.env.MIN_TAU_ENTER || 8),
  MAX_TAU_ENTER: Number(process.env.MAX_TAU_ENTER || 600),
  TRADE_ALL_HOURS: !/^(1|true|yes)$/i.test(process.env.PRIME_ONLY||''),
  FAIR_MIN_HI: Number(process.env.FAIR_MIN_HI || 0.85),
  FAIR_MAX_LO: Number(process.env.FAIR_MAX_LO || 0),
  FILTER_ON: !/^(0|false|no)$/i.test(process.env.FILTER_ON||''),
  LIVE: /^(1|true|yes)$/i.test(process.env.LIVE||''),
  KALSHI_KEY_ID: process.env.KALSHI_KEY_ID||'',
  KALSHI_PRIVATE_KEY: (process.env.KALSHI_PRIVATE_KEY||'').replace(/\\n/g,'\n'),
  LIVE_DAILY_LOSS: Number(process.env.LIVE_DAILY_LOSS || 100),
  LIVE_MAX_CONTRACTS: Number(process.env.LIVE_MAX_CONTRACTS || 50),
  CAL_A: Number(process.env.CAL_A ?? -0.200),
  CAL_B: Number(process.env.CAL_B ?? 1.176),
  CAL_ON: !/^(0|false|no)$/i.test(process.env.CAL_ON||''),
  RADAR_URL: process.env.RADAR_URL||'',
  MIN_CUSHION_SIGMA: Number(process.env.MIN_CUSHION_SIGMA || 1.0),
  FAIR_STABLE_N: Number(process.env.FAIR_STABLE_N || 3),
  TREND_BPS: Number(process.env.TREND_BPS || 0.15),
  REVERSAL_HOLD_S: Number(process.env.REVERSAL_HOLD_S || 12),
  TAIL_TAU: Number(process.env.TAIL_TAU || 45),
  TAIL_SIGMA: Number(process.env.TAIL_SIGMA || 1.5),
  TAIL_EDGE: Number(process.env.TAIL_EDGE || 0.03),
  COOLDOWN_S: Number(process.env.COOLDOWN_S || 120),
  COOLDOWN_SIGMA: Number(process.env.COOLDOWN_SIGMA || 2.0),
  RISK_DOLLARS: Number(process.env.RISK_DOLLARS || 0),
  SETTLE_METRIC: (process.env.SETTLE_METRIC || 'avg60'),
  SKIP_SESSIONS: String(process.env.SKIP_SESSIONS ?? 'midday'),
  NEAR_STRIKE_USD: Number(process.env.NEAR_STRIKE_USD || 15),
  MIN_ENTRY_PX: Number(process.env.MIN_ENTRY_PX ?? 0.55),
  MAX_ENTRY_PX: Number(process.env.MAX_ENTRY_PX ?? 0.78),
  VOL_SKIP_LO: Number(process.env.VOL_SKIP_LO ?? 0.35),
  VOL_SKIP_HI: Number(process.env.VOL_SKIP_HI ?? 0.38),
  VOL_SKIP2_LO: Number(process.env.VOL_SKIP2_LO ?? 0.50),
  VOL_SKIP2_HI: Number(process.env.VOL_SKIP2_HI ?? 0.60),
  VOL_MIN_ENTER: Number(process.env.VOL_MIN_ENTER ?? 0.15),
  VOL_MAX_ENTER: Number(process.env.VOL_MAX_ENTER ?? 0.45),
  VOL_DRIFT_TRUST: Number(process.env.VOL_DRIFT_TRUST ?? 0.35),
  LATE_EXIT_ON: Number(process.env.LATE_EXIT_ON ?? 0),
  LATE_EXIT_TAU: Number(process.env.LATE_EXIT_TAU ?? 20),
  LATE_EXIT_MIN_TAU: Number(process.env.LATE_EXIT_MIN_TAU ?? 3),
  LATE_EXIT_K: Number(process.env.LATE_EXIT_K ?? 2.0),
  LATE_EXIT_MIN_SALVAGE: Number(process.env.LATE_EXIT_MIN_SALVAGE ?? 0.03),
  GAP_MIN: Number(process.env.GAP_MIN ?? 0.12),
  GAP_MAX: Number(process.env.GAP_MAX ?? 0.20),
  DRIFT_OPPOSE_MIN: Number(process.env.DRIFT_OPPOSE_MIN ?? 0.02),
  BASIS_ON: Number(process.env.BASIS_ON ?? 1),
  BASIS_LOOKBACK: Number(process.env.BASIS_LOOKBACK ?? 20),
  BASIS_MANUAL: Number(process.env.BASIS_MANUAL ?? 0),
  BASIS_HAIRCUT_K: Number(process.env.BASIS_HAIRCUT_K ?? 0.5),
  YES_ON: Number(process.env.YES_ON ?? 1),
  YES_AF_MIN: Number(process.env.YES_AF_MIN ?? 0),
  YES_AF_N: Number(process.env.YES_AF_N ?? 10),
  NO_AF_MAX: Number(process.env.NO_AF_MAX ?? 1),
  NO_DRIFT_MAX: Number(process.env.NO_DRIFT_MAX ?? 99),
  REV_VIOLENCE_MAX: Number(process.env.REV_VIOLENCE_MAX ?? 999),
  REV_N: Number(process.env.REV_N ?? 10),
  REGIME_WARMUP: Number(process.env.REGIME_WARMUP ?? 1),
  MIN_TAU_TRADE: Number(process.env.MIN_TAU_TRADE ?? 0),
  REGIME_ON: Number(process.env.REGIME_ON ?? 1),
  REGIME_LOOKBACK: Number(process.env.REGIME_LOOKBACK ?? 5),
  REGIME_MARGIN_MAX: Number(process.env.REGIME_MARGIN_MAX ?? 45),
  REGIME_MARGIN_PCT: Number(process.env.REGIME_MARGIN_PCT ?? 0), // v4.16: 0=off (use fixed $ REGIME_MARGIN_MAX). >0 = threshold as a FRACTION of BTC price (e.g. 0.0015 = 0.15%), so the violent-tape gate scales with price/vol instead of a fixed dollar amount that trips ~63% of the time and worsens as BTC rises.
  REGIME_MARGIN_SANE: Number(process.env.REGIME_MARGIN_SANE ?? 2000),
  REGIME_TREND_OVERRIDE: Number(process.env.REGIME_TREND_OVERRIDE ?? 0), // v4.16 F28: 0=off (identical to 4.15). 1=ride clean aligned trends through regime stand-down.
  REGIME_TREND_CONSIST: Number(process.env.REGIME_TREND_CONSIST ?? 0.5), // v4.16 F28: min |sum(recentMargins)|/sum(|margins|) to call it a clean trend (1=pure trend, 0=chop)
  JUMP_ON: Number(process.env.JUMP_ON ?? 0),        // v4.16 F29: 0=off (pure Gaussian, identical to 4.15). 1=jump-diffusion tail on the settlement prob.
  JUMP_LAMBDA: Number(process.env.JUMP_LAMBDA ?? 0.15), // F29: probability weight on the fat-jump regime
  JUMP_K: Number(process.env.JUMP_K ?? 4),          // F29: jump-regime std as a multiple of diffusion std (fatter tail => less near-strike overconfidence)
  MAKER_FIRST: Number(process.env.MAKER_FIRST ?? 0),      // v4.16 F30: 0=off (taker-primary, identical to 4.15). 1=rest a bid inside the touch, taker fallback.
  MAKER_UNDERCUT: Number(process.env.MAKER_UNDERCUT ?? 0.01), // F30: cents better than the taker ask to rest the maker bid
  MAKER_WAIT_S: Number(process.env.MAKER_WAIT_S ?? 45),   // F30: seconds to rest before falling back to taker
  FAIR_ANCHOR_ON: Number(process.env.FAIR_ANCHOR_ON ?? 0), // v4.16 F31: 0=off (report model fair, 4.15 behavior). 1=anchor reported confidence to the calibrated Kalshi market price.
  FAIR_ANCHOR_K: Number(process.env.FAIR_ANCHOR_K ?? 0.3), // F31: model weight vs market. 0=pure market price (best-calibrated, Brier 0.167); 1=pure model (overconfident, Brier 0.53).
  FAIR_ANCHOR_MIN: Number(process.env.FAIR_ANCHOR_MIN ?? 0.68), // v4.16 F31: conviction floor on the ANCHORED (honest) scale, used in place of FAIR_MIN_HI when FAIR_ANCHOR_ON=1.
  PRIME_START: process.env.PRIME_START || '05:30',
  PRIME_END: process.env.PRIME_END || '09:00',
  HV_START: process.env.HV_START || '05:45',
  HV_END: process.env.HV_END || '06:30',
};

/* ----------------------------- helpers ----------------------------- */
function clamp(x,lo,hi){const n=Number(x);return Number.isFinite(n)?Math.max(lo,Math.min(hi,n)):lo;}
function round(x,d=4){const n=Number(x);return Number.isFinite(n)?Number(n.toFixed(d)):null;}
function erf(x){const s=x<0?-1:1;x=Math.abs(x);const t=1/(1+0.3275911*x);const y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*Math.exp(-x*x);return s*y;}
function normCdf(x){return 0.5*(1+erf(x/Math.SQRT2));}
// v4.16 F29 JUMP-DIFFUSION TAIL: BTC 15-min moves are leptokurtic (fat-tailed / jumpy). A pure Gaussian
// underprices a late strike-cross, so the model is OVERCONFIDENT near the strike — exactly where 56% of
// losses settle (measured). Model a mixture: with prob (1-lam) normal diffusion (std sigma), with prob lam
// a fat-jump regime (std JUMP_K*sigma). survFn(z) = P(price ends on the winning side | cushion z sigmas).
// JUMP_ON=0 => pure normCdf => byte-identical to 4.15. When on, near-strike conviction drops (declines the
// squeakers) while deep-cushion conviction is nearly unchanged (keeps the winners).
function survFn(z){
  if(!CFG.JUMP_ON) return normCdf(z);
  const lam=clamp(CFG.JUMP_LAMBDA,0,1), Kj=Math.max(1.0001,CFG.JUMP_K);
  return (1-lam)*normCdf(z) + lam*normCdf(z/Kj);
}
function cors(res){res.setHeader('Access-Control-Allow-Origin','*');res.setHeader('Access-Control-Allow-Methods','GET,POST,OPTIONS');res.setHeader('Access-Control-Allow-Headers','Content-Type');res.setHeader('Cache-Control','no-store');}
function send(res,code,obj){cors(res);res.statusCode=code;res.setHeader('Content-Type','application/json; charset=utf-8');res.end(JSON.stringify(obj));}
async function fetchJson(url,timeoutMs=3500){
  const ac=new AbortController();const t=setTimeout(()=>{try{ac.abort();}catch(_){}} ,timeoutMs);
  try{const r=await fetch(url,{signal:ac.signal,headers:{accept:'application/json'}});
    if(!r.ok)throw new Error('HTTP '+r.status);return await r.json();}
  finally{clearTimeout(t);}
}
function ptClock(){
  try{
    const p=new Intl.DateTimeFormat('en-US',{timeZone:'America/Los_Angeles',hour12:false,hour:'2-digit',minute:'2-digit'}).formatToParts(new Date());
    const h=Number(p.find(x=>x.type==='hour').value), m=Number(p.find(x=>x.type==='minute').value);
    return h*60+m;
  }catch(_){return null;}
}
const hm=s=>{const[a,b]=String(s).split(':').map(Number);return a*60+b;};
function windowState(nowMin){
  if(nowMin===null)return{inPrime:true,inHV:false};
  const inPrime=nowMin>=hm(CFG.PRIME_START)&&nowMin<hm(CFG.PRIME_END);
  const inHV=nowMin>=hm(CFG.HV_START)&&nowMin<hm(CFG.HV_END);
  return {inPrime,inHV};
}
function sessionTag(nowMin){
  if(nowMin===null)return'unknown';
  if(nowMin<hm('05:30'))return'overnight';
  if(nowMin<hm('09:00'))return'prime';
  if(nowMin<hm('13:00'))return'midday';
  return'evening';
}
function sessionSkipped(tag){
  return CFG.SKIP_SESSIONS.split(',').map(s=>s.trim().toLowerCase()).filter(Boolean).includes(String(tag).toLowerCase());
}
function calFair(f){
  if(f===null||!Number.isFinite(f))return f;
  const hi=x=>Math.max(0.005,Math.min(0.995,CFG.CAL_B*x+CFG.CAL_A));
  return f>=0.5 ? hi(f) : 1-hi(1-f);
}
// v4.16 F31 MARKET-ANCHORED CONFIDENCE. The model's fair is badly overconfident (Brier 0.53: it says 0.95,
// wins 0.78). The Kalshi market price is nearly perfectly calibrated (Brier 0.167: px 0.75 -> wins ~0.75-0.80).
// So the TRUSTWORTHY confidence is the market price, not the model. anchoredFair pulls the model fair toward
// the market mid: a px-0.75 trade reports ~0.78 confidence, not a fake 0.95. FAIR_ANCHOR_ON=0 => returns the
// model fair unchanged (4.15 behavior). Used for the reported/gated confidence; the model still sets direction.
function marketMid(book){
  if(!book)return null;
  const yb=Number(book.yesBid), ya=Number(book.yesAsk);
  if(Number.isFinite(yb)&&Number.isFinite(ya))return (yb+ya)/2;
  if(Number.isFinite(ya))return ya; if(Number.isFinite(yb))return yb;
  return null;
}
function anchoredFair(modelFair, book){
  if(!CFG.FAIR_ANCHOR_ON || modelFair==null || !Number.isFinite(modelFair))return modelFair;
  const mid=marketMid(book);
  if(mid==null)return modelFair; // no market to anchor to -> fall back to model
  const K=clamp(CFG.FAIR_ANCHOR_K,0,1);
  return clamp(mid + K*(modelFair - mid), 0.005, 0.995);
}

/* --------------------- fees (Kalshi model) --------------------- */
function takerFee(price,qty){return CFG.TAKER_FEE_K*price*(1-price)*qty;}
function makerFee(qty){return CFG.MAKER_FEE*qty;}

/* --------------- BRTI proxy tape (Coinbase/Kraken/Bitstamp) --------------- */
const TAPE=[];
let lastTapeErr=null;
async function pollSpot(){
  const now=Date.now();
  const [cb,kr,bs]=await Promise.all([
    fetchJson('https://api.exchange.coinbase.com/products/BTC-USD/ticker').then(j=>Number(j.price)).catch(()=>null),
    fetchJson('https://api.kraken.com/0/public/Ticker?pair=XBTUSD').then(j=>{const k=Object.keys(j.result||{})[0];return k?Number(j.result[k].c[0]):null;}).catch(()=>null),
    fetchJson('https://www.bitstamp.net/api/v2/ticker/btcusd/').then(j=>Number(j.last)).catch(()=>null)
  ]);
  const vals=[cb,kr,bs].filter(v=>Number.isFinite(v)&&v>0).sort((a,b)=>a-b);
  if(!vals.length){lastTapeErr='no spot venue reachable';return;}
  const px=vals[Math.floor(vals.length/2)];
  TAPE.push([now,px]);
  const cut=now-20*60*1000; while(TAPE.length&&TAPE[0][0]<cut)TAPE.shift();
  lastTapeErr=null;
}
function tapeNow(){return TAPE.length?TAPE[TAPE.length-1][1]:null;}
function tapeVolBps(){
  const cut=Date.now()-300000; const w=TAPE.filter(t=>t[0]>=cut);
  if(w.length<10)return 0.45;
  const r=[]; for(let i=1;i<w.length;i++){const dt=Math.max(0.5,(w[i][0]-w[i-1][0])/1000);
    const v=(w[i][1]-w[i-1][1])/w[i-1][1]*1e4/Math.sqrt(dt); if(Number.isFinite(v))r.push(v);}
  if(r.length<5)return 0.45;
  const m=r.reduce((a,b)=>a+b,0)/r.length;
  return clamp(Math.sqrt(r.reduce((a,b)=>a+(b-m)*(b-m),0)/(r.length-1)),0.12,4);
}
function tapeDrift(){
  const cut=Date.now()-90000; const w=TAPE.filter(t=>t[0]>=cut);
  if(w.length<6)return 0;
  let num=0,den=0;const now=w[w.length-1][0];
  for(let i=1;i<w.length;i++){const dt=Math.max(0.5,(w[i][0]-w[i-1][0])/1000);
    const r=(w[i][1]-w[i-1][1])/w[i-1][1]*1e4/dt;const age=(now-w[i][0])/1000;const wt=Math.pow(0.5,age/25);
    if(Number.isFinite(r)){num+=wt*r;den+=wt;}}
  return den?clamp(num/den,-3,3):0;
}
function tapeLastAt(ts){
  for(let i=TAPE.length-1;i>=0;i--){if(TAPE[i][0]<=ts+1500)return TAPE[i][1];}
  return null;
}
function tapeAvg(fromTs,toTs){
  const w=TAPE.filter(t=>t[0]>=fromTs-3000&&t[0]<=toTs+1000);
  if(w.length<2)return null;
  let sum=0,dur=0;
  for(let i=1;i<w.length;i++){const dt=(w[i][0]-w[i-1][0])/1000;sum+=w[i-1][1]*dt;dur+=dt;}
  return dur>0?sum/dur:null;
}

/* --------------- upstream sentinel (Binance perp, compact) --------------- */
function ewmaZ(a){let m=null,v=null;return{update(x){if(m===null){m=x;v=1e-9;return 0;}const d=x-m;m+=a*d;v=(1-a)*(v+a*d*d);return d/Math.sqrt(Math.max(v,1e-9));}};}
const z2s=z=>clamp(z/3.5,-1,1)*100;
const SENT={started:false,lastOk:0,lastAggId:null,trades:[],depthHist:[],curDepth:{bid:0,ask:0},perpMid:null,spotMid:null,basisEwma:null,
  z:{div:ewmaZ(0.03),burst:ewmaZ(0.03),basis:ewmaZ(0.03)},read:{ok:false,error:'warming up',pressure:0}};
function sentCompute(){
  const now=Date.now();
  const cT=now-90000;while(SENT.trades.length&&SENT.trades[0][0]<cT)SENT.trades.shift();
  const cD=now-300000;while(SENT.depthHist.length&&SENT.depthHist[0][0]<cD)SENT.depthHist.shift();
  if(SENT.trades.length<10||SENT.depthHist.length<8||!Number.isFinite(SENT.perpMid))
    return{ok:false,error:'warming up',pressure:0};
  let net=0;for(const t of SENT.trades)net+=t[1];
  const p0=SENT.trades[0][2],p1=SENT.trades[SENT.trades.length-1][2];
  const div=net/1e6-((p1-p0)/p0)*20000;
  const cvdDiv=z2s(SENT.z.div.update(div));
  let b30=0;const c30=now-30000;
  for(let i=SENT.trades.length-1;i>=0&&SENT.trades[i][0]>=c30;i--)b30+=SENT.trades[i][1];
  const burst=z2s(SENT.z.burst.update(b30/1e6));
  const med=a=>{const b=[...a].sort((x,y)=>x-y);return b[Math.floor(b.length/2)]||1e-6;};
  const bidR=SENT.curDepth.bid/Math.max(med(SENT.depthHist.map(d=>d[1])),1e-6);
  const askR=SENT.curDepth.ask/Math.max(med(SENT.depthHist.map(d=>d[2])),1e-6);
  const pull=clamp((bidR-askR)*100,-100,100);
  let basisS=0;
  if(Number.isFinite(SENT.spotMid)){
    const basis=SENT.perpMid-SENT.spotMid;
    if(SENT.basisEwma===null)SENT.basisEwma=basis;
    SENT.basisEwma+=0.05*(basis-SENT.basisEwma);
    basisS=z2s(SENT.z.basis.update(basis-SENT.basisEwma));
  }
  const pressure=clamp(0.35*cvdDiv+0.20*burst+0.30*pull+0.15*basisS,-100,100);
  const stale=(now-SENT.lastOk)>12000;
  return{ok:!stale,error:stale?'stale':null,pressure:Math.round(pressure),
    components:{cvdDiv:Math.round(cvdDiv),burst:Math.round(burst),bookPull:Math.round(pull),basis:Math.round(basisS)}};
}
async function sentPoll(){
  const now=Date.now();
  let any=false;
  try{
    if((SENT.failN||0)<3){
      const aggUrl='https://fapi.binance.com/fapi/v1/aggTrades?symbol=BTCUSDT'+(SENT.lastAggId?('&fromId='+(SENT.lastAggId+1)+'&limit=500'):'&limit=300');
      const[trades,depth,pBT,sBT]=await Promise.all([
        fetchJson(aggUrl).catch(()=>null),
        fetchJson('https://fapi.binance.com/fapi/v1/depth?symbol=BTCUSDT&limit=10').catch(()=>null),
        fetchJson('https://fapi.binance.com/fapi/v1/ticker/bookTicker?symbol=BTCUSDT').catch(()=>null),
        fetchJson('https://api.binance.com/api/v3/ticker/bookTicker?symbol=BTCUSDT').catch(()=>null)
      ]);
      if(Array.isArray(trades)){for(const t of trades){const p=+t.p,q=+t.q;if(!Number.isFinite(p)||!Number.isFinite(q))continue;
        SENT.trades.push([+t.T||now,(t.m?-1:1)*p*q,p]);SENT.lastAggId=Math.max(SENT.lastAggId||0,+t.a||0);}any=true;}
      if(depth&&Array.isArray(depth.bids)){const s=x=>x.reduce((a,y)=>a+(+y[1]||0),0);
        SENT.curDepth={bid:s(depth.bids),ask:s(depth.asks)};SENT.depthHist.push([now,SENT.curDepth.bid,SENT.curDepth.ask]);any=true;}
      if(pBT&&pBT.bidPrice)SENT.perpMid=(+pBT.bidPrice+ +pBT.askPrice)/2;
      if(sBT&&sBT.bidPrice)SENT.spotMid=(+sBT.bidPrice+ +sBT.askPrice)/2;
      if(any){SENT.failN=0;SENT.venue='binance-perp';}
      else SENT.failN=(SENT.failN||0)+1;
    }
    if(!any&&(SENT.failN||0)>=3){
      if(SENT.venue!=='coinbase-spot'){SENT.lastAggId=null;SENT.trades.length=0;SENT.venue='coinbase-spot';}
      const[trades,book]=await Promise.all([
        fetchJson('https://api.exchange.coinbase.com/products/BTC-USD/trades?limit=100').catch(()=>null),
        fetchJson('https://api.exchange.coinbase.com/products/BTC-USD/book?level=2').catch(()=>null)
      ]);
      if(Array.isArray(trades)){
        for(const t of trades){const p=+t.price,q=+t.size,id=+t.trade_id;
          if(!Number.isFinite(p)||!Number.isFinite(q))continue;
          if(SENT.lastAggId&&Number.isFinite(id)&&id<=SENT.lastAggId)continue;
          const signed=(t.side==='sell'?1:-1)*p*q;
          SENT.trades.push([Date.parse(t.time)||now,signed,p]);
          if(Number.isFinite(id))SENT.lastAggId=Math.max(SENT.lastAggId||0,id);}
        any=true;
      }
      if(book&&Array.isArray(book.bids)&&Array.isArray(book.asks)){
        const bb=+((book.bids[0]||[])[0]),ba=+((book.asks[0]||[])[0]);
        if(Number.isFinite(bb)&&Number.isFinite(ba)){
          const mid=(bb+ba)/2,band=mid*0.0006;let bd=0,ad=0;
          for(const b of book.bids){const p=+b[0],sz=+b[1];if(mid-p<=band)bd+=sz;else break;}
          for(const a of book.asks){const p=+a[0],sz=+a[1];if(p-mid<=band)ad+=sz;else break;}
          SENT.curDepth={bid:bd,ask:ad};SENT.depthHist.push([now,bd,ad]);
          SENT.perpMid=mid;SENT.spotMid=mid;any=true;
        }
      }
    }
    if(any)SENT.lastOk=now;
  }catch(_){}
  SENT.read=sentCompute();
  if(SENT.read)SENT.read.venue=SENT.venue||null;
}
function ensureSentinel(){if(SENT.started)return;SENT.started=true;sentPoll();const t=setInterval(sentPoll,2500);if(t.unref)t.unref();}

/* --------------------- PIN RADAR OBSERVER (v3.4) --------------------- */
const RADAR={last:null,lastTs:0,err:null,fetches:0};
async function pollRadar(){
  if(!CFG.RADAR_URL)return;
  const ac=new AbortController();const t=setTimeout(()=>{try{ac.abort();}catch(_){}} ,3000);
  try{
    const r=await fetch(CFG.RADAR_URL,{signal:ac.signal});
    if(!r.ok)throw new Error('HTTP '+r.status);
    const j=await r.json();
    RADAR.last=j; RADAR.lastTs=Date.now(); RADAR.err=null; RADAR.fetches++;
  }catch(e){ RADAR.err=String(e.message||e); }
  finally{ clearTimeout(t); }
}
function radarSnapshot(){
  const j=RADAR.last;
  if(!j||Date.now()-RADAR.lastTs>20000)return {radarCvd:null,radarImb:null,radarSpotImb:null,radarAge:null};
  const dig=(o,keys)=>{for(const k of keys){if(o&&typeof o==='object'&&o[k]!==undefined&&o[k]!==null)return o[k];}return null;};
  const flat=(o,depth=0)=>{
    if(!o||typeof o!=='object'||depth>3)return {};
    let out={};
    for(const [k,v] of Object.entries(o)){
      if(v&&typeof v==='object')Object.assign(out,flat(v,depth+1));
      else out[k]=v;
    }
    return out;
  };
  const F=flat(j);
  return {
    radarCvd: dig(F,['cvd','spotCvd','cvd60','cvdDelta','netFlow']),
    radarImb: dig(F,['imbalance','bookImbalance','kalshiImbalance','imb']),
    radarSpotImb: dig(F,['flowImbalance','spotImbalance','spotImb','depthImbalance']),
    radarBidDepth: dig(F,['bidDepth']), radarAskDepth: dig(F,['askDepth']),
    radarAge: Math.round((Date.now()-RADAR.lastTs)/1000)
  };
}

/* --------------------- LIVE ORDER LAYER (v3.0) --------------------- */
const LIVE={enabled:false,lastFill:null,lastErr:null,orders:[],halted:null,realizedToday:0,day:null};
function liveReady(){ return !!(CFG.KALSHI_KEY_ID && CFG.KALSHI_PRIVATE_KEY); }
function liveRecord(pnl){
  liveHalted();
  if(!Number.isFinite(pnl))return;
  LIVE.realizedToday+=pnl;
}
function signRequest(method,path){
  const ts=Date.now().toString();
  const msg=ts+method.toUpperCase()+path;
  const sig=crypto.sign('sha256',Buffer.from(msg,'utf-8'),
    {key:CFG.KALSHI_PRIVATE_KEY,padding:crypto.constants.RSA_PKCS1_PSS_PADDING,saltLength:crypto.constants.RSA_PSS_SALTLEN_DIGEST});
  return {'KALSHI-ACCESS-KEY':CFG.KALSHI_KEY_ID,'KALSHI-ACCESS-TIMESTAMP':ts,
          'KALSHI-ACCESS-SIGNATURE':sig.toString('base64'),'Content-Type':'application/json'};
}
async function kalshiAuthed(method,path,body){
  const url=KALSHI_BASE+path;
  const headers=signRequest(method,'/trade-api/v2'+path);
  const ac=new AbortController();const t=setTimeout(()=>{try{ac.abort();}catch(_){}} ,6000);
  try{
    const r=await fetch(url,{method,headers,signal:ac.signal,body:body?JSON.stringify(body):undefined});
    const txt=await r.text();
    let j=null; try{j=JSON.parse(txt);}catch(_){}
    if(!r.ok)throw new Error('HTTP '+r.status+' '+txt.slice(0,200));
    return j;
  } finally{clearTimeout(t);}
}
function liveHalted(){
  const d=new Date().toISOString().slice(0,10);
  if(LIVE.day!==d){LIVE.day=d;LIVE.realizedToday=0;LIVE.halted=null;}
  if(LIVE.halted)return LIVE.halted;
  if(LIVE.realizedToday<=-Math.abs(CFG.LIVE_DAILY_LOSS))return 'live daily loss limit';
  return null;
}
async function placeLiveOrder(ticker,side,count,priceCents){
  const isYes = side==='yes';
  const px = isYes ? Math.min(0.99,(priceCents/100)+0.01)
                   : Math.max(0.01,(1 - priceCents/100)-0.01);
  const order={ticker,
    client_order_id:'bot-'+Date.now()+'-'+Math.floor(Math.random()*1e6),
    side: isYes ? 'bid' : 'ask',
    count: Number(count).toFixed(2),
    price: px.toFixed(4),
    time_in_force:'immediate_or_cancel',
    self_trade_prevention_type:'taker_at_cross',
    cancel_order_on_pause:false,
    post_only:false, reduce_only:false, subaccount:0, exchange_index:0};
  if(!CFG.LIVE){
    logLine({ev:'WOULD_PLACE',intent:{side,priceCents,count},v2Order:order,note:'DRY RUN — nothing sent'});
    return {dryRun:true,order};
  }
  const h=liveHalted();
  if(h){logLine({ev:'LIVE_BLOCKED',reason:h,ticker});return {blocked:h};}
  try{
    const res=await kalshiAuthed('POST','/portfolio/events/orders',order);
    const o=res&&(res.order||res);
    const filled=Number((o&&(o.fill_count!==undefined?o.fill_count:o.filled_count))||0);
    const remaining=Number((o&&o.remaining_count)||0);
    logLine({ev:filled>0?'LIVE_FILL':'LIVE_NOFILL',ticker,intentSide:side,v2Side:order.side,
      price:order.price,requested:order.count,filled:filled.toFixed(2),remaining:remaining.toFixed(2),
      orderId:o&&(o.order_id||o.id)});
    LIVE.lastFill={ticker,filled,requested:Number(order.count)};
    LIVE.orders.push({ticker,side,v2Side:order.side,price:order.price,count:order.count,ts:Date.now(),res:o});
    if(LIVE.orders.length>100)LIVE.orders.shift();
    return res;
  }catch(e){
    LIVE.lastErr=String(e.message||e);
    LIVE.halted='order error: '+LIVE.lastErr;
    logLine({ev:'LIVE_ERROR',ticker,err:LIVE.lastErr,halted:true});
    return {error:LIVE.lastErr};
  }
}
async function placeCloseOrder(pos, salvagePx){
  const isYes = pos.side==='YES';
  const order={ticker:pos.ticker,
    client_order_id:'close-'+Date.now()+'-'+Math.floor(Math.random()*1e6),
    side: isYes ? 'ask' : 'bid',
    count: Number(pos.qty).toFixed(2),
    price: Math.max(0.01,Math.min(0.99, isYes ? salvagePx : (1-salvagePx))).toFixed(4),
    time_in_force:'immediate_or_cancel',
    reduce_only:true, post_only:false, subaccount:0, exchange_index:0,
    self_trade_prevention_type:'taker_at_cross', cancel_order_on_pause:false};
  if(!CFG.LIVE){ logLine({ev:'WOULD_CLOSE',ticker:pos.ticker,intent:{side:pos.side,salvagePx,qty:pos.qty},v2Order:order,note:'DRY RUN'}); return {dryRun:true}; }
  try{
    const res=await kalshiAuthed('POST','/portfolio/events/orders',order);
    const oo=res&&(res.order||res);
    logLine({ev:'LIVE_CLOSE',ticker:pos.ticker,side:pos.side,price:order.price,qty:order.count,orderId:oo&&(oo.order_id||oo.id)});
    return res;
  }catch(e){ LIVE.lastErr=String(e.message||e); logLine({ev:'LIVE_CLOSE_ERROR',ticker:pos.ticker,err:LIVE.lastErr}); return {error:LIVE.lastErr}; }
}
async function fetchLivePositions(){
  try{ return await kalshiAuthed('GET','/portfolio/positions'); }
  catch(e){ LIVE.lastErr=String(e.message||e); return null; }
}

/* --------------------- Kalshi market discovery --------------------- */
let mktCache={t:0,data:null};
const DISC={ts:0,err:null,totalMarkets:0,btcCount:0,nearestCloseSec:null,picked:null};
function parseStrike(m){
  if(!m||typeof m!=='object')return NaN; // v4.15 F26: null/garbage market object can't throw in the poll loop
  for(const c of[m.floor_strike,m.cap_strike,m.strike]){const n=Number(c);if(Number.isFinite(n)&&n>0)return n;}
  // v4.15 F26 STRIKE-POISON GUARD: the KXBTC15M ticker suffix is a minute/bucket code (…-15/-30/-45/-00),
  // NOT a dollar strike. The old fallback trusted it -> strike~45 -> settle margin~64900 (the F25 poison)
  // AND fair pinned ~1.0 (phantom edges). Real BTC strikes are tens of thousands; reject any tail value
  // below STRIKE_SANE_MIN so the window is skipped cleanly (Number.isFinite(mkt.strike) guard in tick())
  // instead of trading/observing off a garbage strike. Legit tail-encoded strikes (>=$1000) still parse.
  const tail=String(m.ticker||'').split('-').pop()||'';const n=Number(tail.replace(/[^0-9.]/g,''));
  return (Number.isFinite(n)&&n>=STRIKE_SANE_MIN)?n:NaN;
}
function closeMs(m){
  const s=Number(m.close_ts);if(Number.isFinite(s)&&s>0)return s*1000;
  for(const f of[m.close_time,m.expected_expiration_time,m.expiration_time]){
    const t=Date.parse(f||'');if(Number.isFinite(t))return t;}
  return 0;
}
async function discoverMarket(refPrice){
  const now=Date.now();
  const cacheMs=(DISC.err&&/429/.test(DISC.err))?25000:8000;
  if(mktCache.data&&now-mktCache.t<cacheMs)return mktCache.data;
  if(!mktCache.data&&now-mktCache.t<cacheMs&&mktCache.t>0)return null;
  const s=Math.floor(now/1000);
  let j=await fetchJson(KALSHI_BASE+'/markets?series_ticker=KXBTC15M&status=open&limit=20')
    .catch(e=>({__err:String((e&&e.message)||e)}));
  let via='series';
  if(!j||j.__err||!Array.isArray(j.markets)||!j.markets.length){
    const firstErr=j&&j.__err?j.__err:null;
    j=await fetchJson(KALSHI_BASE+'/markets?status=open&limit=200&min_close_ts='+s+'&max_close_ts='+(s+16*60))
      .catch(e=>({__err:String((e&&e.message)||e)}));
    via='broad'+(firstErr?(' (series: '+firstErr+')'):'');
  }
  DISC.ts=now;
  DISC.via=via;
  DISC.err=j&&j.__err?j.__err:(j?null:'null response');
  const all=Array.isArray(j&&j.markets)?j.markets:[];
  DISC.totalMarkets=all.length;
  // BUG6 fix: require the exact KXBTC15M series on the TICKER (not a loose /BTC/ text match on title),
  // so a broad fallback can never select a different BTC product with a different settlement rule.
  const btc=all.filter(m=>/^KXBTC15M/.test(String(m.ticker||'')))
    .map(m=>({m,c:closeMs(m)})).filter(x=>x.c>now+3000);
  DISC.btcCount=btc.length;
  DISC.nearestCloseSec=btc.length?Math.round((Math.min(...btc.map(x=>x.c))-now)/1000):null;
  if(!btc.length){DISC.picked=null;mktCache={t:now,data:null};return null;}
  btc.sort((a,b)=>a.c-b.c);
  const firstClose=btc[0].c;
  let win=btc.filter(x=>x.c===firstClose).map(x=>x.m);
  if(!win.length){mktCache={t:now,data:null};return null;}
  if(Number.isFinite(refPrice))win.sort((a,b)=>Math.abs(parseStrike(a)-refPrice)-Math.abs(parseStrike(b)-refPrice));
  const m=win[0];
  const c2=v=>{const n=Number(v);return Number.isFinite(n)&&n>0&&n<100?n/100:null;};
  const data={ticker:m.ticker,strike:parseStrike(m),closeTs:firstClose,title:m.title||'',
    quotes:{yesBid:c2(m.yes_bid),yesAsk:c2(m.yes_ask),noBid:c2(m.no_bid),noAsk:c2(m.no_ask)}};
  DISC.picked=data.ticker;
  mktCache={t:now,data};return data;
}
let obCache={t:0,ticker:'',data:null};
function normalizeBook(j){
  const fp=j&&j.orderbook_fp, legacy=j&&j.orderbook;
  const src=fp||legacy; if(!src)return null;
  const norm=a=>(Array.isArray(a)?a:[]).filter(x=>Array.isArray(x)&&x.length>=2)
    .map(x=>[Number(x[0])/(fp?1:100),Number(x[1])])
    .filter(x=>Number.isFinite(x[0])&&x[0]>0&&x[0]<1&&Number.isFinite(x[1]));
  return {yes:norm(fp?src.yes_dollars:src.yes), no:norm(fp?src.no_dollars:src.no)};
}
async function getBook(ticker,fallbackQuotes){
  const now=Date.now();
  if(obCache.data&&obCache.ticker===ticker&&now-obCache.t<1500)return obCache.data;
  const j=await fetchJson(KALSHI_BASE+'/markets/'+encodeURIComponent(ticker)+'/orderbook?depth=10').catch(()=>null);
  const nb=normalizeBook(j);
  const yes=nb?nb.yes:[], no=nb?nb.no:[];
  const bestYesBid=yes.length?Math.max(...yes.map(x=>x[0])):null;
  const bestNoBid=no.length?Math.max(...no.map(x=>x[0])):null;
  let data={yesBid:bestYesBid, yesAsk:bestNoBid!==null?round(1-bestNoBid,2):null,
    noBid:bestNoBid, noAsk:bestYesBid!==null?round(1-bestYesBid,2):null,
    yesDepth:yes.reduce((a,x)=>a+x[1],0), noDepth:no.reduce((a,x)=>a+x[1],0), source:'orderbook'};
  const empty=data.yesBid===null&&data.yesAsk===null&&data.noBid===null;
  if(empty&&fallbackQuotes&&(fallbackQuotes.yesBid!==null||fallbackQuotes.yesAsk!==null)){
    data={yesBid:fallbackQuotes.yesBid,yesAsk:fallbackQuotes.yesAsk,
      noBid:fallbackQuotes.noBid,noAsk:fallbackQuotes.noAsk,yesDepth:0,noDepth:0,source:'listing'};
  }else if(empty){data.source='none';}
  obCache={t:now,ticker,data};return data;
}

/* --------------------- fair value engine (E1 core) --------------------- */
function computeFair(o){
  const {price,strike,tauSec,volBps,driftBps,knownAvg,knownDur}=o;
  if(!Number.isFinite(price)||!Number.isFinite(strike))return null;
  const sigUsdPerSqrtSec=(volBps/1e4)*price;
  const driftUsdPerSec=(driftBps/1e4)*price;
  let mean,sd;
  if(tauSec>60){
    const h=(tauSec-60)+20;
    mean=price+driftUsdPerSec*Math.min(tauSec,120)*0.5;
    sd=Math.max(1e-6,sigUsdPerSqrtSec*Math.sqrt(h));
    return clamp(1-survFn((strike-mean)/sd),0.005,0.995);
  }
  const r=Math.max(0.5,tauSec);
  const e=clamp(Number.isFinite(knownDur)?knownDur:60-r,0,60-r+0.01)||Math.max(0,60-r);
  const kAvg=Number.isFinite(knownAvg)?knownAvg:price;
  const sumKnown=kAvg*e;
  const reqFutureMean=(60*strike-sumKnown)/r;
  mean=price+driftUsdPerSec*r*0.5;
  sd=Math.max(1e-6,sigUsdPerSqrtSec*Math.sqrt(r/3));
  return clamp(1-survFn((reqFutureMean-mean)/sd),0.001,0.999);
}

/* --------------------- decision engine (E2-E4) --------------------- */
function decideEntry(o){
  const {fair,book,tauSec,inHV,sentPressure,haveOpen,ticker,lockout}=o;
  if(!haveOpen && regimeViolent(o.price)){
    // v4.16 F28 TREND-ALIGNED OVERRIDE: the regime gate keys on mean |settle margin|, which cannot
    // distinguish a clean one-directional TREND (safe — ride it) from choppy WHIPSAW (dangerous) —
    // both inflate |margin|. When the tape is a clean trend AND the bot's lean agrees with it AND
    // conviction is high, ride it instead of standing down. Chop, counter-trend leans, and low
    // conviction still stand down. Default OFF (REGIME_TREND_OVERRIDE=0) => identical to 4.15.
    let rideTrend=false, rt=null;
    if(CFG.REGIME_TREND_OVERRIDE && Number.isFinite(fair)){
      rt=regimeTrend();
      if(rt){
        const leanSign = fair>=0.5 ? 1 : -1;
        const highConv = fair>=CFG.FAIR_MIN_HI || fair<=(1-CFG.FAIR_MIN_HI);
        rideTrend = rt.consistency>=CFG.REGIME_TREND_CONSIST && leanSign===rt.trendSign && highConv;
      }
    }
    if(!rideTrend)
      return{action:'NONE',reason:'regime stand-down: recent mean |settle margin| '+round(regimeMean(),0)+' > '+round(regimeThreshold(o.price),0)+(CFG.REGIME_MARGIN_PCT>0?' ('+(CFG.REGIME_MARGIN_PCT*100).toFixed(2)+'% of price)':' (fixed)')+' (violent tape)'+(CFG.REGIME_TREND_OVERRIDE&&rt?(' [F28: consist '+round(rt.consistency,2)+' trend '+(rt.trendSign>0?'+':'-')+' — not a clean aligned high-conviction trend]'):'')};
    // else: clean trend the bot agrees with — fall through and evaluate the normal entry gates (F28)
  }
  if(!haveOpen && CFG.REGIME_ON && CFG.REGIME_WARMUP && !regimeWarm())
    return{action:'NONE',reason:'regime warmup: only '+STATE.recentMargins.length+'/'+CFG.REGIME_LOOKBACK+' settles buffered — F12/F22 blind after restart, standing down (F23)'};
  if(haveOpen)return{action:'NONE',reason:'position open'};
  if(!haveOpen && CFG.REV_VIOLENCE_MAX<999 && Number.isFinite(o.entryViolence) && o.entryViolence>=CFG.REV_VIOLENCE_MAX)
    return{action:'NONE',reason:'reversal filter: tape violence '+round(o.entryViolence,0)+' >= '+CFG.REV_VIOLENCE_MAX+' (last '+CFG.REV_N+' settles) — overreaction regime, reversal-prone (F22)'};
  if(!book||fair===null)return{action:'NONE',reason:'no data'};
  if(tauSec<CFG.MIN_TAU_ENTER)return{action:'NONE',reason:'too close to expiry'};
  if(CFG.MIN_TAU_TRADE>0 && tauSec<CFG.MIN_TAU_TRADE)
    return{action:'NONE',reason:'late entry: tau '+Math.round(tauSec)+'s < '+CFG.MIN_TAU_TRADE+'s — sub-window entries chase extended moves (tau<250 = -$0.67/tr) (F24)'};
  const cdActive = o.cooldownUntil && Date.now()<o.cooldownUntil;
  const cdSameWindow = cdActive && o.lockout && o.ticker && o.lockout.ticker===o.ticker;
  const locked=lockout&&ticker&&lockout.ticker===ticker;
  // v4.16 F31 fix: the conviction floor must match the scale of the value being gated. FAIR_MIN_HI (0.85)
  // is on the OVERCONFIDENT model-fair scale; when anchoring is on, conviction is on the honest market scale
  // (~0.68-0.84), so gate against FAIR_ANCHOR_MIN instead — otherwise anchoring silently blocks all volume.
  const convFloor = CFG.FAIR_ANCHOR_ON ? CFG.FAIR_ANCHOR_MIN : CFG.FAIR_MIN_HI;
  const inBand=v=>!CFG.FILTER_ON || v>=convFloor || v<=CFG.FAIR_MAX_LO;
  if(CFG.FILTER_ON && CFG.FAIR_STABLE_N>1 && typeof o.fairStreak==='number' && o.fairStreak<CFG.FAIR_STABLE_N)
    return{action:'NONE',reason:'fair not stable yet ('+o.fairStreak+'/'+CFG.FAIR_STABLE_N+' consecutive reads)'};
  let realCushionSigma=null, cushionSide=null;
  const basis = Number.isFinite(o.basis)?o.basis:0;
  if(o.price&&o.strike&&o.volBps&&tauSec>0){
    const sig=(o.volBps/1e4)*o.price*Math.sqrt(tauSec);
    const corrPrice=o.price-basis;
    realCushionSigma=(corrPrice-o.strike)/Math.max(sig,1e-9);
    cushionSide=realCushionSigma>=0?'YES':'NO';
  }
  const cushionOK=(side)=>{
    if(realCushionSigma===null)return true;
    let noExtra=0;
    if(CFG.BASIS_ON && CFG.BASIS_HAIRCUT_K>0 && basis<0 && o.volBps>0 && tauSec>0){
      const sig=(o.volBps/1e4)*o.price*Math.sqrt(tauSec);
      noExtra=CFG.BASIS_HAIRCUT_K*(Math.abs(basis)/Math.max(sig,1e-9));
    }
    return side==='YES' ? realCushionSigma>=CFG.MIN_CUSHION_SIGMA
                        : (-realCushionSigma)>=(CFG.MIN_CUSHION_SIGMA+noExtra);
  };
  const satYES = Number.isFinite(o.rawFair) && o.rawFair>=0.995;
  const satNO  = Number.isFinite(o.rawFair) && o.rawFair<=0.005;
  const volSkip = Number.isFinite(o.volBps) && (
      (CFG.VOL_SKIP_HI>CFG.VOL_SKIP_LO && o.volBps>=CFG.VOL_SKIP_LO && o.volBps<CFG.VOL_SKIP_HI) ||
      (CFG.VOL_SKIP2_HI>CFG.VOL_SKIP2_LO && o.volBps>=CFG.VOL_SKIP2_LO && o.volBps<CFG.VOL_SKIP2_HI));
  const volTooHot = CFG.VOL_MAX_ENTER>0 && Number.isFinite(o.volBps) && o.volBps>CFG.VOL_MAX_ENTER;
  const drift=(CFG.VOL_DRIFT_TRUST>0&&Number.isFinite(o.volBps)&&o.volBps>CFG.VOL_DRIFT_TRUST)?0:(o.driftBps||0);
  if(o.price&&o.strike&&o.volBps&&tauSec<=CFG.TAIL_TAU&&tauSec>=CFG.MIN_TAU_ENTER){
    const sig=(o.volBps/1e4)*o.price*Math.sqrt(tauSec);
    const cushion=(o.price-o.strike)/Math.max(sig,1e-9);
    if(Math.abs(cushion)>=CFG.TAIL_SIGMA){
      const afBlockTail=CFG.YES_AF_MIN>0&&Number.isFinite(o.aboveFrac)&&o.aboveFrac<CFG.YES_AF_MIN;
      if(CFG.YES_ON&&!afBlockTail&&cushion>0&&book.yesAsk>0&&book.yesAsk<0.99){
        const net=fair-book.yesAsk-takerFee(book.yesAsk,1);
        if(net>=CFG.TAIL_EDGE&&!(lockout&&o.ticker&&lockout.ticker===o.ticker&&lockout.side==='YES'))
          return{action:'BUY_YES',mode:'taker',px:book.yesAsk,fair,netEdge:round(net,3),reason:'tail-snipe YES: '+round(cushion,1)+' sigma past strike, tau '+round(tauSec,0)};
      }
      if(cushion<0&&book.noAsk>0&&book.noAsk<0.99){
        const net=(1-fair)-book.noAsk-takerFee(book.noAsk,1);
        if(net>=CFG.TAIL_EDGE&&!(lockout&&o.ticker&&lockout.ticker===o.ticker&&lockout.side==='NO'))
          return{action:'BUY_NO',mode:'taker',px:book.noAsk,fair,netEdge:round(net,3),reason:'tail-snipe NO: '+round(-cushion,1)+' sigma past strike, tau '+round(tauSec,0)};
      }
    }
  }
  const counterTrend=(side)=> Math.abs(drift)>=CFG.TREND_BPS && ((side==='YES'&&drift<=-CFG.TREND_BPS)||(side==='NO'&&drift>=CFG.TREND_BPS));
  const vetoAt=tauSec<=300?25:CFG.SENT_VETO;
  const edgeMin=inHV?CFG.EDGE_MIN_TAKER_HV:CFG.EDGE_MIN_TAKER;
  if(CFG.YES_AF_MIN>0&&Number.isFinite(o.aboveFrac)&&o.aboveFrac<CFG.YES_AF_MIN&&Number.isFinite(book.yesAsk)&&book.yesAsk>0.02&&book.yesAsk<0.98&&fair>0.5)
    return{action:'NONE',reason:'YES regime gate: above-frac '+round(o.aboveFrac,2)+' < '+CFG.YES_AF_MIN+' — recent settles bearish, YES base rate below breakeven (F20)'};
  if(CFG.YES_ON&&Number.isFinite(book.yesAsk)&&book.yesAsk>0.02&&book.yesAsk<0.98){
    const gross=fair-book.yesAsk;
    const net=gross-takerFee(book.yesAsk,1);
    if(counterTrend('YES')&&net<CFG.EDGE_MIN_TAKER_HV)return{action:'NONE',reason:'counter-trend YES needs edge >= '+CFG.EDGE_MIN_TAKER_HV+' (drift '+round(drift,3)+')'};
    if(net>=edgeMin){
      if(volSkip)return{action:'NONE',reason:'vol regime '+round(o.volBps,3)+' in skip band ['+CFG.VOL_SKIP_LO+','+CFG.VOL_SKIP_HI+') — model miscalibrated in transitional chop'};
      if(volTooHot)return{action:'NONE',reason:'hot tape '+round(o.volBps,3)+' > '+CFG.VOL_MAX_ENTER+' — drift is noise, side-selection unreliable (50% wr / -$1.87 above 0.45)'};
      if(CFG.GAP_MIN>0){const g=fair-book.yesAsk; if(g<CFG.GAP_MIN||g>=CFG.GAP_MAX)return{action:'NONE',reason:'gap '+round(g,3)+' outside edge band ['+CFG.GAP_MIN+','+CFG.GAP_MAX+'] — model-vs-market disagreement not in the 83%-wr zone (F17)'};}
      if(CFG.VOL_MIN_ENTER>0&&Number.isFinite(o.volBps)&&o.volBps<CFG.VOL_MIN_ENTER)return{action:'NONE',reason:'dead-calm tape '+round(o.volBps,3)+' < '+CFG.VOL_MIN_ENTER+' (70.6% wr / -$27 — model overconfident before a move)'};
      if(CFG.DRIFT_OPPOSE_MIN>0&&drift<=-CFG.DRIFT_OPPOSE_MIN)return{action:'NONE',reason:'YES opposes drift '+round(drift,3)+' (|d|>='+CFG.DRIFT_OPPOSE_MIN+') — against-flow lost -$33 on 47 trades'};
      if(book.yesAsk<CFG.MIN_ENTRY_PX||book.yesAsk>CFG.MAX_ENTRY_PX)return{action:'NONE',reason:'entry px '+book.yesAsk+' outside edge band ['+CFG.MIN_ENTRY_PX+','+CFG.MAX_ENTRY_PX+']'};
      if(!cushionOK('YES'))return{action:'NONE',reason:'real cushion only '+round(realCushionSigma,2)+' sigma (need '+CFG.MIN_CUSHION_SIGMA+') — fair is drift-manufactured'};
      if(locked&&lockout.side==='YES')return{action:'NONE',reason:'reversal lockout (YES) this window'};
      if(cdSameWindow&&o.lockout.side==='YES')return{action:'NONE',reason:'cooldown same-side YES ('+Math.ceil((o.cooldownUntil-Date.now())/1000)+'s)'};
      if(!inBand(anchoredFair(fair,book)))return{action:'NONE',reason:'conviction '+round(anchoredFair(fair,book),3)+(CFG.FAIR_ANCHOR_ON?' (market-anchored)':'')+' outside trade band ['+CFG.FAIR_MAX_LO+','+convFloor+']'};
      if(sentPressure<=-vetoAt)return{action:'NONE',reason:'YES edge but perp pressure down (veto @'+vetoAt+')'};
      return{action:'BUY_YES',mode:'taker',px:book.yesAsk,fair,netEdge:round(net,3),reason:'fair '+round(fair,3)+' vs ask '+book.yesAsk};
    }
  }
  if(Number.isFinite(book.noAsk)&&book.noAsk>0.02&&book.noAsk<0.98){
    const gross=(1-fair)-book.noAsk;
    const net=gross-takerFee(book.noAsk,1);
    if(counterTrend('NO')&&net<CFG.EDGE_MIN_TAKER_HV)return{action:'NONE',reason:'counter-trend NO needs edge >= '+CFG.EDGE_MIN_TAKER_HV+' (drift '+round(drift,3)+')'};
    if(net>=edgeMin){
      if(volSkip)return{action:'NONE',reason:'vol regime '+round(o.volBps,3)+' in skip band ['+CFG.VOL_SKIP_LO+','+CFG.VOL_SKIP_HI+') — model miscalibrated in transitional chop'};
      if(volTooHot)return{action:'NONE',reason:'hot tape '+round(o.volBps,3)+' > '+CFG.VOL_MAX_ENTER+' — drift is noise, side-selection unreliable (50% wr / -$1.87 above 0.45)'};
      if(CFG.GAP_MIN>0){const g=(1-fair)-book.noAsk; if(g<CFG.GAP_MIN||g>=CFG.GAP_MAX)return{action:'NONE',reason:'gap '+round(g,3)+' outside edge band ['+CFG.GAP_MIN+','+CFG.GAP_MAX+'] — model-vs-market disagreement not in the 83%-wr zone (F17)'};}
      if(CFG.VOL_MIN_ENTER>0&&Number.isFinite(o.volBps)&&o.volBps<CFG.VOL_MIN_ENTER)return{action:'NONE',reason:'dead-calm tape '+round(o.volBps,3)+' < '+CFG.VOL_MIN_ENTER+' (70.6% wr / -$27 — model overconfident before a move)'};
      if(CFG.DRIFT_OPPOSE_MIN>0&&drift>=CFG.DRIFT_OPPOSE_MIN)return{action:'NONE',reason:'NO opposes drift +'+round(drift,3)+' (|d|>='+CFG.DRIFT_OPPOSE_MIN+') — against-flow lost -$33 on 47 trades'};
      if(CFG.NO_DRIFT_MAX<99&&Number.isFinite(o.driftBps)&&o.driftBps>=CFG.NO_DRIFT_MAX)return{action:'NONE',reason:'NO regime gate: raw drift +'+round(o.driftBps,3)+' >= '+CFG.NO_DRIFT_MAX+' — entering against up-tape (hot-tape drift-blind hole), NO base rate below breakeven (F21)'};
      if(CFG.NO_AF_MAX<1&&Number.isFinite(o.aboveFrac)&&o.aboveFrac>CFG.NO_AF_MAX)return{action:'NONE',reason:'NO regime gate: above-frac '+round(o.aboveFrac,2)+' > '+CFG.NO_AF_MAX+' — recent settles not bearish, NO base rate below breakeven (F21)'};
      if(book.noAsk<CFG.MIN_ENTRY_PX||book.noAsk>CFG.MAX_ENTRY_PX)return{action:'NONE',reason:'entry px '+book.noAsk+' outside edge band ['+CFG.MIN_ENTRY_PX+','+CFG.MAX_ENTRY_PX+']'};
      if(!cushionOK('NO'))return{action:'NONE',reason:'real cushion only '+round(-realCushionSigma,2)+' sigma (need '+CFG.MIN_CUSHION_SIGMA+') — fair is drift-manufactured'};
      if(locked&&lockout.side==='NO')return{action:'NONE',reason:'reversal lockout (NO) this window'};
      if(cdSameWindow&&o.lockout.side==='NO')return{action:'NONE',reason:'cooldown same-side NO ('+Math.ceil((o.cooldownUntil-Date.now())/1000)+'s)'};
      if(!inBand(1-anchoredFair(fair,book)))return{action:'NONE',reason:'conviction(no) '+round(1-anchoredFair(fair,book),3)+(CFG.FAIR_ANCHOR_ON?' (market-anchored)':'')+' outside trade band ['+CFG.FAIR_MAX_LO+','+convFloor+']'};
      if(sentPressure>=vetoAt)return{action:'NONE',reason:'NO edge but perp pressure up (veto @'+vetoAt+')'};
      return{action:'BUY_NO',mode:'taker',px:book.noAsk,fair,netEdge:round(net,3),reason:'fair(no) '+round(1-fair,3)+' vs ask '+book.noAsk};
    }
  }
  const makerFairMax=Math.min(0.9, CFG.MAX_ENTRY_PX+CFG.MAKER_EDGE_MIN);
  if(tauSec<=CFG.MAKER_WINDOW_S&&fair>=0.35&&fair<=makerFairMax&&!(locked&&lockout.side==='YES')){
    const bid=round(Math.max(0.02,fair-CFG.MAKER_EDGE_MIN),2);
    if(bid<CFG.MIN_ENTRY_PX||bid>CFG.MAX_ENTRY_PX)
      return{action:'NONE',reason:'maker bid '+bid+' outside edge band ['+CFG.MIN_ENTRY_PX+','+CFG.MAX_ENTRY_PX+']'};
    if(Number.isFinite(book.yesAsk)&&bid<book.yesAsk)
      return{action:'POST_YES_BID',mode:'maker',px:bid,fair,netEdge:round(fair-bid-CFG.MAKER_FEE,3),reason:'panic-capture bid '+bid+' vs fair '+round(fair,3)};
  }
  return{action:'NONE',reason:'no edge ≥ '+edgeMin};
}
// v4.16 F30 MAKER-FIRST EXECUTION PLANNER (pure/testable). Given a taker BUY decision, decide whether to
// rest a maker bid 1c inside the touch (cheaper fill + flat maker fee) or take. Taker fallback if there's
// not enough time left to rest (tau must exceed MIN_TAU_ENTER + the wait). MAKER_FIRST=0 => always take
// (identical to 4.15). Outcome-independent edge: every maker fill saves fee delta + the undercut.
function planExecution(decision, tauSec){
  if(!CFG.MAKER_FIRST) return {mode:'taker', px:decision.px, side:decision.action==='BUY_YES'?'YES':'NO'};
  if(decision.action!=='BUY_YES' && decision.action!=='BUY_NO')
    return {mode:'taker', px:decision.px, side:decision.action==='BUY_YES'?'YES':'NO'};
  const side=decision.action==='BUY_YES'?'YES':'NO';
  // need room to rest and still fall back to a taker inside the trade window
  if(!(tauSec > CFG.MIN_TAU_ENTER + CFG.MAKER_WAIT_S))
    return {mode:'taker', px:decision.px, side, reason:'too little time to rest maker'};
  const makerPx=round(Math.max(0.02, decision.px - CFG.MAKER_UNDERCUT), 2);
  // never rest at/through the taker price (would be a taker); require a real improvement
  if(!(makerPx < decision.px))
    return {mode:'taker', px:decision.px, side, reason:'undercut collapses to taker'};
  return {mode:'maker-first', makerPx, takerPx:decision.px, side, deadlineMs:Date.now()+CFG.MAKER_WAIT_S*1000};
}
function decideExit(o){
  const {pos,fair,sentPressure,tauSec,condSince}=o;
  if(!pos)return{exit:false,cond:false};
  const adverse=pos.side==='YES'?(sentPressure<=-CFG.EXIT_SENT):(sentPressure>=CFG.EXIT_SENT);
  const posFair=pos.side==='YES'?fair:1-fair;
  const collapsed=(pos.entryFair-posFair)>=CFG.EXIT_FAIR_DROP;
  const cond=adverse&&collapsed&&tauSec>3;
  if(!cond)return{exit:false,cond:false};
  const heldMs=condSince?Date.now()-condSince:0;
  const needMs=CFG.REVERSAL_HOLD_S*1000;
  if(heldMs>=needMs||tauSec<60)
    return{exit:true,cond:true,reason:'confirmed reversal ('+Math.round(heldMs/1000)+'s persist): perp '+sentPressure+', fair '+round(pos.entryFair,2)+'→'+round(posFair,2)};
  return{exit:false,cond:true};
}

/* --------------------- v4.3 F16: late-window locked-average salvage exit --------------------- */
function decideLateExit(o){
  const {side,strike,tauSec,lockedAvg,elapsedSec,price,volBps,book,K,minSalvage}=o;
  if(!Number.isFinite(strike)||!Number.isFinite(lockedAvg)||!Number.isFinite(price)||!Number.isFinite(volBps))
    return{exit:false,reason:'insufficient data'};
  const kk=Number.isFinite(K)?K:2.0;
  const remaining=tauSec;
  if(remaining<=0||elapsedSec<=0) return{exit:false,reason:'window not open'};
  const lockedSum=lockedAvg*elapsedSec;
  const reqFutureMean=(60*strike - lockedSum)/remaining;
  const sig=(volBps/1e4)*price;
  const moveCap=kk*sig*Math.sqrt(Math.max(remaining,1));
  let decidedLoss;
  if(side==='YES'){
    decidedLoss=(price+moveCap) <= reqFutureMean;
  } else {
    decidedLoss=(price-moveCap) > reqFutureMean;
  }
  if(!decidedLoss) return{exit:false,reason:'not decided'};
  const salvagePx = side==='YES' ? (book&&book.yesBid) : (book&&book.noBid);
  if(!Number.isFinite(salvagePx)||salvagePx< (minSalvage??0.03))
    return{exit:false,reason:'decided loss but no salvage bid ('+round(salvagePx,2)+')',decidedLoss:true};
  return{exit:true,salvagePx,reason:'late-exit: locked avg decides loss ('+kk+'σ cannot recover w/ '+round(remaining,0)+'s left) — salvage @'+round(salvagePx,2)};
}

/* --------------------- risk cage (E5) --------------------- */
function makeCage(){
  return{
    day:null,realized:0,consecLosses:0,manualHalt:false,
    roll(){const d=new Date().toISOString().slice(0,10);if(d!==this.day){this.day=d;this.realized=0;this.consecLosses=0;}},
    record(pnl){this.roll();if(!Number.isFinite(pnl))return;this.realized+=pnl;if(pnl<0)this.consecLosses++;else if(pnl>0)this.consecLosses=0;},
    adjust(delta){this.roll();if(!Number.isFinite(delta))return;this.realized+=delta;},
    halted(){this.roll();
      if(this.manualHalt)return'manual halt';
      if(this.realized<=-Math.abs(CFG.DAILY_LOSS_LIMIT))return'daily loss limit';
      if(this.consecLosses>=CFG.MAX_CONSEC_LOSSES)return'consecutive losses';
      return null;}
  };
}
const cage=makeCage();

/* --------------------- shadow book-keeping --------------------- */
const STATE={pos:null,pendingMaker:null,lastReversal:null,cooldownUntil:0,fairStreak:0,fairStreakTicker:'',trades:[],reconcile:[],lastStatus:null,lastErr:null,ticks:0,lastSkipKey:'',skips:[],phantoms:[],revCondSince:0,recentMargins:[],observedMarkets:{},basisSamples:[],settledTickers:[]};
function pushBasis(sample){
  if(sample==null||!Number.isFinite(sample))return;
  STATE.basisSamples.push(sample);
  while(STATE.basisSamples.length>Math.max(CFG.BASIS_LOOKBACK,5))STATE.basisSamples.shift();
}
function currentBasis(){
  if(!CFG.BASIS_ON)return 0;
  if(CFG.BASIS_MANUAL!==0)return CFG.BASIS_MANUAL;
  const s=STATE.basisSamples;
  if(s.length<3)return 0;
  const w=[...s].sort((a,b)=>a-b);
  return w[Math.floor(w.length/2)];
}
function seedRegimeFromLog(){
  try{
    if(!fs.existsSync(LOG_PATH))return 0;
    const raw=fs.readFileSync(LOG_PATH,'utf8');
    const lines=raw.split(/\r?\n/); const byTicker={};
    for(const ln of lines){
      if(!ln)continue;
      if(ln.indexOf('REGIME_OBSERVE')<0 && ln.indexOf('"CLOSE"')<0 && ln.indexOf('"ev":"CLOSE"')<0)continue;
      let o; try{o=JSON.parse(ln);}catch(_){continue;}
      if(!o||(o.ev!=='REGIME_OBSERVE'&&o.ev!=='CLOSE'))continue;
      if(o.margin==null||!Number.isFinite(o.margin)||!o.ticker)continue;
      if(CFG.REGIME_MARGIN_SANE>0 && Math.abs(o.margin)>CFG.REGIME_MARGIN_SANE)continue;
      byTicker[o.ticker]=o.margin;
    }
    const key=t=>{const m=String(t).match(/26[A-Z]{3}(\d{2})(\d{2})(\d{2})-/);return m?(m[1]+m[2]+m[3]):'';};
    const ordered=Object.keys(byTicker).sort((a,b)=>key(a)<key(b)?-1:key(a)>key(b)?1:0);
    const cap=Math.max(CFG.REGIME_LOOKBACK*3,30);
    const seedTickers=ordered.slice(-cap);
    STATE.recentMargins=seedTickers.map(t=>byTicker[t]);
    STATE.settledTickers=seedTickers.slice();
    return STATE.recentMargins.length;
  }catch(_){return 0;}
}
function regimeWarm(){ return STATE.recentMargins.length>=CFG.REGIME_LOOKBACK; }
function markSettled(ticker){
  if(!ticker)return true;
  if(STATE.settledTickers.indexOf(ticker)>=0)return false;
  STATE.settledTickers.push(ticker);
  while(STATE.settledTickers.length>200)STATE.settledTickers.shift();
  return true;
}
function pushRegimeMargin(margin){
  if(margin==null||!Number.isFinite(margin))return;
  if(CFG.REGIME_MARGIN_SANE>0 && Math.abs(margin)>CFG.REGIME_MARGIN_SANE){
    try{logLine({ev:'POISON_MARGIN',margin:round(margin,2),sane:CFG.REGIME_MARGIN_SANE,note:'dropped from regime buffer (F25)'});}catch(_){}
    return;
  }
  STATE.recentMargins.push(margin);
  const cap=Math.max(CFG.REGIME_LOOKBACK*3,30);
  while(STATE.recentMargins.length>cap)STATE.recentMargins.shift();
}
function regimeMean(){
  const n=CFG.REGIME_LOOKBACK;
  if(STATE.recentMargins.length<n)return null;
  const w=STATE.recentMargins.slice(-n);
  return w.reduce((a,b)=>a+Math.abs(b),0)/n;
}
function aboveFrac(){
  const n=CFG.YES_AF_N, s=STATE.recentMargins;
  if(s.length<4)return null;
  const w=s.slice(-n);
  return w.filter(x=>x>0).length/w.length;
}
function entryViolence(){
  const s=STATE.recentMargins;
  if(s.length<4)return null;
  const w=s.slice(-CFG.REV_N);
  return w.reduce((a,b)=>a+Math.abs(b),0)/w.length;
}
function regimeThreshold(price){
  // price-normalized when REGIME_MARGIN_PCT>0 (scales the violent-tape cutoff with BTC price/vol);
  // otherwise the legacy fixed-dollar REGIME_MARGIN_MAX.
  if(CFG.REGIME_MARGIN_PCT>0 && Number.isFinite(price) && price>0) return CFG.REGIME_MARGIN_PCT*price;
  return CFG.REGIME_MARGIN_MAX;
}
function regimeViolent(price){
  if(!CFG.REGIME_ON)return false;
  const thr=regimeThreshold(price);
  if(thr<=0)return false;
  const m=regimeMean();
  return m!=null && m>thr;
}
// v4.16 F28: characterize the recent settle regime. recentMargins holds SIGNED (settle-strike).
// consistency = |sum(margins)|/sum(|margins|): 1=one-directional trend, ~0=alternating chop.
// trendSign = net direction of the last REGIME_LOOKBACK settles (+1 = settling above strike / up-tape).
// Returns null when the buffer is too short to judge.
function regimeTrend(){
  const n=CFG.REGIME_LOOKBACK, s=STATE.recentMargins;
  if(s.length<n)return null;
  const w=s.slice(-n);
  const sum=w.reduce((a,b)=>a+b,0);
  const abs=w.reduce((a,b)=>a+Math.abs(b),0);
  const consistency=abs>0?Math.abs(sum)/abs:0;
  return {consistency, trendSign: sum>=0?1:-1};
}
function logLine(obj){try{fs.appendFileSync(LOG_PATH,JSON.stringify(obj)+'\n');}catch(_){}}
function openPos(mkt,side,mode,px,fair,tauSec){
  const _drift=round(tapeDrift(),4), _vol=round(tapeVolBps(),3);
  let baseQty=CFG.CONTRACTS;
  if(CFG.RISK_DOLLARS>0 && px>0.01){
    baseQty=Math.max(1,Math.round(CFG.RISK_DOLLARS/px));
  }
  const qty=STATE.inHV?Math.max(1,Math.floor(baseQty/2)):baseQty;
  const fees=mode==='taker'?takerFee(px,qty):makerFee(qty);
  STATE.pos={ticker:mkt.ticker,strike:mkt.strike,closeTs:mkt.closeTs,side,mode,px,qty,fees,
    entryFair:side==='YES'?fair:1-fair,entryTs:Date.now(),entryTau:tauSec,session:sessionTag(ptClock()),entryDrift:_drift,entryVol:_vol,
    ...radarSnapshot()};
  logLine({ev:'OPEN',...STATE.pos});
  if(liveReady()){
    const cents=Math.round(px*100);
    const cnt=Math.min(qty,CFG.LIVE_MAX_CONTRACTS);
    const posRef=STATE.pos;
    placeLiveOrder(mkt.ticker,side.toLowerCase(),cnt,cents).then(r=>{
      if(!CFG.LIVE||!r||r.dryRun||r.blocked)return;
      const f=LIVE.lastFill&&LIVE.lastFill.ticker===mkt.ticker?LIVE.lastFill.filled:0;
      if(!f||f<=0){
        if(STATE.pos===posRef){STATE.pos=null;STATE.revCondSince=0;}
        logLine({ev:'POSITION_VOID',ticker:mkt.ticker,reason:'order filled 0 — no position held'});
      } else if(STATE.pos===posRef && f<posRef.qty){
        STATE.pos.qty=f;
        logLine({ev:'POSITION_RESIZED',ticker:mkt.ticker,from:posRef.qty,to:f});
      }
    }).catch(e=>{
      LIVE.lastErr=String(e.message||e);logLine({ev:'LIVE_ERROR',err:LIVE.lastErr});});
  }
}
function closePos(reason,exitPx,settled,won,extra){
  const p=STATE.pos;if(!p)return;
  let pnl;
  if(settled){pnl=p.qty*((won?1:0)-p.px)-p.fees;}
  else{const fee=takerFee(exitPx,p.qty);pnl=p.qty*(exitPx-p.px)-p.fees-fee;}
  let riskPnl=pnl;
  const nearStrike=settled&&extra&&extra.margin!=null&&Math.abs(extra.margin)<CFG.NEAR_STRIKE_USD;
  if(nearStrike){riskPnl=-(p.qty*p.px)-p.fees;}
  const rec={ev:'CLOSE',ticker:p.ticker,side:p.side,mode:p.mode,entryPx:p.px,exitPx:settled?(won?1:0):exitPx,
    qty:p.qty,pnl:round(pnl,2),reason,settled:!!settled,entryFair:round(p.entryFair,3),
    entryTau:p.entryTau,session:p.session||'unknown',ts:Date.now(),
    ...(nearStrike?{riskProvisional:round(riskPnl,2)}:{}),...(extra||{})};
  rec.riskBooked=round(riskPnl,2);
  if(settled&&extra&&extra.margin!=null&&markSettled(rec.ticker))pushRegimeMargin(extra.margin);
  STATE.trades.push(rec);cage.record(riskPnl);
  if(CFG.LIVE)liveRecord(riskPnl);
  logLine(rec);
  if(settled)STATE.reconcile.push({ticker:p.ticker,ourWin:won,side:p.side,checkedAt:0});
  else {STATE.lastReversal={ticker:p.ticker,side:p.side,ts:Date.now()};STATE.cooldownUntil=Date.now()+CFG.COOLDOWN_S*1000;
    STATE.phantoms.push({ticker:p.ticker,side:p.side,px:p.px,qty:p.qty,fees:p.fees,
      closeTs:p.closeTs,strike:p.strike,exitPnl:pnl,ts:Date.now()});
    if(STATE.phantoms.length>50)STATE.phantoms.shift();}
  STATE.pos=null; STATE.revCondSince=0;
}

/* --------------------- main loop --------------------- */
let _tickInFlight=false; // BUG1 fix: single-flight mutex — prevents overlapping ticks (slow API) from double-acting
async function tick(){
  if(_tickInFlight){STATE.tickSkips=(STATE.tickSkips||0)+1;return;} // a prior tick is still running; skip this one
  _tickInFlight=true;
  try{ return await _tickBody(); }
  finally{ _tickInFlight=false; }
}
async function _tickBody(){
  STATE.ticks++;
  if(CFG.RADAR_URL&&STATE.ticks%3===0)pollRadar().catch(()=>{});
  await pollSpot().catch(()=>{});
  ensureSentinel();
  const price=tapeNow();
  const sent=SENT.read||{ok:false,pressure:0};
  const nowMin=ptClock();
  const w=windowState(nowMin);STATE.inHV=w.inHV;
  const haltReason=cage.halted();
  let mkt=null,book=null,fair=null,rawFair=null,tauSec=null,decision={action:'NONE',reason:'idle'};
  try{
    mkt=await discoverMarket(price);
    if(mkt&&Number.isFinite(mkt.strike)&&Number.isFinite(mkt.closeTs)){
      STATE.observedMarkets=STATE.observedMarkets||{};
      if(!STATE.observedMarkets[mkt.ticker])STATE.observedMarkets[mkt.ticker]={strike:mkt.strike,closeTs:mkt.closeTs};
    }
    if(STATE.observedMarkets){
      for(const tk of Object.keys(STATE.observedMarkets)){
        const om=STATE.observedMarkets[tk];
        if(Date.now()>om.closeTs+1500){
          const settleAvg=tapeAvg(om.closeTs-60000,om.closeTs);
          const settlePx=(settleAvg!==null)?settleAvg:tapeLastAt(om.closeTs);
          if(settlePx!==null && markSettled(tk)){
            pushRegimeMargin(settlePx-om.strike);
            logLine({ev:'REGIME_OBSERVE',ticker:tk,margin:round(settlePx-om.strike,2),regimeMean:round(regimeMean(),1),traded:false});
          }
          delete STATE.observedMarkets[tk];
        }
      }
    }
    for(let i=STATE.phantoms.length-1;i>=0;i--){
      const ph=STATE.phantoms[i];
      if(Date.now()>ph.closeTs+1500){
        const lastPx=tapeLastAt(ph.closeTs);
        if(lastPx!==null){
          const won=(ph.side==='YES')?lastPx>ph.strike:lastPx<=ph.strike;
          const heldPnl=won?(1-ph.px)*ph.qty-ph.fees:-(ph.px*ph.qty)-ph.fees;
          logLine({ev:'PHANTOM',ticker:ph.ticker,side:ph.side,exitPnl:round(ph.exitPnl,2),
            heldPnl:round(heldPnl,2),exitSaved:round(ph.exitPnl-heldPnl,2),
            settleLast:round(lastPx,2),strike:ph.strike,ts:Date.now()});
        }
        STATE.phantoms.splice(i,1);
      }
    }
    if(STATE.pos&&Date.now()>STATE.pos.closeTs){
      const avg=tapeAvg(STATE.pos.closeTs-60000,STATE.pos.closeTs);
      const lastPx=tapeLastAt(STATE.pos.closeTs);
      const metric=(CFG.SETTLE_METRIC==='avg60')?avg:lastPx;
      const fallback=(metric===null)?((CFG.SETTLE_METRIC==='avg60')?lastPx:avg):null;
      const use=metric!==null?metric:fallback;
      // BUG5 fix: if BOTH proxy measurements are unavailable, DO NOT book won=false (a fabricated loss).
      // Defer — keep the position and let RECONCILE resolve it from Kalshi's official result. Only clear
      // the observed-market marker and book once we have a real settlement number (proxy or, later, Kalshi).
      if(use===null){
        if(!STATE.pos._deferredSettle){STATE.pos._deferredSettle=Date.now();
          logLine({ev:'SETTLE_DEFER',ticker:STATE.pos.ticker,reason:'no proxy settle data — awaiting Kalshi official result',strike:STATE.pos.strike});}
        // reconcile() (which fetches Kalshi's official result) will settle it; nothing booked here.
      } else {
        if(STATE.observedMarkets)delete STATE.observedMarkets[STATE.pos.ticker];
        const won=(STATE.pos.side==='YES'?use>STATE.pos.strike:use<=STATE.pos.strike);
        closePos('settlement ('+CFG.SETTLE_METRIC+' '+round(use,2)+')',null,true,won,
          {settleAvg60:round(avg,2),settleLast:round(lastPx,2),settleUsed:metric!==null?CFG.SETTLE_METRIC:'fallback',
           margin:round(use-STATE.pos.strike,2),strike:STATE.pos.strike});
      }
    }
    if(STATE.pos&&CFG.LATE_EXIT_ON){
      const posTau=(STATE.pos.closeTs-Date.now())/1000;
      if(posTau<=CFG.LATE_EXIT_TAU&&posTau>=CFG.LATE_EXIT_MIN_TAU){
        const elapsed=Math.max(0,60-posTau);
        const lockedAvg=tapeAvg(STATE.pos.closeTs-60000, Date.now());
        const px=tapeNow();
        if(Number.isFinite(lockedAvg)&&Number.isFinite(px)){
          let pbook=null;
          try{ pbook=await getBook(STATE.pos.ticker,null); }catch(_){}
          const lx=decideLateExit({side:STATE.pos.side,strike:STATE.pos.strike,tauSec:posTau,lockedAvg,
            elapsedSec:elapsed,price:px,volBps:tapeVolBps(),book:pbook||{},K:CFG.LATE_EXIT_K,minSalvage:CFG.LATE_EXIT_MIN_SALVAGE});
          logLine({ev:'LATE_EVAL',ticker:STATE.pos.ticker,posTau:round(posTau,0),lockedAvg:round(lockedAvg,1),
            price:round(px,1),strike:STATE.pos.strike,side:STATE.pos.side,decided:!!lx.exit,reason:lx.reason});
          if(lx.exit){
            // BUG2 fix: in LIVE, await the close and only mark the position closed if it did NOT error.
            // If the close fails, keep the position (a later tick / reconcile handles it) rather than
            // recording a phantom-closed position that could let the bot open a duplicate trade.
            if(CFG.LIVE&&liveReady()){
              let res=null; try{ res=await placeCloseOrder(STATE.pos,lx.salvagePx); }catch(e){ res={error:String(e&&e.message||e)}; }
              if(res&&res.error){
                logLine({ev:'LATE_EXIT_CLOSE_FAILED',ticker:STATE.pos.ticker,err:res.error,note:'position kept — not booked closed'});
              } else {
                closePos(lx.reason,lx.salvagePx,false,null,{lateExit:true});
              }
            } else {
              closePos(lx.reason,lx.salvagePx,false,null,{lateExit:true}); // dry-run: safe to book
            }
          }
        }
      }
    }
    if(STATE.lastReversal&&mkt&&STATE.lastReversal.ticker!==mkt.ticker)STATE.lastReversal=null;
    if(STATE.pendingMaker&&(!mkt||STATE.pendingMaker.ticker!==mkt.ticker)){
      logLine({ev:'MAKER_CANCEL',ticker:STATE.pendingMaker.ticker,why:'window rolled'});
      STATE.pendingMaker=null;
    }
    if(mkt&&Number.isFinite(mkt.strike)){
      tauSec=(mkt.closeTs-Date.now())/1000;
      book=await getBook(mkt.ticker,mkt.quotes);
      const avgStart=mkt.closeTs-60000;
      const knownDur=clamp((Date.now()-avgStart)/1000,0,60);
      const knownAvg=knownDur>1?tapeAvg(avgStart,Date.now()):null;
      fair=computeFair({price,strike:mkt.strike,tauSec,volBps:tapeVolBps(),driftBps:tapeDrift(),knownAvg,knownDur});
      rawFair=fair;
      if(CFG.CAL_ON&&fair!==null){
        fair=calFair(fair);
      }
      if(STATE.pendingMaker&&STATE.pendingMaker.ticker===mkt.ticker){
        const pm=STATE.pendingMaker;
        if(pm.makerFirst){
          // BUG3 fix: maker-first is a SIMULATION — openPos() sends an IOC (taker) order, so a "maker fill" at
          // pm.makerPx is fictional (reported price/fee/P&L would be wrong). Until real resting maker orders are
          // implemented (submit/cancel/reconcile against Kalshi), do NOT run the simulation on LIVE money.
          if(CFG.LIVE){
            STATE.pendingMaker=null;
            logLine({ev:'MAKER_DISABLED_LIVE',ticker:pm.ticker,side:pm.side,note:'maker-first not implemented for live (IOC only) — taking as taker instead'});
            const ask = pm.side==='YES' ? book.yesAsk : book.noAsk;
            const fbAsk = Number.isFinite(ask)?ask:pm.takerPx;
            if(fbAsk>=CFG.MIN_ENTRY_PX && fbAsk<=CFG.MAX_ENTRY_PX) openPos(mkt,pm.side,'taker',fbAsk,fair,tauSec);
          } else {
          // v4.16 F30 maker-first resolution (DRY-RUN/shadow only): fill if the touch comes to our bid; taker-fallback on deadline.
          const ask = pm.side==='YES' ? book.yesAsk : book.noAsk;
          if(tauSec<CFG.MIN_TAU_ENTER || Math.abs((fair??0)-pm.fairAtPost)>0.12){
            STATE.pendingMaker=null; logLine({ev:'MAKER_CANCEL',ticker:pm.ticker,side:pm.side,why:'stale/fair moved (maker-first)'});
          } else if(Number.isFinite(ask)&&ask<=pm.makerPx){
            STATE.pendingMaker=null; logLine({ev:'MAKER_FILL',ticker:pm.ticker,side:pm.side,px:pm.makerPx,takerPx:pm.takerPx,saved:round(pm.takerPx-pm.makerPx,3)});
            openPos(mkt,pm.side,'maker',pm.makerPx,fair,tauSec);
          } else if(Date.now()>=pm.deadlineMs){
            const fbAsk = Number.isFinite(ask)?ask:pm.takerPx; // fall back to current ask (or original taker px)
            STATE.pendingMaker=null; logLine({ev:'MAKER_TIMEOUT',ticker:pm.ticker,side:pm.side,fallbackPx:fbAsk});
            if(fbAsk>=CFG.MIN_ENTRY_PX && fbAsk<=CFG.MAX_ENTRY_PX) openPos(mkt,pm.side,'taker',fbAsk,fair,tauSec);
          }
          }
        } else {
          if(tauSec<8||Math.abs((fair??0)-pm.fairAtPost)>0.12){STATE.pendingMaker=null;logLine({ev:'MAKER_CANCEL',ticker:pm.ticker,why:'stale/fair moved'});}
          else if(Number.isFinite(book.yesAsk)&&book.yesAsk<=pm.px){
            STATE.pendingMaker=null;openPos(mkt,'YES','maker',pm.px,fair,tauSec);
          }
        }
      }
      if(STATE.pos&&STATE.pos.ticker===mkt.ticker&&tauSec>0){
        const ex=decideExit({pos:STATE.pos,fair,sentPressure:sent.pressure||0,tauSec,condSince:STATE.revCondSince});
        if(ex.cond&&!STATE.revCondSince)STATE.revCondSince=Date.now();
        if(!ex.cond)STATE.revCondSince=0;
        if(ex.exit){
          const px=STATE.pos.side==='YES'?(book.yesBid??Math.max(0.01,fair-0.03)):(book.noBid??Math.max(0.01,1-fair-0.03));
          closePos(ex.reason,px,false,null);
        }
      }
      const sessNow=sessionTag(nowMin);
      const liveHalt=CFG.LIVE?liveHalted():null;
      const gated=haltReason?('halted: '+haltReason)
        :(liveHalt?('live halted: '+liveHalt)
        :(sessionSkipped(sessNow)?('session "'+sessNow+'" disabled (SKIP_SESSIONS='+CFG.SKIP_SESSIONS+')')
        :((!CFG.TRADE_ALL_HOURS&&!w.inPrime)?'outside prime window'
        :(!sent.ok&&tauSec<180?'sentinel warming (late-window entries blocked)':null))));
      if(!gated&&tauSec>0&&tauSec<=CFG.MAX_TAU_ENTER&&!STATE.pendingMaker){
        (function(){
          // BUGFIX (stability-counter scale): when market-anchoring is on, the conviction GATE uses the
          // anchored value against FAIR_ANCHOR_MIN — so the stability streak must use the SAME basis, or the
          // honest ~0.78 trades anchoring is meant to admit can never accumulate FAIR_STABLE_N reads.
          let conf, floor;
          if(CFG.FAIR_ANCHOR_ON){ const af=anchoredFair(fair,book); conf=Math.max(af,1-af); floor=CFG.FAIR_ANCHOR_MIN; }
          else { conf=Math.max(fair,1-fair); floor=CFG.FAIR_MIN_HI; }
          const clears=(conf>=floor)||(Math.min(fair,1-fair)<=CFG.FAIR_MAX_LO&&CFG.FAIR_MAX_LO>0);
          if(mkt.ticker!==STATE.fairStreakTicker){STATE.fairStreakTicker=mkt.ticker;STATE.fairStreak=0;}
          STATE.fairStreak = clears ? STATE.fairStreak+1 : 0;
        })();
        decision=decideEntry({fair,rawFair,book,tauSec,fairStreak:STATE.fairStreak,inHV:w.inHV,sentPressure:sent.pressure||0,haveOpen:!!STATE.pos,ticker:mkt.ticker,lockout:STATE.lastReversal,cooldownUntil:STATE.cooldownUntil,driftBps:tapeDrift(),price,strike:mkt.strike,volBps:tapeVolBps(),basis:currentBasis(),aboveFrac:aboveFrac(),entryViolence:entryViolence()});
        if(decision.action==='NONE'){
          const key=(mkt?mkt.ticker:'-')+'|'+decision.reason;
          if(key!==STATE.lastSkipKey && decision.reason!=='position open'){
            STATE.lastSkipKey=key;
            const rec={ev:'SKIP',ticker:mkt?mkt.ticker:null,fair:fair===null?null:round(fair,3),
              tauSec:round(tauSec,0),reason:decision.reason,ts:Date.now()};
            STATE.skips.push(rec); if(STATE.skips.length>200)STATE.skips.shift();
            logLine(rec);
          }
        } else { STATE.lastSkipKey=''; }
        if(decision.action==='BUY_YES'||decision.action==='BUY_NO'){
          const plan=planExecution(decision,tauSec);
          if(plan.mode==='maker-first'){
            STATE.pendingMaker={ticker:mkt.ticker,side:plan.side,makerPx:plan.makerPx,takerPx:plan.takerPx,
              fairAtPost:fair,deadlineMs:plan.deadlineMs,entryTau:tauSec,makerFirst:true};
            logLine({ev:'MAKER_POST',ticker:mkt.ticker,side:plan.side,px:plan.makerPx,takerPx:plan.takerPx,fair:round(fair,3),mode:'maker-first'});
          } else {
            openPos(mkt,plan.side,'taker',plan.px,fair,tauSec);
          }
        }
        else if(decision.action==='POST_YES_BID'){STATE.pendingMaker={ticker:mkt.ticker,px:decision.px,fairAtPost:fair,ts:Date.now()};logLine({ev:'MAKER_POST',ticker:mkt.ticker,px:decision.px,fair:round(fair,3)});}
      }else if(gated){decision={action:'NONE',reason:gated};}
    }
    STATE.lastErr=null;
  }catch(e){STATE.lastErr=String(e.message||e);}
  const rc=STATE.reconcile.find(r=>Date.now()-r.checkedAt>30000);
  if(rc){rc.checkedAt=Date.now();
    fetchJson(KALSHI_BASE+'/markets/'+encodeURIComponent(rc.ticker)).then(j=>{
      const result=j&&j.market&&j.market.result;
      if(result==='yes'||result==='no'){
        const actualWin=rc.side==='YES'?result==='yes':result==='no';
        const match=actualWin===rc.ourWin;
        logLine({ev:'RECONCILE',ticker:rc.ticker,kalshiResult:result,ourWin:rc.ourWin,match});
        let rec=null;
        for(let i=STATE.trades.length-1;i>=0;i--){if(STATE.trades[i].ticker===rc.ticker&&STATE.trades[i].settled){rec=STATE.trades[i];break;}}
        if(CFG.BASIS_ON){
          const mk=j&&j.market||{};
          let kSettle=null;
          for(const f of[mk.settlement_value,mk.result_value,mk.expiration_value,mk.settled_value]){
            const n=Number(f); if(Number.isFinite(n)&&n>0){kSettle=n>1e5?n/100:n;break;}
          }
          if(kSettle!==null && rec && Number.isFinite(rec.settleAvg60)){
            const basisSample=round(rec.settleAvg60-kSettle,2);
            pushBasis(basisSample);
            logLine({ev:'BASIS',ticker:rc.ticker,proxyAvg60:rec.settleAvg60,kalshiSettle:kSettle,
              basis:basisSample,rollingBasis:round(currentBasis(),2),n:STATE.basisSamples.length});
          }
        }
        if(rec){rec.kalshiResult=result;
          const np=truthPnl(rec,actualWin);
          const booked=(rec.riskBooked!==undefined&&rec.riskBooked!==null)?rec.riskBooked:rec.pnl;
          const delta=Math.round((np-booked)*100)/100;
          if(delta!==0){
            cage.adjust(delta);
            if(CFG.LIVE)liveRecord(delta);
            logLine({ev:'RISK_ADJUST',ticker:rc.ticker,booked,truth:np,delta,
              cageRealized:round(cage.realized,2),liveRealized:round(LIVE.realizedToday,2)});
          }
          rec.riskBooked=np;
          if(!match){
            logLine({ev:'CORRECTION',ticker:rc.ticker,oldPnl:rec.pnl,newPnl:np,margin:rec.margin??null});
            rec.pnlOriginal=rec.pnl;rec.pnl=np;rec.corrected=true;
          } else if(rec.pnl!==np){ rec.pnl=np; }
        }
        STATE.reconcile=STATE.reconcile.filter(x=>x!==rc);
      }
    }).catch(()=>{});
  }
  STATE.lastStatus={ts:Date.now(),price:round(price,2),market:mkt?{ticker:mkt.ticker,strike:mkt.strike,tauSec:round(tauSec,0)}:null,
    recentSkips:STATE.skips.slice(-5),
    discovery:{...DISC},
    book,fair:fair===null?null:round(fair,3),sentinel:{ok:sent.ok,pressure:sent.pressure||0,venue:sent.venue||null},
    volBps:round(tapeVolBps(),3),driftBps:round(tapeDrift(),4),rawFair:rawFair===null?null:round(rawFair,4),
    window:{inPrime:w.inPrime,inHV:w.inHV},halt:haltReason,liveHalt:CFG.LIVE?liveHalted():null,decision,
    session:sessionTag(nowMin),skipSessions:CFG.SKIP_SESSIONS,
    basis:{on:!!CFG.BASIS_ON,rolling:round(currentBasis(),2),n:STATE.basisSamples.length,haircutK:CFG.BASIS_HAIRCUT_K},
    yesRegime:{afMin:CFG.YES_AF_MIN,af:aboveFrac()==null?null:round(aboveFrac(),2),n:Math.min(STATE.recentMargins.length,CFG.YES_AF_N)},
    noRegime:{afMax:CFG.NO_AF_MAX,driftMax:CFG.NO_DRIFT_MAX},
    reversalFilter:{volMax:CFG.VOL_MAX_ENTER,violenceMax:CFG.REV_VIOLENCE_MAX,violence:entryViolence()==null?null:round(entryViolence(),0),n:CFG.REV_N},
    regimeWarmup:{on:CFG.REGIME_WARMUP,warm:regimeWarm(),buffered:STATE.recentMargins.length,need:CFG.REGIME_LOOKBACK},
    tauFloor:CFG.MIN_TAU_TRADE,
    strikeSaneMin:STRIKE_SANE_MIN,
    riskToday:{cage:round(cage.realized,2),live:round(LIVE.realizedToday,2)},
    position:STATE.pos?{ticker:STATE.pos.ticker,side:STATE.pos.side,px:STATE.pos.px,qty:STATE.pos.qty,mode:STATE.pos.mode}:null,
    pendingMaker:STATE.pendingMaker?{px:STATE.pendingMaker.px}:null,
    tapeErr:lastTapeErr,err:STATE.lastErr};
}

function truthPnl(rec,actualWin){
  const fee=rec.mode==='taker'?takerFee(rec.entryPx,rec.qty):CFG.MAKER_FEE*rec.qty;
  return Math.round((rec.qty*((actualWin?1:0)-rec.entryPx)-fee)*100)/100;
}

/* --------------------- reporting --------------------- */
function report(){
  const t=STATE.trades;
  const n=t.length,wins=t.filter(x=>x.pnl>0).length;
  const pnl=t.reduce((a,x)=>a+x.pnl,0);
  const settledN=t.filter(x=>x.settled).length;
  const byMode={};
  for(const x of t){byMode[x.mode]=byMode[x.mode]||{n:0,pnl:0};byMode[x.mode].n++;byMode[x.mode].pnl=round(byMode[x.mode].pnl+x.pnl,2);}
  const bySession={};
  for(const x of t){const s=x.session||'unknown';bySession[s]=bySession[s]||{n:0,wins:0,pnl:0};
    bySession[s].n++;if(x.pnl>0)bySession[s].wins++;bySession[s].pnl=round(bySession[s].pnl+x.pnl,2);}
  return{version:VERSION,mode:'24/7'+(CFG.TRADE_ALL_HOURS?'':' (PRIME_ONLY)')+(CFG.SKIP_SESSIONS?(' minus ['+CFG.SKIP_SESSIONS+']'):''),
    trades:n,wins,winRate:n?round(wins/n,3):null,totalPnl:round(pnl,2),
    avgPnlPerTrade:n?round(pnl/n,2):null,settled:settledN,reversalExits:n-settledN,corrections:t.filter(x=>x.corrected).length,
    byMode,bySession,todayRealized:round(cage.realized,2),liveRealizedToday:round(LIVE.realizedToday,2),
    consecLosses:cage.consecLosses,halt:cage.halted(),liveHalt:CFG.LIVE?liveHalted():null,
    last10:t.slice(-10)};
}

/* --------------------- self-test (pure, offline) --------------------- */
function runSelfTest(){
  const C=[];
  const _yesOnSaved=CFG.YES_ON; CFG.YES_ON=1;
  const _warmupSaved=CFG.REGIME_WARMUP, _tauTradeSaved=CFG.MIN_TAU_TRADE;
  // v4.16: force all new opt-in flags OFF so the legacy test suite is deterministic regardless of env.
  // Each feature (F28/F29/F30/F31) toggles its own flag inside its dedicated test block.
  const _anchorSaved=CFG.FAIR_ANCHOR_ON, _jumpSaved=CFG.JUMP_ON, _makerSaved=CFG.MAKER_FIRST, _trendSaved=CFG.REGIME_TREND_OVERRIDE;
  CFG.FAIR_ANCHOR_ON=0; CFG.JUMP_ON=0; CFG.MAKER_FIRST=0; CFG.REGIME_TREND_OVERRIDE=0;
  CFG.REGIME_WARMUP=0; CFG.MIN_TAU_TRADE=0;
  // v4.16: force the gate params the pure-logic tests assume to their code defaults, so /selftest is a
  // deterministic code-integrity check regardless of the operator's live tuning (GAP band, cushion, px band).
  const _gS={GAP_MIN:CFG.GAP_MIN,GAP_MAX:CFG.GAP_MAX,MIN_CUSHION_SIGMA:CFG.MIN_CUSHION_SIGMA,MIN_ENTRY_PX:CFG.MIN_ENTRY_PX,MAX_ENTRY_PX:CFG.MAX_ENTRY_PX,VOL_MAX_ENTER:CFG.VOL_MAX_ENTER,VOL_MIN_ENTER:CFG.VOL_MIN_ENTER,FAIR_MIN_HI:CFG.FAIR_MIN_HI};
  CFG.GAP_MIN=0.12; CFG.GAP_MAX=0.20; CFG.MIN_CUSHION_SIGMA=1.0; CFG.MIN_ENTRY_PX=0.55; CFG.MAX_ENTRY_PX=0.78; CFG.VOL_MAX_ENTER=0.45; CFG.VOL_MIN_ENTER=0.15; CFG.FAIR_MIN_HI=0.85;
  const w1=computeFair({price:62200,strike:62050,tauSec:10,volBps:0.6,driftBps:0,knownAvg:62200,knownDur:50});
  C.push({name:'locked avg: near-certain win → fair>0.99',pass:w1>0.99,got:round(w1,4)});
  const l1=computeFair({price:61900,strike:62050,tauSec:10,volBps:0.6,driftBps:0,knownAvg:61900,knownDur:50});
  C.push({name:'locked avg: near-certain loss → fair<0.01',pass:l1<0.01,got:round(l1,4)});
  const m1=computeFair({price:62050,strike:62050,tauSec:300,volBps:0.6,driftBps:0,knownAvg:null,knownDur:0});
  C.push({name:'ATM mid-window → fair≈0.5',pass:m1>0.4&&m1<0.6,got:round(m1,3)});
  const f=takerFee(0.5,1);
  C.push({name:'taker fee @0.50 = 0.0175',pass:Math.abs(f-0.0175)<1e-9,got:round(f,4)});
  const d1=decideEntry({fair:0.90,book:{yesAsk:0.75,noAsk:0.2,yesBid:0.72,noBid:0.14},tauSec:40,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.02,price:66150,strike:66000,volBps:0.30,fairStreak:99});
  C.push({name:'fair .96 vs ask .84 → BUY_YES',pass:d1.action==='BUY_YES',got:d1.action+' '+(d1.netEdge??'')});
  const d2=decideEntry({fair:0.87,book:{yesAsk:0.84,noAsk:0.2,yesBid:0.8,noBid:0.14},tauSec:400,inHV:false,sentPressure:0,haveOpen:false});
  C.push({name:'thin edge → no trade (selectivity)',pass:d2.action==='NONE',got:d2.action});
  const d3=decideEntry({fair:0.92,book:{yesAsk:0.84,noAsk:0.2,yesBid:0.8,noBid:0.14},tauSec:40,inHV:true,sentPressure:0,haveOpen:false});
  C.push({name:'same edge blocked in high-variance window',pass:d3.action==='NONE',got:d3.action});
  const d4=decideEntry({fair:0.96,book:{yesAsk:0.84,noAsk:0.2,yesBid:0.8,noBid:0.14},tauSec:40,inHV:false,sentPressure:-55,haveOpen:false});
  C.push({name:'perp pressure down vetoes YES buy',pass:d4.action==='NONE',got:d4.action});
  const d5=decideEntry({fair:0.68,book:{yesAsk:0.66,noAsk:0.5,yesBid:0.42,noBid:0.4},tauSec:120,inHV:false,sentPressure:0,haveOpen:false});
  C.push({name:'late window → panic-capture bid below fair',pass:d5.action==='POST_YES_BID'&&d5.px<0.62,got:d5.action+' @'+d5.px});
  const posA={side:'YES',entryFair:0.9};
  const revOff = CFG.EXIT_SENT>=100;
  if(revOff){
    const eOff=decideExit({pos:posA,fair:0.6,sentPressure:-45,tauSec:200,condSince:Date.now()-15000});
    C.push({name:'reversal exits DISABLED (EXIT_SENT>=100) — never exits [expected]',pass:eOff.exit===false,got:'exit='+eOff.exit+' (EXIT_SENT='+CFG.EXIT_SENT+')'});
  } else {
    const eA=decideExit({pos:posA,fair:0.6,sentPressure:-45,tauSec:200,condSince:Date.now()-15000});
    const eB=decideExit({pos:posA,fair:0.85,sentPressure:-45,tauSec:200,condSince:Date.now()-15000});
    C.push({name:'persistent reversal exits; wiggle does not',pass:eA.exit===true&&eB.exit===false,got:eA.exit+'/'+eB.exit});
    const eC=decideExit({pos:posA,fair:0.6,sentPressure:-45,tauSec:200,condSince:Date.now()-2000});
    C.push({name:'v2.6 fresh reversal (2s) does NOT exit mid-window',pass:eC.exit===false&&eC.cond===true,got:eC.exit+'/'+eC.cond});
    const eD=decideExit({pos:posA,fair:0.6,sentPressure:-45,tauSec:45,condSince:Date.now()-2000});
    C.push({name:'v2.6 late-window fresh reversal DOES exit (no time to wait)',pass:eD.exit===true,got:String(eD.exit)});
  }
  const cg=makeCage();
  const smallLoss=-Math.min(1, Math.abs(CFG.DAILY_LOSS_LIMIT)/(CFG.MAX_CONSEC_LOSSES+1));
  for(let i=0;i<CFG.MAX_CONSEC_LOSSES;i++)cg.record(smallLoss);
  C.push({name:'cage: MAX_CONSEC_LOSSES consec losses → halted',pass:cg.halted()==='consecutive losses',got:String(cg.halted())+' (n='+CFG.MAX_CONSEC_LOSSES+', each '+smallLoss+')'});
  const cg2=makeCage();cg2.record(-250);
  C.push({name:'cage: daily loss limit → halted',pass:cg2.halted()==='daily loss limit',got:String(cg2.halted())});
  const st=[sessionTag(120),sessionTag(400),sessionTag(700),sessionTag(1200)].join(',');
  C.push({name:'session tags: overnight/prime/midday/evening',pass:st==='overnight,prime,midday,evening',got:st});
  const cA=closeMs({close_ts:1784392000}),cB=closeMs({close_time:'2026-07-18T16:00:00Z'});
  C.push({name:'closeMs parses close_ts and ISO close_time',pass:cA===1784392000000&&cB===Date.parse('2026-07-18T16:00:00Z'),got:cA+','+cB});
  const nbA=normalizeBook({orderbook_fp:{yes_dollars:[['0.1500','100.00'],['0.4200','13.00']],no_dollars:[['0.5600','17.00']]}});
  const nbB=normalizeBook({orderbook:{yes:[[15,100],[42,13]],no:[[56,17]]}});
  const okA=nbA&&Math.max(...nbA.yes.map(x=>x[0]))===0.42&&Math.max(...nbA.no.map(x=>x[0]))===0.56;
  const okB=nbB&&Math.max(...nbB.yes.map(x=>x[0]))===0.42;
  C.push({name:'normalizeBook parses fp-dollars and legacy-cents',pass:!!(okA&&okB),got:JSON.stringify(nbA&&nbA.yes)});
  const f_hi=decideEntry({fair:0.90,book:{yesAsk:0.75,noAsk:0.14,yesBid:0.72,noBid:0.1},tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.02,price:66150,strike:66000,volBps:0.30,fairStreak:99});
  C.push({name:'v2 filter PASSES fair>=0.85 favorite',pass:f_hi.action==='BUY_YES',got:f_hi.action});
  const inBandMid=(!CFG.FILTER_ON)||(0.84>=CFG.FAIR_MIN_HI||0.84<=CFG.FAIR_MAX_LO);
  C.push({name:'v2 filter: fair 0.84 OUTSIDE trade band',pass:inBandMid===false,got:'inBand='+inBandMid});
  const f_lo=decideEntry({fair:0.18,book:{yesAsk:0.07,noAsk:0.9,yesBid:0.05,noBid:0.88},tauSec:400,inHV:false,sentPressure:0,haveOpen:false});
  C.push({name:'v2.3 filter REJECTS longshots',pass:f_lo.action==='NONE',got:f_lo.action+' '+f_lo.reason});
  const badTrade=decideEntry({fair:0.90,book:{yesAsk:0.75,noAsk:0.19,yesBid:0.73,noBid:0.17},
    tauSec:427,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.015,price:65711,strike:65718.69,volBps:0.286,fairStreak:99});
  C.push({name:'v3.3 BLOCKS drift-manufactured trade',pass:badTrade.action==='NONE'&&/real cushion/.test(badTrade.reason),got:badTrade.action+' '+(badTrade.reason||'')});
  const goodTrade=decideEntry({fair:0.90,book:{yesAsk:0.75,noAsk:0.12,yesBid:0.73,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.02,price:66150,strike:66000,volBps:0.3,fairStreak:99});
  C.push({name:'v3.3 ALLOWS genuinely cushioned favorite',pass:goodTrade.action==='BUY_YES',got:goodTrade.action+' '+(goodTrade.reason||'')});
  const goodNo=decideEntry({fair:0.10,book:{yesAsk:0.90,noAsk:0.75,yesBid:0.88,noBid:0.73},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.02,price:65850,strike:66000,volBps:0.3,fairStreak:99});
  C.push({name:'v3.3 ALLOWS cushioned NO',pass:goodNo.action==='BUY_NO',got:goodNo.action+' '+(goodNo.reason||'')});
  const flicker=decideEntry({fair:0.90,book:{yesAsk:0.75,noAsk:0.12,yesBid:0.73,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.02,price:66150,strike:66000,volBps:0.3,fairStreak:1});
  C.push({name:'v3.3 REJECTS single-read flicker',pass:flicker.action==='NONE'&&/not stable/.test(flicker.reason),got:flicker.action+' '+(flicker.reason||'')});
  C.push({name:'v3.6 sym cal: fair 0.10 -> ~0.142',pass:Math.abs(calFair(0.10)-0.1424)<0.01,got:calFair(0.10).toFixed(4)});
  C.push({name:'v3.6 sym cal: raw 0.17 no longer floors',pass:calFair(0.17)>0.2,got:calFair(0.17).toFixed(4)});
  C.push({name:'v3.6 sym cal symmetric',pass:Math.abs(calFair(0.3)-(1-calFair(0.7)))<1e-9,got:calFair(0.3).toFixed(4)});
  const capY=decideEntry({fair:0.97,rawFair:0.97,book:{yesAsk:0.90,noAsk:0.05,yesBid:0.88,noBid:0.03},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.02,price:66300,strike:66000,volBps:0.3,fairStreak:99});
  C.push({name:'v3.7 px band blocks YES ask 0.90',pass:capY.action==='NONE'&&/edge band/.test(capY.reason),got:capY.action+' '+(capY.reason||'')});
  const cheap=decideEntry({fair:0.92,rawFair:0.94,book:{yesAsk:0.70,noAsk:0.22,yesBid:0.68,noBid:0.20},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.02,price:66150,strike:66000,volBps:0.3,fairStreak:99});
  C.push({name:'v3.7 px band BLOCKS cheap 0.70',pass:cheap.action==='NONE'&&/edge band/.test(cheap.reason),got:cheap.action+' '+(cheap.reason||'')});
  const vFloor=decideEntry({fair:0.90,rawFair:0.94,book:{yesAsk:0.75,noAsk:0.12,yesBid:0.73,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.10,fairStreak:99});
  C.push({name:'v4.1 F8 vol floor BLOCKS dead-calm 0.10',pass:vFloor.action==='NONE'&&/dead-calm/.test(vFloor.reason),got:vFloor.action+' '+(vFloor.reason||'')});
  const vOk=decideEntry({fair:0.90,rawFair:0.94,book:{yesAsk:0.75,noAsk:0.12,yesBid:0.73,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.22,fairStreak:99});
  C.push({name:'v4.1 F8 vol floor PASSES moderate 0.22',pass:vOk.action==='BUY_YES',got:vOk.action+' '+(vOk.reason||'')});
  const vCeil=decideEntry({fair:0.90,rawFair:0.92,book:{yesAsk:0.82,noAsk:0.12,yesBid:0.80,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.16,price:66150,strike:66000,volBps:0.72,fairStreak:99});
  C.push({name:'v4.2 F13 vol CEILING BLOCKS hot 0.72 (the -$4.92 63540 trade)',pass:vCeil.action==='NONE'&&/hot tape/.test(vCeil.reason),got:vCeil.action+' '+(vCeil.reason||'')});
  const vCeil2=decideEntry({fair:0.10,rawFair:0.08,book:{yesAsk:0.90,noAsk:0.82,yesBid:0.88,noBid:0.80},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.16,price:65850,strike:66000,volBps:0.65,fairStreak:99});
  C.push({name:'v4.2 F13 vol CEILING BLOCKS hot NO side (0.65)',pass:vCeil2.action==='NONE'&&/hot tape/.test(vCeil2.reason),got:vCeil2.action+' '+(vCeil2.reason||'')});
  const vCeilOk=decideEntry({fair:0.90,rawFair:0.94,book:{yesAsk:0.75,noAsk:0.12,yesBid:0.73,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.30,fairStreak:99});
  C.push({name:'v4.2 F13 vol ceiling PASSES calm 0.30 (edge zone intact)',pass:vCeilOk.action==='BUY_YES',got:vCeilOk.action+' '+(vCeilOk.reason||'')});
  const dTrust=decideEntry({fair:0.90,rawFair:0.94,book:{yesAsk:0.75,noAsk:0.12,yesBid:0.73,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.20,price:66150,strike:66000,volBps:0.40,fairStreak:99});
  C.push({name:'v4.2 F14 hot-tape (0.40) zeroes drift: YES not blocked by F9',pass:dTrust.action==='BUY_YES'||/hot tape/.test(dTrust.reason||''),got:dTrust.action+' '+(dTrust.reason||'')});
  const dTrustCalm=decideEntry({fair:0.90,rawFair:0.94,book:{yesAsk:0.75,noAsk:0.12,yesBid:0.73,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.05,price:66150,strike:66000,volBps:0.22,fairStreak:99});
  C.push({name:'v4.2 F14 calm-tape (0.22) still trusts drift: opposing-drift YES blocked',pass:dTrustCalm.action==='NONE'&&/opposes drift/.test(dTrustCalm.reason),got:dTrustCalm.action+' '+(dTrustCalm.reason||'')});
  const tailExempt=decideEntry({fair:0.97,rawFair:0.97,book:{yesAsk:0.93,noAsk:0.08,yesBid:0.92,noBid:0.06},
    tauSec:30,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.10,price:66300,strike:66000,volBps:0.72});
  C.push({name:'v4.2 tail-snipe EXEMPT from vol ceiling',pass:tailExempt.action==='BUY_YES'&&/tail-snipe/.test(tailExempt.reason),got:tailExempt.action+' '+(tailExempt.reason||'')});
  const doY=decideEntry({fair:0.90,rawFair:0.94,book:{yesAsk:0.75,noAsk:0.12,yesBid:0.73,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.05,price:66150,strike:66000,volBps:0.22,fairStreak:99});
  C.push({name:'v4.1 F9 BLOCKS YES opposing drift (calm tape)',pass:doY.action==='NONE'&&/opposes drift/.test(doY.reason),got:doY.action+' '+(doY.reason||'')});
  (function(){
    const sOn=CFG.REGIME_ON,sLb=CFG.REGIME_LOOKBACK,sMx=CFG.REGIME_MARGIN_MAX,saved=STATE.recentMargins;
    CFG.REGIME_ON=1;CFG.REGIME_LOOKBACK=5;CFG.REGIME_MARGIN_MAX=45;STATE.recentMargins=[];
    [80,90,100].forEach(pushRegimeMargin);
    C.push({name:'v4.1 F12 warm-up -> inactive',pass:regimeViolent()===false&&regimeMean()===null,got:'violent='+regimeViolent()});
    STATE.recentMargins=[];[60,20,15,10,25].forEach(pushRegimeMargin);
    C.push({name:'v4.1 F12 calm regime -> trades allowed',pass:regimeViolent()===false,got:'mean='+regimeMean()});
    STATE.recentMargins=[];[44,45,79,18,135].forEach(pushRegimeMargin);
    C.push({name:'v4.1 F12 violent regime -> STAND DOWN',pass:regimeViolent()===true,got:'mean='+regimeMean()});
    [10,10,10,10,10].forEach(pushRegimeMargin);
    C.push({name:'v4.1 F12 recovers on calm settles',pass:regimeViolent()===false,got:'mean='+regimeMean()});
    CFG.REGIME_ON=sOn;CFG.REGIME_LOOKBACK=sLb;CFG.REGIME_MARGIN_MAX=sMx;STATE.recentMargins=saved;
  })();
  (function(){
    const sOn=CFG.REGIME_ON,sLb=CFG.REGIME_LOOKBACK,sMx=CFG.REGIME_MARGIN_MAX,saved=STATE.recentMargins;
    CFG.REGIME_ON=1;CFG.REGIME_LOOKBACK=5;CFG.REGIME_MARGIN_MAX=45;STATE.recentMargins=[];
    [80,90,100,70,60].forEach(pushRegimeMargin);
    const stuck=regimeViolent();
    [10,12,8,15,11].forEach(pushRegimeMargin);
    const freed=regimeViolent();
    C.push({name:'v4.5 regime deadlock: violent then calm OBSERVED settles -> resumes',pass:stuck===true&&freed===false,got:'stuck='+stuck+' freed='+freed});
    CFG.REGIME_ON=sOn;CFG.REGIME_LOOKBACK=sLb;CFG.REGIME_MARGIN_MAX=sMx;STATE.recentMargins=saved;
  })();
  (function(){
    const cgN=makeCage();cgN.record(NaN);cgN.record(-30);cgN.record(NaN);cgN.adjust(NaN);cgN.record(-30);cgN.record(-30);cgN.record(-30);
    C.push({name:'v4.1 F10 cage survives NaN',pass:Number.isFinite(cgN.realized)&&cgN.realized===-120&&cgN.halted()!==null,got:'realized='+cgN.realized});
  })();
  C.push({name:'v3.0 defaults to DRY RUN',pass:CFG.LIVE===false||process.env.LIVE!==undefined,got:'LIVE='+CFG.LIVE});
  const tp=truthPnl({mode:'taker',entryPx:0.79,qty:10},false);
  C.push({name:'truthPnl flips phantom win to real loss',pass:Math.abs(tp-(-8.02))<0.02,got:tp});
  const gLoss=decideEntry({fair:0.94,rawFair:0.94,book:{yesAsk:0.85,noAsk:0.12,yesBid:0.83,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:64100,strike:64000,volBps:0.30,fairStreak:99});
  C.push({name:'v4.4 F17 BLOCKS thin gap (the -$5 YES @0.85, gap 0.09)',pass:gLoss.action==='NONE'&&/gap/.test(gLoss.reason),got:gLoss.action+' '+(gLoss.reason||'')});
  const gGood=decideEntry({fair:0.90,rawFair:0.90,book:{yesAsk:0.75,noAsk:0.12,yesBid:0.73,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.30,fairStreak:99});
  C.push({name:'v4.4 F17 PASSES sweet-spot gap 0.14',pass:gGood.action==='BUY_YES',got:gGood.action+' '+(gGood.reason||'')});
  const gBig=decideEntry({fair:0.96,rawFair:0.96,book:{yesAsk:0.70,noAsk:0.22,yesBid:0.68,noBid:0.20},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.30,fairStreak:99});
  C.push({name:'v4.4 F17 BLOCKS oversized gap 0.26 (model hallucinating)',pass:gBig.action==='NONE'&&/gap/.test(gBig.reason),got:gBig.action+' '+(gBig.reason||'')});
  const gNo=decideEntry({fair:0.10,rawFair:0.10,book:{yesAsk:0.90,noAsk:0.75,yesBid:0.88,noBid:0.73},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.03,price:65850,strike:66000,volBps:0.30,fairStreak:99});
  C.push({name:'v4.4 F17 NO-side sweet-spot gap 0.14 trades',pass:gNo.action==='BUY_NO',got:gNo.action+' '+(gNo.reason||'')});
  const mk=decideEntry({fair:0.894,rawFair:0.894,book:{yesAsk:0.83,noAsk:0.14,yesBid:0.80,noBid:0.12},
    tauSec:114,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:64300,strike:64306,volBps:0.30,fairStreak:99});
  C.push({name:'v4.5 maker cap BLOCKS the -$4.88 trade (fair 0.894 -> bid 0.81 > 0.78)',pass:!(mk.action==='POST_YES_BID')&&!(mk.action==='BUY_YES'),got:mk.action+' '+(mk.reason||'')});
  const mk2=decideEntry({fair:0.84,rawFair:0.84,book:{yesAsk:0.80,noAsk:0.14,yesBid:0.74,noBid:0.12},
    tauSec:120,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:64300,strike:64200,volBps:0.30,fairStreak:99});
  C.push({name:'v4.5 maker still posts when bid in band (fair 0.84 -> bid 0.76)',pass:mk2.action==='POST_YES_BID',got:mk2.action+' '+(mk2.reason||'')});
  (function(){const sv=CFG.GAP_MIN;CFG.GAP_MIN=0;
    const off=decideEntry({fair:0.94,rawFair:0.94,book:{yesAsk:0.85,noAsk:0.12,yesBid:0.83,noBid:0.10},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:64100,strike:64000,volBps:0.30,fairStreak:99});
    C.push({name:'v4.4 F17 GAP_MIN=0 disables gate',pass:!/gap/.test(off.reason||''),got:off.action+' '+(off.reason||'')});
    CFG.GAP_MIN=sv;})();
  const lx1=decideLateExit({side:'YES',strike:66000,tauSec:10,lockedAvg:65880,elapsedSec:50,
    price:65885,volBps:0.30,book:{yesBid:0.18,noBid:0.80},K:2.0,minSalvage:0.03});
  C.push({name:'v4.3 F16 FIRES on decided YES loss (locked avg below strike, 10s left)',pass:lx1.exit===true&&/locked avg decides/.test(lx1.reason),got:(lx1.exit)+' '+(lx1.reason||'')});
  const lx2=decideLateExit({side:'YES',strike:66000,tauSec:55,lockedAvg:65995,elapsedSec:5,
    price:65996,volBps:0.30,book:{yesBid:0.4,noBid:0.6},K:2.0,minSalvage:0.03});
  C.push({name:'v4.3 F16 does NOT fire when recoverable (55s left, near strike)',pass:lx2.exit===false,got:lx2.exit+' '+(lx2.reason||'')});
  const lx3=decideLateExit({side:'YES',strike:66000,tauSec:10,lockedAvg:66200,elapsedSec:50,
    price:66210,volBps:0.30,book:{yesBid:0.95,noBid:0.05},K:2.0,minSalvage:0.03});
  C.push({name:'v4.3 F16 NEVER fires on a winning position',pass:lx3.exit===false,got:lx3.exit+' '+(lx3.reason||'')});
  const lx4=decideLateExit({side:'NO',strike:66000,tauSec:10,lockedAvg:66150,elapsedSec:50,
    price:66155,volBps:0.30,book:{yesBid:0.85,noBid:0.14},K:2.0,minSalvage:0.03});
  C.push({name:'v4.3 F16 FIRES on decided NO loss (locked avg above strike)',pass:lx4.exit===true,got:lx4.exit+' '+(lx4.reason||'')});
  const lx5=decideLateExit({side:'YES',strike:66000,tauSec:10,lockedAvg:65880,elapsedSec:50,
    price:65885,volBps:0.30,book:{yesBid:0.01,noBid:0.98},K:2.0,minSalvage:0.03});
  C.push({name:'v4.3 F16 holds if decided loss but no salvage bid',pass:lx5.exit===false&&/no salvage/.test(lx5.reason),got:lx5.exit+' '+(lx5.reason||'')});
  const lx6=decideLateExit({side:'YES',strike:66000,tauSec:45,lockedAvg:65992,elapsedSec:15,
    price:65997,volBps:0.5,book:{yesBid:0.4,noBid:0.6},K:2.0,minSalvage:0.03});
  C.push({name:'v4.3 F16 recoverable (45s of weight left) -> does NOT fire',pass:lx6.exit===false,got:lx6.exit+' '+(lx6.reason||'')});
  const lx7=decideLateExit({side:'YES',strike:66000,tauSec:10,lockedAvg:65992,elapsedSec:50,
    price:65997,volBps:0.5,book:{yesBid:0.3,noBid:0.7},K:2.0,minSalvage:0.03});
  C.push({name:'v4.3 F16 same deficit but 10s left -> leverage decides loss -> fires',pass:lx7.exit===true,got:lx7.exit+' '+(lx7.reason||'')});
  (function(){
    const saved=STATE.basisSamples, sOn=CFG.BASIS_ON, sK=CFG.BASIS_HAIRCUT_K, sMan=CFG.BASIS_MANUAL, sLb=CFG.BASIS_LOOKBACK;
    CFG.BASIS_ON=1; CFG.BASIS_HAIRCUT_K=1.0; CFG.BASIS_MANUAL=0; CFG.BASIS_LOOKBACK=20;
    STATE.basisSamples=[];
    pushBasis(-8); pushBasis(-10);
    C.push({name:'v4.6 F18 <3 samples -> basis 0 (inert)',pass:currentBasis()===0,got:'basis='+currentBasis()});
    pushBasis(-12);
    C.push({name:'v4.6 F18 rolling median of [-8,-10,-12] = -10',pass:currentBasis()===-10,got:currentBasis()});
    CFG.BASIS_MANUAL=-7;
    C.push({name:'v4.6 F18 manual override wins',pass:currentBasis()===-7,got:currentBasis()});
    CFG.BASIS_MANUAL=0;
    STATE.basisSamples=[-10,-10,-10];
    const noArgs=b=>({fair:0.12,rawFair:0.02,book:{yesAsk:0.88,noAsk:0.72,yesBid:0.86,noBid:0.70},
      tauSec:250,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.03,price:63464,strike:63500,volBps:0.24,fairStreak:99,basis:b});
    const noBasis0=(function(){const s=CFG.BASIS_ON;CFG.BASIS_ON=0;const d=decideEntry(noArgs(0));CFG.BASIS_ON=s;return d;})();
    const noBasisOn=decideEntry(noArgs(-14));
    C.push({name:'v4.6 F18 near-strike NO admitted at basis 0 is BLOCKED at basis -14',
      pass:noBasis0.action==='BUY_NO' && noBasisOn.action==='NONE' && /cushion/.test(noBasisOn.reason||''),
      got:'basis0='+noBasis0.action+' | basisOn='+noBasisOn.action+' '+(noBasisOn.reason||'')});
    const yesUnaff=decideEntry({fair:0.90,rawFair:0.94,book:{yesAsk:0.75,noAsk:0.12,yesBid:0.73,noBid:0.10},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.30,fairStreak:99,basis:-14});
    C.push({name:'v4.6 F18 YES entry unaffected by NO haircut',pass:yesUnaff.action==='BUY_YES',got:yesUnaff.action});
    const noDeep=decideEntry({fair:0.10,rawFair:0.02,book:{yesAsk:0.90,noAsk:0.74,yesBid:0.88,noBid:0.72},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.03,price:65840,strike:66000,volBps:0.22,fairStreak:99,basis:-14});
    C.push({name:'v4.6 F18 deep-cushion NO still trades through basis correction',pass:noDeep.action==='BUY_NO',got:noDeep.action+' '+(noDeep.reason||'')});
    CFG.BASIS_HAIRCUT_K=0;
    const noK0=decideEntry(noArgs(-14));
    C.push({name:'v4.6 F18 HAIRCUT_K=0 path runs (price-correction only)',pass:noK0.action==='NONE'||noK0.action==='BUY_NO',got:'K0 action='+noK0.action});
    CFG.BASIS_HAIRCUT_K=sK; CFG.BASIS_ON=sOn; CFG.BASIS_MANUAL=sMan; CFG.BASIS_LOOKBACK=sLb; STATE.basisSamples=saved;
  })();
  (function(){
    const s=CFG.YES_ON;
    const yesArgs={fair:0.90,rawFair:0.94,book:{yesAsk:0.72,noAsk:0.12,yesBid:0.70,noBid:0.10},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.30,fairStreak:99,basis:0};
    CFG.YES_ON=1; const on=decideEntry(yesArgs);
    CFG.YES_ON=0; const off=decideEntry(yesArgs);
    C.push({name:'v4.7 F19 YES trades when YES_ON=1',pass:on.action==='BUY_YES',got:on.action});
    C.push({name:'v4.7 F19 YES BLOCKED when YES_ON=0',pass:off.action==='NONE',got:off.action+' '+(off.reason||'')});
    const noArgs={fair:0.10,rawFair:0.02,book:{yesAsk:0.90,noAsk:0.72,yesBid:0.88,noBid:0.70},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.03,price:65840,strike:66000,volBps:0.22,fairStreak:99,basis:0};
    CFG.YES_ON=0; const noStill=decideEntry(noArgs);
    C.push({name:'v4.7 F19 NO still trades when YES_ON=0',pass:noStill.action==='BUY_NO',got:noStill.action+' '+(noStill.reason||'')});
    CFG.YES_ON=s;
  })();
  (function(){
    const sMin=CFG.YES_AF_MIN, sN=CFG.YES_AF_N, sBuf=STATE.recentMargins;
    CFG.YES_AF_MIN=0.55; CFG.YES_AF_N=10;
    const yesArgs=af=>({fair:0.90,rawFair:0.94,book:{yesAsk:0.72,noAsk:0.12,yesBid:0.70,noBid:0.10},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.30,fairStreak:99,basis:0,aboveFrac:af});
    const blk=decideEntry(yesArgs(0.30));
    C.push({name:'v4.8 F20 YES BLOCKED at above-frac 0.30 (bearish tape)',pass:blk.action==='NONE'&&/regime gate/.test(blk.reason||''),got:blk.action+' '+(blk.reason||'')});
    const ok=decideEntry(yesArgs(0.70));
    C.push({name:'v4.8 F20 YES ALLOWED at above-frac 0.70 (bullish tape)',pass:ok.action==='BUY_YES',got:ok.action});
    const warm=decideEntry(yesArgs(null));
    C.push({name:'v4.8 F20 warmup (af null) -> inert, YES allowed',pass:warm.action==='BUY_YES',got:warm.action});
    const noArgs={fair:0.10,rawFair:0.02,book:{yesAsk:0.90,noAsk:0.72,yesBid:0.88,noBid:0.70},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.03,price:65840,strike:66000,volBps:0.22,fairStreak:99,basis:0,aboveFrac:0.30};
    const noUn=decideEntry(noArgs);
    C.push({name:'v4.8 F20 NO unaffected by regime gate',pass:noUn.action==='BUY_NO',got:noUn.action+' '+(noUn.reason||'')});
    CFG.YES_AF_MIN=0; const inert=decideEntry(yesArgs(0.10));
    C.push({name:'v4.8 F20 default YES_AF_MIN=0 -> fully inert',pass:inert.action==='BUY_YES',got:inert.action});
    STATE.recentMargins=[-10,-5,8,-3,12,-7,-9,4,-2,-6];
    const afv=aboveFrac();
    C.push({name:'v4.8 aboveFrac computes sign fraction (3/10=0.3)',pass:Math.abs(afv-0.3)<1e-9,got:afv});
    STATE.recentMargins=[-10,-5];
    C.push({name:'v4.8 aboveFrac null under 4 samples',pass:aboveFrac()===null,got:String(aboveFrac())});
    CFG.YES_AF_MIN=sMin; CFG.YES_AF_N=sN; STATE.recentMargins=sBuf;
  })();
  (function(){
    const sD=CFG.NO_DRIFT_MAX, sA=CFG.NO_AF_MAX, sVol=CFG.VOL_MAX_ENTER;
    CFG.NO_DRIFT_MAX=0.03; CFG.NO_AF_MAX=0.5; CFG.VOL_MAX_ENTER=0.45;
    const noUp={fair:0.10,rawFair:0.02,book:{yesAsk:0.90,noAsk:0.72,yesBid:0.88,noBid:0.70},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.086,price:65840,strike:66000,volBps:0.389,fairStreak:99,basis:0,aboveFrac:0.5};
    const blkD=decideEntry(noUp);
    C.push({name:'v4.9 F21 NO into up-drift 0.086 in HOT tape BLOCKED (raw drift, 041145 hole)',pass:blkD.action==='NONE'&&/F21/.test(blkD.reason||''),got:blkD.action+' '+(blkD.reason||'')});
    const noBull={fair:0.10,rawFair:0.02,book:{yesAsk:0.90,noAsk:0.72,yesBid:0.88,noBid:0.70},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.02,price:65840,strike:66000,volBps:0.22,fairStreak:99,basis:0,aboveFrac:0.7};
    const blkA=decideEntry(noBull);
    C.push({name:'v4.9 F21 NO in bullish tape (af 0.7) BLOCKED',pass:blkA.action==='NONE'&&/F21/.test(blkA.reason||''),got:blkA.action+' '+(blkA.reason||'')});
    const noOk={fair:0.10,rawFair:0.02,book:{yesAsk:0.90,noAsk:0.72,yesBid:0.88,noBid:0.70},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.03,price:65840,strike:66000,volBps:0.22,fairStreak:99,basis:0,aboveFrac:0.3};
    const ok=decideEntry(noOk);
    C.push({name:'v4.9 F21 NO in bearish tape+down-drift ALLOWED',pass:ok.action==='BUY_NO',got:ok.action+' '+(ok.reason||'')});
    const yesUn={fair:0.90,rawFair:0.94,book:{yesAsk:0.72,noAsk:0.12,yesBid:0.70,noBid:0.10},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.30,fairStreak:99,basis:0,aboveFrac:0.7};
    const yUn=decideEntry(yesUn);
    C.push({name:'v4.9 F21 YES unaffected by NO gate',pass:yUn.action==='BUY_YES',got:yUn.action});
    CFG.NO_DRIFT_MAX=99; CFG.NO_AF_MAX=1;
    const inert=decideEntry(noUp);
    C.push({name:'v4.9 F21 default (driftMax=99,afMax=1) -> inert, NO allowed',pass:inert.action==='BUY_NO',got:inert.action+' '+(inert.reason||'')});
    CFG.NO_DRIFT_MAX=sD; CFG.NO_AF_MAX=sA; CFG.VOL_MAX_ENTER=sVol;
  })();
  (function(){
    const sV=CFG.REV_VIOLENCE_MAX, sN=CFG.REV_N, sVol=CFG.VOL_MAX_ENTER, sBuf=STATE.recentMargins;
    CFG.REV_VIOLENCE_MAX=60; CFG.REV_N=10; CFG.VOL_MAX_ENTER=0.36;
    const yes=ev=>({fair:0.90,rawFair:0.94,book:{yesAsk:0.72,noAsk:0.12,yesBid:0.70,noBid:0.10},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.30,fairStreak:99,basis:0,aboveFrac:0.7,entryViolence:ev});
    const blk=decideEntry(yes(75));
    C.push({name:'v4.10 F22 blocks entry when violence 75 >= 60',pass:blk.action==='NONE'&&/reversal filter/.test(blk.reason||''),got:blk.action+' '+(blk.reason||'')});
    const ok=decideEntry(yes(30));
    C.push({name:'v4.10 F22 allows entry when violence 30 < 60',pass:ok.action==='BUY_YES',got:ok.action});
    const bnd=decideEntry(yes(60));
    C.push({name:'v4.10 F22 boundary violence=60 blocks (>=)',pass:bnd.action==='NONE',got:bnd.action});
    C.push({name:'v4.10 F22 boundary violence=59 allows',pass:decideEntry(yes(59)).action==='BUY_YES',got:decideEntry(yes(59)).action});
    const hotVol=decideEntry({...yes(30),volBps:0.40});
    C.push({name:'v4.10 F22 vol ceiling 0.36 blocks vol 0.40',pass:hotVol.action==='NONE',got:hotVol.action+' '+(hotVol.reason||'')});
    const noV={fair:0.10,rawFair:0.02,book:{yesAsk:0.90,noAsk:0.72,yesBid:0.88,noBid:0.70},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.03,price:65840,strike:66000,volBps:0.22,fairStreak:99,basis:0,aboveFrac:0.3,entryViolence:80};
    C.push({name:'v4.10 F22 NO also blocked by violence gate',pass:decideEntry(noV).action==='NONE',got:decideEntry(noV).action});
    CFG.REV_VIOLENCE_MAX=999; CFG.VOL_MAX_ENTER=0.45;
    C.push({name:'v4.10 F22 default inert (violence 999) allows',pass:decideEntry(yes(500)).action==='BUY_YES',got:decideEntry(yes(500)).action});
    STATE.recentMargins=[-100,50,-80,120,-40,60,-90,30,-70,110];
    const ev=entryViolence(); const exp=(100+50+80+120+40+60+90+30+70+110)/10;
    C.push({name:'v4.10 entryViolence mean|margin| correct',pass:Math.abs(ev-exp)<1e-9,got:ev});
    STATE.recentMargins=[-10,5]; C.push({name:'v4.10 entryViolence null <4 samples',pass:entryViolence()===null,got:String(entryViolence())});
    CFG.REV_VIOLENCE_MAX=sV; CFG.REV_N=sN; CFG.VOL_MAX_ENTER=sVol; STATE.recentMargins=sBuf;
  })();
  (function(){
    const sBuf=STATE.recentMargins, sW=CFG.REGIME_WARMUP, sLb=CFG.REGIME_LOOKBACK, sViol=CFG.REV_VIOLENCE_MAX, sVol=CFG.VOL_MAX_ENTER;
    CFG.REGIME_WARMUP=1; CFG.REGIME_LOOKBACK=5; CFG.REV_VIOLENCE_MAX=999; CFG.VOL_MAX_ENTER=0.45;
    const yes={fair:0.90,rawFair:0.94,book:{yesAsk:0.72,noAsk:0.12,yesBid:0.70,noBid:0.10},tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.25,fairStreak:99,basis:0,aboveFrac:0.7,entryViolence:10};
    STATE.recentMargins=[10,-5];
    const cold=decideEntry(yes);
    C.push({name:'v4.11 F23 cold buffer (2<5) stands down',pass:cold.action==='NONE'&&/warmup/.test(cold.reason||''),got:cold.action+' '+(cold.reason||'')});
    STATE.recentMargins=[10,-5,8,-3,12];
    C.push({name:'v4.11 F23 warm buffer (5>=5) allows',pass:decideEntry(yes).action==='BUY_YES',got:decideEntry(yes).action});
    STATE.recentMargins=[]; CFG.REGIME_WARMUP=0;
    C.push({name:'v4.11 F23 disabled (warmup=0) allows when cold',pass:decideEntry(yes).action==='BUY_YES',got:decideEntry(yes).action});
    const savedLog=process.env.LOG_PATH; process.env.LOG_PATH='/tmp/__nope_'+Date.now()+'.jsonl';
    let seededN; try{seededN=seedRegimeFromLog();}catch(e){seededN='THREW';}
    C.push({name:'v4.11 F23 seedRegimeFromLog no-throw',pass:typeof seededN==='number',got:String(seededN)});
    if(savedLog===undefined)delete process.env.LOG_PATH; else process.env.LOG_PATH=savedLog;
    const sSet=STATE.settledTickers, sRM=STATE.recentMargins;
    STATE.settledTickers=[]; STATE.recentMargins=[];
    const first=markSettled('KXBTC15M-26AUG051345-45'); if(first)pushRegimeMargin(99.05);
    const second=markSettled('KXBTC15M-26AUG051345-45'); if(second)pushRegimeMargin(99.05);
    C.push({name:'v4.12 dup fix: 1st settle pushes, 2nd is deduped',pass:first===true&&second===false&&STATE.recentMargins.length===1,got:'first='+first+' second='+second+' len='+STATE.recentMargins.length});
    C.push({name:'v4.12 dup fix: different ticker still pushes',pass:markSettled('KXBTC15M-26AUG051400-00')===true,got:'ok'});
    STATE.recentMargins=[]; const pLen0=STATE.recentMargins.length;
    pushRegimeMargin(64489.16); const pAfterPoison=STATE.recentMargins.length;
    pushRegimeMargin(42.6); const pAfterGood=STATE.recentMargins.length;
    C.push({name:'v4.13 F25 poison margin dropped, normal kept',pass:pLen0===0&&pAfterPoison===0&&pAfterGood===1,got:'poison->'+pAfterPoison+' good->'+pAfterGood});
    STATE.recentMargins=[]; pushRegimeMargin(-603.3);
    C.push({name:'v4.13 F25 real max-magnitude margin survives',pass:STATE.recentMargins.length===1,got:'len='+STATE.recentMargins.length});
    STATE.settledTickers=sSet; STATE.recentMargins=sRM;
    CFG.REGIME_WARMUP=sW; CFG.REGIME_LOOKBACK=sLb; CFG.REV_VIOLENCE_MAX=sViol; CFG.VOL_MAX_ENTER=sVol; STATE.recentMargins=sBuf;
  })();
  (function(){
    const sT=CFG.MIN_TAU_TRADE, sBuf=STATE.recentMargins;
    STATE.recentMargins=[10,-5,8,-3,12];
    CFG.MIN_TAU_TRADE=300;
    const yes=tau=>({fair:0.90,rawFair:0.94,book:{yesAsk:0.72,noAsk:0.12,yesBid:0.70,noBid:0.10},tauSec:tau,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.25,fairStreak:99,basis:0,aboveFrac:0.7,entryViolence:10});
    C.push({name:'v4.11 F24 tau 245 < 300 blocked',pass:decideEntry(yes(245)).action==='NONE'&&/late entry/.test(decideEntry(yes(245)).reason||''),got:decideEntry(yes(245)).action});
    C.push({name:'v4.11 F24 tau 400 >= 300 allowed',pass:decideEntry(yes(400)).action==='BUY_YES',got:decideEntry(yes(400)).action});
    C.push({name:'v4.11 F24 boundary tau=300 allowed',pass:decideEntry(yes(300)).action==='BUY_YES',got:decideEntry(yes(300)).action});
    C.push({name:'v4.11 F24 boundary tau=299 blocked',pass:decideEntry(yes(299)).action==='NONE',got:decideEntry(yes(299)).action});
    CFG.MIN_TAU_TRADE=0;
    C.push({name:'v4.11 F24 default inert (0) allows tau 100',pass:decideEntry(yes(100)).action==='BUY_YES',got:decideEntry(yes(100)).action});
    CFG.MIN_TAU_TRADE=sT; STATE.recentMargins=sBuf;
  })();
  // ---- v4.15 F26 STRIKE-POISON GUARD ----
  (function(){
    // the exact live poison: minute-suffix ticker, no strike fields -> must be NaN (window skipped)
    C.push({name:'v4.15 F26 rejects minute-suffix -45 as strike (the 64847 poison source)',
      pass:Number.isNaN(parseStrike({ticker:'KXBTC15M-26AUG072145-45'})),
      got:String(parseStrike({ticker:'KXBTC15M-26AUG072145-45'}))});
    C.push({name:'v4.15 F26 rejects suffix -15',pass:Number.isNaN(parseStrike({ticker:'KXBTC15M-26AUG072215-15'})),got:String(parseStrike({ticker:'KXBTC15M-26AUG072215-15'}))});
    C.push({name:'v4.15 F26 rejects suffix -00',pass:Number.isNaN(parseStrike({ticker:'KXBTC15M-26AUG072200-00'})),got:String(parseStrike({ticker:'KXBTC15M-26AUG072200-00'}))});
    // real strike fields still win (unchanged behavior)
    C.push({name:'v4.15 F26 floor_strike still parses',pass:parseStrike({floor_strike:64850,ticker:'KXBTC15M-26AUG072145-45'})===64850,got:String(parseStrike({floor_strike:64850,ticker:'KXBTC15M-26AUG072145-45'}))});
    C.push({name:'v4.15 F26 cap_strike still parses',pass:parseStrike({cap_strike:65000,ticker:'KXBTC15M-26AUG072145-45'})===65000,got:String(parseStrike({cap_strike:65000,ticker:'KXBTC15M-26AUG072145-45'}))});
    C.push({name:'v4.15 F26 strike field still parses',pass:parseStrike({strike:63500.5,ticker:'X-45'})===63500.5,got:String(parseStrike({strike:63500.5,ticker:'X-45'}))});
    // a legit tail-encoded dollar strike (>=$1000) still parses for other series
    C.push({name:'v4.15 F26 legit tail strike 64000 still parses',pass:parseStrike({ticker:'KXSOMETHING-26AUG07-64000'})===64000,got:String(parseStrike({ticker:'KXSOMETHING-26AUG07-64000'}))});
    // downstream safety: a NaN strike must make computeFair return null (no phantom ~1.0 fair)
    const fairPoison=computeFair({price:64862,strike:parseStrike({ticker:'KXBTC15M-26AUG072215-15'}),tauSec:400,volBps:0.3,driftBps:0,knownAvg:null,knownDur:0});
    C.push({name:'v4.15 F26 poison strike -> computeFair null (no phantom edge)',pass:fairPoison===null,got:String(fairPoison)});
    // and a real strike still computes a sane fair
    const fairReal=computeFair({price:64862,strike:64850,tauSec:400,volBps:0.3,driftBps:0,knownAvg:null,knownDur:0});
    C.push({name:'v4.15 F26 real strike -> computeFair returns a number',pass:Number.isFinite(fairReal),got:String(round(fairReal,3))});
    // guard is env-tunable: lowering STRIKE_SANE_MIN below the suffix would re-admit it (proves the knob works)
    C.push({name:'v4.15 F26 boundary: value exactly STRIKE_SANE_MIN parses',pass:parseStrike({ticker:'X-'+STRIKE_SANE_MIN})===STRIKE_SANE_MIN,got:String(parseStrike({ticker:'X-'+STRIKE_SANE_MIN}))});
    C.push({name:'v4.15 F26 boundary: value just below floor rejected',pass:Number.isNaN(parseStrike({ticker:'X-'+(STRIKE_SANE_MIN-1)})),got:String(parseStrike({ticker:'X-'+(STRIKE_SANE_MIN-1)}))});
  })();
  // ---- v4.16 F28 TREND-ALIGNED REGIME OVERRIDE ----
  (function(){
    const sOn=CFG.REGIME_ON,sLb=CFG.REGIME_LOOKBACK,sMx=CFG.REGIME_MARGIN_MAX,sOv=CFG.REGIME_TREND_OVERRIDE,sC=CFG.REGIME_TREND_CONSIST,sW=CFG.REGIME_WARMUP,sBuf=STATE.recentMargins;
    CFG.REGIME_ON=1;CFG.REGIME_LOOKBACK=5;CFG.REGIME_MARGIN_MAX=45;CFG.REGIME_WARMUP=0;CFG.REGIME_TREND_CONSIST=0.5;
    // regimeTrend math: pure up-trend -> consistency 1, trendSign +1
    STATE.recentMargins=[100,120,90,110,130];
    let rt=regimeTrend();
    C.push({name:'v4.16 F28 regimeTrend: pure up-trend -> consistency 1.0, sign +',pass:rt&&Math.abs(rt.consistency-1)<1e-9&&rt.trendSign===1,got:rt?('c='+round(rt.consistency,2)+' s='+rt.trendSign):'null'});
    // pure chop (alternating) -> consistency ~0
    STATE.recentMargins=[100,-100,100,-100,100];
    rt=regimeTrend();
    C.push({name:'v4.16 F28 regimeTrend: alternating chop -> consistency low (<0.25)',pass:rt&&rt.consistency<0.25,got:rt?('c='+round(rt.consistency,2)):'null'});
    // down-trend -> sign -1
    STATE.recentMargins=[-100,-120,-90,-110,-130];
    rt=regimeTrend();
    C.push({name:'v4.16 F28 regimeTrend: down-trend -> sign -',pass:rt&&rt.trendSign===-1&&rt.consistency>0.9,got:rt?('c='+round(rt.consistency,2)+' s='+rt.trendSign):'null'});
    C.push({name:'v4.16 F28 regimeTrend null when buffer short',pass:(STATE.recentMargins=[100,-100],regimeTrend()===null),got:'ok'});

    // Entry-level behavior. A violent regime (mean|margin| 110 > 45) that is a CLEAN UP-TREND.
    const upTrend=[100,120,90,110,130]; // regimeMean 110 -> violent; consistency 1, sign +
    const yesAligned={fair:0.90,rawFair:0.94,book:{yesAsk:0.72,noAsk:0.12,yesBid:0.70,noBid:0.10},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.30,fairStreak:99,basis:0,aboveFrac:0.7,entryViolence:10};
    // OVERRIDE OFF -> identical to 4.15: stands down
    CFG.REGIME_TREND_OVERRIDE=0; STATE.recentMargins=upTrend.slice();
    const off=decideEntry(yesAligned);
    C.push({name:'v4.16 F28 OFF (default) -> stands down in violent up-trend (4.15 behavior)',pass:off.action==='NONE'&&/stand-down/.test(off.reason||''),got:off.action+' '+(off.reason||'')});
    // OVERRIDE ON, YES lean aligns with up-trend, high conviction -> rides (trades)
    CFG.REGIME_TREND_OVERRIDE=1; STATE.recentMargins=upTrend.slice();
    const rideY=decideEntry(yesAligned);
    C.push({name:'v4.16 F28 ON + YES lean aligned w/ up-trend + high conv -> TRADES',pass:rideY.action==='BUY_YES',got:rideY.action+' '+(rideY.reason||'')});
    // OVERRIDE ON but COUNTER-TREND: NO lean (fair 0.10) into an up-trend -> still stands down
    const noCounter={...yesAligned,fair:0.10,rawFair:0.02,book:{yesAsk:0.90,noAsk:0.72,yesBid:0.88,noBid:0.70},driftBps:-0.03,price:65840,aboveFrac:0.3};
    STATE.recentMargins=upTrend.slice();
    const ctr=decideEntry(noCounter);
    C.push({name:'v4.16 F28 ON + NO lean AGAINST up-trend -> STANDS DOWN (counter-trend blocked)',pass:ctr.action==='NONE'&&/stand-down/.test(ctr.reason||''),got:ctr.action+' '+(ctr.reason||'')});
    // OVERRIDE ON but CHOP: high |margin| but alternating -> stands down even if aligned/high-conv
    STATE.recentMargins=[100,-100,120,-110,130]; // mean|m|~112 violent, consistency ~0.08 chop, sum + so trendSign +
    const chop=decideEntry(yesAligned);
    C.push({name:'v4.16 F28 ON + chop (low consistency) -> STANDS DOWN even if lean matches',pass:chop.action==='NONE'&&/stand-down/.test(chop.reason||''),got:chop.action+' '+(chop.reason||'')});
    // OVERRIDE ON, aligned trend, but LOW conviction (fair 0.60) -> stands down
    const lowConv={...yesAligned,fair:0.60,rawFair:0.60};
    STATE.recentMargins=upTrend.slice();
    const lc=decideEntry(lowConv);
    C.push({name:'v4.16 F28 ON + aligned trend but low conviction (0.60) -> STANDS DOWN',pass:lc.action==='NONE'&&/stand-down/.test(lc.reason||''),got:lc.action+' '+(lc.reason||'')});
    // NO-side symmetric: clean DOWN-trend + NO lean (fair 0.10) aligned + high conv -> trades
    CFG.REGIME_TREND_OVERRIDE=1; STATE.recentMargins=[-100,-120,-90,-110,-130];
    const noAligned={fair:0.10,rawFair:0.02,book:{yesAsk:0.90,noAsk:0.72,yesBid:0.88,noBid:0.70},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.03,price:65840,strike:66000,volBps:0.22,fairStreak:99,basis:0,aboveFrac:0.3,entryViolence:10};
    const rideN=decideEntry(noAligned);
    C.push({name:'v4.16 F28 ON + NO lean aligned w/ down-trend + high conv -> TRADES',pass:rideN.action==='BUY_NO',got:rideN.action+' '+(rideN.reason||'')});
    // once past the override, the NORMAL gates still apply: aligned trend but a normal gate still blocks.
    // Use a dead-calm vol so the freed trade is rejected by the vol floor (proves override != auto-trade).
    CFG.REGIME_TREND_OVERRIDE=1; STATE.recentMargins=upTrend.slice();
    const calmVol={...yesAligned,volBps:0.10};
    const cv=decideEntry(calmVol);
    C.push({name:'v4.16 F28 ON: freed trade still subject to normal gates (dead-calm vol floor blocks)',pass:cv.action==='NONE'&&/dead-calm/.test(cv.reason||''),got:cv.action+' '+(cv.reason||'')});
    CFG.REGIME_ON=sOn;CFG.REGIME_LOOKBACK=sLb;CFG.REGIME_MARGIN_MAX=sMx;CFG.REGIME_TREND_OVERRIDE=sOv;CFG.REGIME_TREND_CONSIST=sC;CFG.REGIME_WARMUP=sW;STATE.recentMargins=sBuf;
  })();
  // ---- v4.16 F29 JUMP-DIFFUSION TAIL ----
  (function(){
    const sOn=CFG.JUMP_ON,sL=CFG.JUMP_LAMBDA,sK=CFG.JUMP_K;
    // OFF => survFn is pure normCdf => computeFair identical to 4.15
    CFG.JUMP_ON=0;
    const fOff=computeFair({price:66150,strike:66000,tauSec:400,volBps:0.30,driftBps:0,knownAvg:null,knownDur:0});
    C.push({name:'v4.16 F29 OFF -> survFn==normCdf (identical to 4.15)',pass:Math.abs(survFn(1.0)-normCdf(1.0))<1e-12,got:survFn(1.0).toFixed(4)});
    // ON => near-strike conviction DROPS (fat tail adds crossing prob), deep-cushion nearly unchanged
    CFG.JUMP_ON=1; CFG.JUMP_LAMBDA=0.15; CFG.JUMP_K=4;
    const near=survFn(1.0), deep=survFn(2.5), g1=normCdf(1.0), g25=normCdf(2.5);
    C.push({name:'v4.16 F29 ON: near-strike (z=1) de-confidenced vs Gaussian',pass:near<g1-0.02,got:'jd '+near.toFixed(3)+' < gauss '+g1.toFixed(3)});
    C.push({name:'v4.16 F29 ON: deep-cushion (z=2.5) nearly preserved (within 0.05)',pass:Math.abs(deep-g25)<0.05,got:'jd '+deep.toFixed(3)+' vs gauss '+g25.toFixed(3)});
    C.push({name:'v4.16 F29 ON: monotone in z (higher cushion -> higher conviction)',pass:survFn(0.5)<survFn(1.5)&&survFn(1.5)<survFn(2.5),got:[survFn(0.5),survFn(1.5),survFn(2.5)].map(x=>x.toFixed(3)).join('<')});
    // ON changes computeFair output downward for a near-strike setup
    CFG.JUMP_ON=1; const fJump=computeFair({price:66050,strike:66000,tauSec:400,volBps:0.30,driftBps:0,knownAvg:null,knownDur:0});
    CFG.JUMP_ON=0; const fGauss=computeFair({price:66050,strike:66000,tauSec:400,volBps:0.30,driftBps:0,knownAvg:null,knownDur:0});
    C.push({name:'v4.16 F29 near-strike computeFair lower under jump model',pass:Math.abs(fJump-0.5)<Math.abs(fGauss-0.5),got:'jump '+round(fJump,3)+' vs gauss '+round(fGauss,3)});
    // lam=0 collapses to Gaussian even when JUMP_ON
    CFG.JUMP_ON=1; CFG.JUMP_LAMBDA=0;
    C.push({name:'v4.16 F29 lambda=0 -> collapses to Gaussian',pass:Math.abs(survFn(1.0)-normCdf(1.0))<1e-9,got:survFn(1.0).toFixed(4)});
    CFG.JUMP_ON=sOn;CFG.JUMP_LAMBDA=sL;CFG.JUMP_K=sK;
  })();
  // ---- v4.16 F30 MAKER-FIRST EXECUTION PLANNER ----
  (function(){
    const sF=CFG.MAKER_FIRST,sU=CFG.MAKER_UNDERCUT,sW=CFG.MAKER_WAIT_S,sMin=CFG.MIN_TAU_ENTER;
    CFG.MAKER_UNDERCUT=0.01; CFG.MAKER_WAIT_S=45; CFG.MIN_TAU_ENTER=8;
    const yesDec={action:'BUY_YES',px:0.75}, noDec={action:'BUY_NO',px:0.72}, noneDec={action:'NONE'};
    // OFF -> always taker (identical to 4.15)
    CFG.MAKER_FIRST=0;
    C.push({name:'v4.16 F30 OFF -> taker (identical to 4.15)',pass:planExecution(yesDec,400).mode==='taker',got:planExecution(yesDec,400).mode});
    // ON, ample time -> maker-first at 1c inside, both sides
    CFG.MAKER_FIRST=1;
    const py=planExecution(yesDec,400);
    C.push({name:'v4.16 F30 ON YES -> maker-first bid 1c inside (0.74)',pass:py.mode==='maker-first'&&py.makerPx===0.74&&py.takerPx===0.75,got:py.mode+' @'+py.makerPx});
    const pn=planExecution(noDec,400);
    C.push({name:'v4.16 F30 ON NO -> maker-first bid 1c inside (0.71)',pass:pn.mode==='maker-first'&&pn.makerPx===0.71&&pn.side==='NO',got:pn.mode+' @'+pn.makerPx+' '+pn.side});
    // not enough time to rest -> taker fallback (tau <= MIN_TAU_ENTER+WAIT = 53)
    C.push({name:'v4.16 F30 too little time (tau 50) -> taker',pass:planExecution(yesDec,50).mode==='taker',got:planExecution(yesDec,50).mode});
    C.push({name:'v4.16 F30 boundary tau just above 53 -> maker-first',pass:planExecution(yesDec,54).mode==='maker-first',got:planExecution(yesDec,54).mode});
    // NONE / non-buy decisions pass through as taker (no maker post)
    C.push({name:'v4.16 F30 NONE decision -> taker passthrough',pass:planExecution(noneDec,400).mode==='taker',got:planExecution(noneDec,400).mode});
    // undercut that collapses to >= taker px -> take (never rest at/through taker)
    CFG.MAKER_UNDERCUT=0;
    C.push({name:'v4.16 F30 zero undercut -> taker (no phantom improvement)',pass:planExecution(yesDec,400).mode==='taker',got:planExecution(yesDec,400).mode});
    // maker fill saves the fee delta + undercut (economics sanity: maker fee < taker fee at these prices)
    CFG.MAKER_UNDERCUT=0.01;
    C.push({name:'v4.16 F30 maker fee (0.003*q) < taker fee (0.07*px*(1-px)*q) at px 0.75',pass:makerFee(10)<takerFee(0.75,10),got:'maker '+makerFee(10).toFixed(3)+' < taker '+takerFee(0.75,10).toFixed(3)});
    CFG.MAKER_FIRST=sF;CFG.MAKER_UNDERCUT=sU;CFG.MAKER_WAIT_S=sW;CFG.MIN_TAU_ENTER=sMin;
  })();
  _f31tests(C);
  const failed=C.filter(c=>!c.pass); CFG.YES_ON=_yesOnSaved; CFG.REGIME_WARMUP=_warmupSaved; CFG.MIN_TAU_TRADE=_tauTradeSaved;
  CFG.FAIR_ANCHOR_ON=_anchorSaved; CFG.JUMP_ON=_jumpSaved; CFG.MAKER_FIRST=_makerSaved; CFG.REGIME_TREND_OVERRIDE=_trendSaved;
  Object.assign(CFG,_gS);
  return{ok:failed.length===0,version:VERSION,passed:C.length-failed.length,total:C.length,checks:C};
}
function _f31tests(C){
  const sOn=CFG.FAIR_ANCHOR_ON,sK=CFG.FAIR_ANCHOR_K;
  const book={yesBid:0.74,yesAsk:0.76,noBid:0.24,noAsk:0.26}; // mid 0.75
  // OFF -> returns model fair unchanged
  CFG.FAIR_ANCHOR_ON=0;
  C.push({name:'v4.16 F31 OFF -> model fair unchanged',pass:anchoredFair(0.95,book)===0.95,got:String(anchoredFair(0.95,book))});
  // ON K=0.3 -> pulls 0.95 toward 0.75 mid: 0.75+0.3*(0.95-0.75)=0.81
  CFG.FAIR_ANCHOR_ON=1; CFG.FAIR_ANCHOR_K=0.3;
  const a=anchoredFair(0.95,book);
  C.push({name:'v4.16 F31 ON K=.3: 0.95 model -> ~0.81 honest (kills fake 95%)',pass:Math.abs(a-0.81)<0.005,got:a.toFixed(3)});
  // K=0 -> pure market mid
  CFG.FAIR_ANCHOR_K=0;
  C.push({name:'v4.16 F31 K=0 -> pure market mid 0.75',pass:Math.abs(anchoredFair(0.99,book)-0.75)<1e-9,got:anchoredFair(0.99,book).toFixed(3)});
  // K=1 -> pure model
  CFG.FAIR_ANCHOR_K=1;
  C.push({name:'v4.16 F31 K=1 -> pure model 0.99',pass:Math.abs(anchoredFair(0.99,book)-0.99)<1e-9,got:anchoredFair(0.99,book).toFixed(3)});
  // no book -> falls back to model (never crashes)
  CFG.FAIR_ANCHOR_K=0.3;
  C.push({name:'v4.16 F31 no book -> model fallback',pass:anchoredFair(0.9,null)===0.9,got:String(anchoredFair(0.9,null))});
  // anchoring is symmetric for NO side (1-anchored)
  const yb={yesBid:0.23,yesAsk:0.25,noBid:0.75,noAsk:0.77}; // yes mid 0.24
  C.push({name:'v4.16 F31 low-price window anchors toward market too',pass:anchoredFair(0.05,yb)>0.05&&anchoredFair(0.05,yb)<0.24,got:anchoredFair(0.05,yb).toFixed(3)});
  // gating effect: a model-0.95 YES at market 0.75 is BELOW FAIR_MIN_HI(0.85) once anchored -> honest gate
  CFG.FAIR_ANCHOR_ON=1; CFG.FAIR_ANCHOR_K=0.3;
  const anc=anchoredFair(0.95,book);
  C.push({name:'v4.16 F31 anchored conviction (0.81) < FAIR_MIN_HI(0.85) -> gate sees honest number',pass:anc<0.85,got:anc.toFixed(3)});
  CFG.FAIR_ANCHOR_ON=sOn; CFG.FAIR_ANCHOR_K=sK;
}

/* --------------------- HTTP server --------------------- */
const server=http.createServer(async (req,res)=>{
  let u;
  try{ u=new URL(req.url,'http://'+(req.headers.host||'localhost')); }
  catch(_){ return send(res,400,{error:'bad url'}); }
  const path=u.pathname.replace(/\/+$/,'')||'/';
  if(req.method==='OPTIONS'){cors(res);res.statusCode=204;return res.end();}
  try{
    if(path==='/'||path==='/health'){
      return send(res,200,{ok:true,version:VERSION,ticks:STATE.ticks,uptimeSec:Math.round(process.uptime()),
        strikeSaneMin:STRIKE_SANE_MIN,halt:cage.halted(),liveHalt:CFG.LIVE?liveHalted():null});
    }
    if(path==='/selftest'){ return send(res,200,runSelfTest()); }
    if(path==='/status'){
      if(!STATE.lastStatus)return send(res,200,{version:VERSION,warmup:true,ticks:STATE.ticks,note:'no tick yet'});
      return send(res,200,STATE.lastStatus);
    }
    if(path==='/report'){ return send(res,200,report()); }
    if(path==='/radar'){ return send(res,200,{version:VERSION,...radarSnapshot()}); }
    if(path==='/live'){
      return send(res,200,{version:VERSION,liveEnabled:!!CFG.LIVE,ready:liveReady(),halt:CFG.LIVE?liveHalted():null,
        realizedToday:round(LIVE.realizedToday,2),lastFill:LIVE.lastFill,lastErr:LIVE.lastErr,orders:LIVE.orders.slice(-10)});
    }
    if(path==='/livecheck'){
      if(!liveReady())return send(res,200,{ready:false,note:'no KALSHI_KEY_ID/PRIVATE_KEY configured'});
      try{ const pos=await fetchLivePositions(); return send(res,200,{ready:true,positions:pos}); }
      catch(e){ return send(res,502,{ready:true,error:String(e&&e.message||e)}); }
    }
    if(path==='/halt'){
      const on=u.searchParams.get('on');
      if(on==='1'){cage.manualHalt=true;return send(res,200,{ok:true,manualHalt:true,halt:cage.halted()});}
      if(on==='0'){cage.manualHalt=false;return send(res,200,{ok:true,manualHalt:false,halt:cage.halted()});}
      return send(res,200,{manualHalt:cage.manualHalt,halt:cage.halted(),usage:'/halt?on=1 to halt, /halt?on=0 to resume'});
    }
    if(path==='/log'){
      const n=Math.max(1,Math.min(5000,Number(u.searchParams.get('n')||200)));
      let lines=[];
      try{ const raw=fs.readFileSync(LOG_PATH,'utf8').trim(); if(raw)lines=raw.split('\n'); }
      catch(_){ lines=[]; }
      const tail=lines.slice(-n).map(l=>{try{return JSON.parse(l);}catch(_){return {raw:l};}});
      return send(res,200,{path:LOG_PATH,count:tail.length,total:lines.length,lines:tail});
    }
    return send(res,404,{error:'not found',routes:['/health','/selftest','/status','/report','/radar','/live','/livecheck','/halt','/log']});
  }catch(e){
    return send(res,500,{error:String(e&&e.message||e)});
  }
});

/* --------------------- startup --------------------- */
if(require.main===module){
  let seeded=0; try{seeded=seedRegimeFromLog();}catch(_){seeded='err';}
  server.listen(PORT,()=>{
    console.log('['+VERSION+'] listening on :'+PORT+' | F26 strike-poison guard active (STRIKE_SANE_MIN=$'+STRIKE_SANE_MIN+') | regime seeded='+seeded+' | LOG_PATH='+LOG_PATH);
    console.log('  routes: /health /selftest /status /report /radar /live /livecheck /halt?on=1|0 /log?n=200');
  });
  const it=setInterval(()=>{tick().catch(e=>{STATE.lastErr=String(e&&e.message||e);});},2000);
  if(it.unref===undefined){/* keep alive */}
}

module.exports={
  computeFair,survFn,anchoredFair,marketMid,decideEntry,planExecution,decideExit,decideLateExit,takerFee,makerFee,makeCage,runSelfTest,
  windowState,sessionTag,tapeAvg,calFair,sessionSkipped,truthPnl,pushRegimeMargin,regimeMean,
  regimeViolent,regimeTrend,pushBasis,currentBasis,aboveFrac,entryViolence,seedRegimeFromLog,regimeWarm,
  markSettled,parseStrike,STATE
};
