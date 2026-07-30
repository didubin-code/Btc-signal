/* =====================================================================
   BTC LIVE TRADER v4.2 — vol-ceiling fix (2026-07-29)
   v4.2 CHANGES (data-derived from live 4.1 blowups):
     F13 VOL CEILING (VOL_MAX_ENTER=0.45): live 4.1 data — vol>0.45 = 50% wr,
        -$1.87/trade; the -$4.92 (63540 slot) fired at vol 0.721. Above ~0.45
        drift is noise and F9/counter-trend SELECT THE WRONG SIDE off it. The old
        "vol>=0.60 is fine (94% wr)" was fit to stale data and is false live.
        There was a vol FLOOR and two pain-band skips but NO ceiling — hot tape
        sailed through and picked the wrong direction. Now hard-blocked.
     F14 DRIFT-TRUST CEILING (VOL_DRIFT_TRUST=0.35): above this vol, drift is
        zeroed for side-selection so counter-trend (v2.4) and F9 stop forcing a
        side off noise in the 0.35-0.45 band that still trades.
   ---------------------------------------------------------------------
   v4.1 CHANGES (retained):
     F8 vol FLOOR (dead-calm <0.15 = 70.6% wr, -$27). F9 drift-oppose gate.
     F10 NaN hardening. F12 regime detector (adaptive stand-down).
   PRIOR (retained): F1 sym-cal, F2 sat-gate(removed v3.7), F3 px cap, F4 honest
     risk, F5 avg60 settle, F6 session skip, F7 vol pain-bands.
   Zero dependencies. Deploy as its own Render service:
     Start Command: node live-trader-4.2.js
   Endpoints: /health /selftest /status /report /log /halt?on=1|0 /live /livecheck /radar
   ===================================================================== */
'use strict';
const http = require('http');
const fs = require('fs');
const { URL } = require('url');
const crypto = require('crypto');

const PORT = Number(process.env.PORT || 10000);
const VERSION = 'live-trader-4.4';
const KALSHI_BASE = (process.env.KALSHI_BASE || 'https://api.elections.kalshi.com/trade-api/v2').replace(/\/+$/,'');
const LOG_PATH = process.env.LOG_PATH || '/tmp/shadow_trades.jsonl';

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
  MIN_ENTRY_PX: Number(process.env.MIN_ENTRY_PX ?? 0.80),
  MAX_ENTRY_PX: Number(process.env.MAX_ENTRY_PX ?? 0.85),
  VOL_SKIP_LO: Number(process.env.VOL_SKIP_LO ?? 0.35),
  VOL_SKIP_HI: Number(process.env.VOL_SKIP_HI ?? 0.38),
  VOL_SKIP2_LO: Number(process.env.VOL_SKIP2_LO ?? 0.50),
  VOL_SKIP2_HI: Number(process.env.VOL_SKIP2_HI ?? 0.60),
  VOL_MIN_ENTER: Number(process.env.VOL_MIN_ENTER ?? 0.15),  // v4.1 F8: reject dead-calm tape (<0.15). 0 disables.
  VOL_MAX_ENTER: Number(process.env.VOL_MAX_ENTER ?? 0.45),  // v4.2 F13: reject HOT tape. Live 4.1: vol>0.45 = 50% wr, -$1.87/trade; the -$4.92 (63540 slot) fired at 0.721. Above ~0.45 drift is noise, side-selection unreliable. 0 disables.
  VOL_DRIFT_TRUST: Number(process.env.VOL_DRIFT_TRUST ?? 0.35), // v4.2 F14: above this vol, ZERO drift for side-selection (counter-trend v2.4 + F9 stop forcing a side off noise). 0 = always trust drift.
  LATE_EXIT_ON: Number(process.env.LATE_EXIT_ON ?? 1),          // v4.3 F16: late-window locked-average SALVAGE exit. Settlement=60s avg; in the final seconds it's mostly locked. If even K-sigma favorable move can't drag the locked avg back to our winning side, the loss is MATHEMATICALLY decided -> sell for salvage instead of holding to $0. NOT the reversal gate (no sentiment/prediction) -> in 38k sim fires it cut ZERO winners. Backtest: +$78.77 -> +$183.30, positive 7/7 days. 0 disables.
  LATE_EXIT_TAU: Number(process.env.LATE_EXIT_TAU ?? 20),        // only evaluate F16 when tauSec <= this (final window, avg mostly locked)
  LATE_EXIT_MIN_TAU: Number(process.env.LATE_EXIT_MIN_TAU ?? 3), // ...and tauSec >= this (need time to actually place the close)
  LATE_EXIT_K: Number(process.env.LATE_EXIT_K ?? 2.0),          // sigma buffer: only fire when a K-sigma favorable move STILL can't win. Higher=more conservative=fewer fires, never cuts a winner.
  LATE_EXIT_MIN_SALVAGE: Number(process.env.LATE_EXIT_MIN_SALVAGE ?? 0.03), // don't bother exiting if bid below this (no salvage value worth the fee)
  GAP_MIN: Number(process.env.GAP_MIN ?? 0.12),   // v4.4 F17 GAP GATE: require model_conf - price in [GAP_MIN, GAP_MAX]. On 515 trades this band = 83% wr / +$0.53/tr, p=0.006 significant, holds out-of-sample (train 86%/test 73% on unseen days), blocks tonight's -$5 losses (gap 0.08-0.09). Below GAP_MIN = overpaying favorites w/ no edge (73% wr, -$0.29). 0 disables.
  GAP_MAX: Number(process.env.GAP_MAX ?? 0.20),   // above this = model hallucinating edge, market is right (gap 0.20-0.28 = 68% wr / -$0.37). Uses ONLY entryFair & price (both real, known at entry) — no execution assumptions, cannot lie like a salvage-price backtest.
  DRIFT_OPPOSE_MIN: Number(process.env.DRIFT_OPPOSE_MIN ?? 0.02),
  REGIME_ON: Number(process.env.REGIME_ON ?? 1),
  REGIME_LOOKBACK: Number(process.env.REGIME_LOOKBACK ?? 5),
  REGIME_MARGIN_MAX: Number(process.env.REGIME_MARGIN_MAX ?? 45),
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

// v4.3 F16 live close: flatten a position (reduce-only IOC). Paper mode logs WOULD_CLOSE.
async function placeCloseOrder(pos, salvagePx){
  const isYes = pos.side==='YES';
  // to exit, SELL the side we hold at a marketable price (the bid we can hit)
  const order={ticker:pos.ticker,
    client_order_id:'close-'+Date.now()+'-'+Math.floor(Math.random()*1e6),
    side: isYes ? 'ask' : 'bid',   // sell our YES (ask) / cover our NO (bid) — reduce_only flattens
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
  for(const c of[m.floor_strike,m.cap_strike,m.strike]){const n=Number(c);if(Number.isFinite(n)&&n>0)return n;}
  const tail=String(m.ticker||'').split('-').pop()||'';const n=Number(tail.replace(/[^0-9.]/g,''));
  return Number.isFinite(n)&&n>0?n:NaN;
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
  const btc=all.filter(m=>/BTC/i.test(String(m.ticker||'')+' '+String(m.title||'')))
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
    return clamp(1-normCdf((strike-mean)/sd),0.005,0.995);
  }
  const r=Math.max(0.5,tauSec);
  const e=clamp(Number.isFinite(knownDur)?knownDur:60-r,0,60-r+0.01)||Math.max(0,60-r);
  const kAvg=Number.isFinite(knownAvg)?knownAvg:price;
  const sumKnown=kAvg*e;
  const reqFutureMean=(60*strike-sumKnown)/r;
  mean=price+driftUsdPerSec*r*0.5;
  sd=Math.max(1e-6,sigUsdPerSqrtSec*Math.sqrt(r/3));
  return clamp(1-normCdf((reqFutureMean-mean)/sd),0.001,0.999);
}

/* --------------------- decision engine (E2-E4) --------------------- */
function decideEntry(o){
  const {fair,book,tauSec,inHV,sentPressure,haveOpen,ticker,lockout}=o;
  if(!haveOpen && regimeViolent())
    return{action:'NONE',reason:'regime stand-down: recent mean |settle margin| '+round(regimeMean(),0)+' > '+CFG.REGIME_MARGIN_MAX+' (violent tape)'};
  if(haveOpen)return{action:'NONE',reason:'position open'};
  if(!book||fair===null)return{action:'NONE',reason:'no data'};
  if(tauSec<CFG.MIN_TAU_ENTER)return{action:'NONE',reason:'too close to expiry'};
  const cdActive = o.cooldownUntil && Date.now()<o.cooldownUntil;
  const cdSameWindow = cdActive && o.lockout && o.ticker && o.lockout.ticker===o.ticker;
  const locked=lockout&&ticker&&lockout.ticker===ticker;
  const inBand=v=>!CFG.FILTER_ON || v>=CFG.FAIR_MIN_HI || v<=CFG.FAIR_MAX_LO;
  if(CFG.FILTER_ON && CFG.FAIR_STABLE_N>1 && typeof o.fairStreak==='number' && o.fairStreak<CFG.FAIR_STABLE_N)
    return{action:'NONE',reason:'fair not stable yet ('+o.fairStreak+'/'+CFG.FAIR_STABLE_N+' consecutive reads)'};
  let realCushionSigma=null, cushionSide=null;
  if(o.price&&o.strike&&o.volBps&&tauSec>0){
    const sig=(o.volBps/1e4)*o.price*Math.sqrt(tauSec);
    realCushionSigma=(o.price-o.strike)/Math.max(sig,1e-9);
    cushionSide=realCushionSigma>=0?'YES':'NO';
  }
  const cushionOK=(side)=>{
    if(realCushionSigma===null)return true;
    return side==='YES' ? realCushionSigma>=CFG.MIN_CUSHION_SIGMA
                        : (-realCushionSigma)>=CFG.MIN_CUSHION_SIGMA;
  };
  const satYES = Number.isFinite(o.rawFair) && o.rawFair>=0.995;
  const satNO  = Number.isFinite(o.rawFair) && o.rawFair<=0.005;
  const volSkip = Number.isFinite(o.volBps) && (
      (CFG.VOL_SKIP_HI>CFG.VOL_SKIP_LO && o.volBps>=CFG.VOL_SKIP_LO && o.volBps<CFG.VOL_SKIP_HI) ||
      (CFG.VOL_SKIP2_HI>CFG.VOL_SKIP2_LO && o.volBps>=CFG.VOL_SKIP2_LO && o.volBps<CFG.VOL_SKIP2_HI));
  // v4.2 F13 VOL CEILING: reject entries when the tape is too hot. Above VOL_MAX_ENTER the drift
  // estimate is noise and F9/counter-trend select the WRONG side off it (the -$4.92 63540 trade
  // fired at vol 0.721 and bought YES into a $101 down-move). Tail-snipe exempt (own sigma bar).
  const volTooHot = CFG.VOL_MAX_ENTER>0 && Number.isFinite(o.volBps) && o.volBps>CFG.VOL_MAX_ENTER;
  // v4.2 F14 DRIFT-TRUST CEILING: above VOL_DRIFT_TRUST, zero drift for side-selection so the
  // counter-trend (v2.4) and F9 gates stop forcing a side off an unreliable signal.
  const drift=(CFG.VOL_DRIFT_TRUST>0&&Number.isFinite(o.volBps)&&o.volBps>CFG.VOL_DRIFT_TRUST)?0:(o.driftBps||0);
  if(o.price&&o.strike&&o.volBps&&tauSec<=CFG.TAIL_TAU&&tauSec>=CFG.MIN_TAU_ENTER){
    const sig=(o.volBps/1e4)*o.price*Math.sqrt(tauSec);
    const cushion=(o.price-o.strike)/Math.max(sig,1e-9);
    if(Math.abs(cushion)>=CFG.TAIL_SIGMA){
      if(cushion>0&&book.yesAsk>0&&book.yesAsk<0.99){
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
  // taker YES
  if(Number.isFinite(book.yesAsk)&&book.yesAsk>0.02&&book.yesAsk<0.98){
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
      if(!inBand(fair))return{action:'NONE',reason:'fair '+round(fair,3)+' outside trade band ['+CFG.FAIR_MAX_LO+','+CFG.FAIR_MIN_HI+']'};
      if(sentPressure<=-vetoAt)return{action:'NONE',reason:'YES edge but perp pressure down (veto @'+vetoAt+')'};
      return{action:'BUY_YES',mode:'taker',px:book.yesAsk,fair,netEdge:round(net,3),reason:'fair '+round(fair,3)+' vs ask '+book.yesAsk};
    }
  }
  // taker NO
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
      if(book.noAsk<CFG.MIN_ENTRY_PX||book.noAsk>CFG.MAX_ENTRY_PX)return{action:'NONE',reason:'entry px '+book.noAsk+' outside edge band ['+CFG.MIN_ENTRY_PX+','+CFG.MAX_ENTRY_PX+']'};
      if(!cushionOK('NO'))return{action:'NONE',reason:'real cushion only '+round(-realCushionSigma,2)+' sigma (need '+CFG.MIN_CUSHION_SIGMA+') — fair is drift-manufactured'};
      if(locked&&lockout.side==='NO')return{action:'NONE',reason:'reversal lockout (NO) this window'};
      if(cdSameWindow&&o.lockout.side==='NO')return{action:'NONE',reason:'cooldown same-side NO ('+Math.ceil((o.cooldownUntil-Date.now())/1000)+'s)'};
      if(!inBand(1-fair))return{action:'NONE',reason:'fair(no) '+round(1-fair,3)+' outside trade band ['+CFG.FAIR_MAX_LO+','+CFG.FAIR_MIN_HI+']'};
      if(sentPressure>=vetoAt)return{action:'NONE',reason:'NO edge but perp pressure up (veto @'+vetoAt+')'};
      return{action:'BUY_NO',mode:'taker',px:book.noAsk,fair,netEdge:round(net,3),reason:'fair(no) '+round(1-fair,3)+' vs ask '+book.noAsk};
    }
  }
  // maker panic-capture (final window only)
  if(tauSec<=CFG.MAKER_WINDOW_S&&fair>=0.35&&fair<=0.9&&!(locked&&lockout.side==='YES')){
    const bid=round(Math.max(0.02,fair-CFG.MAKER_EDGE_MIN),2);
    if(Number.isFinite(book.yesAsk)&&bid<book.yesAsk)
      return{action:'POST_YES_BID',mode:'maker',px:bid,fair,netEdge:round(fair-bid-CFG.MAKER_FEE,3),reason:'panic-capture bid '+bid+' vs fair '+round(fair,3)};
  }
  return{action:'NONE',reason:'no edge ≥ '+edgeMin};
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
// PURE + testable. Settlement = mean of final 60s. At tauSec remaining (elapsedSec observed),
// the locked partial sum constrains the final average. Compute the future mean the remaining
// seconds would REQUIRE for our side to win; if even a K-sigma favorable move can't reach it,
// the loss is decided -> exit for salvage. Cannot cut a winner by construction (only fires when
// the winning outcome is mathematically unreachable).
function decideLateExit(o){
  const {side,strike,tauSec,lockedAvg,elapsedSec,price,volBps,book,K,minSalvage}=o;
  if(!Number.isFinite(strike)||!Number.isFinite(lockedAvg)||!Number.isFinite(price)||!Number.isFinite(volBps))
    return{exit:false,reason:'insufficient data'};
  const kk=Number.isFinite(K)?K:2.0;
  const remaining=tauSec;
  if(remaining<=0||elapsedSec<=0) return{exit:false,reason:'window not open'};
  const lockedSum=lockedAvg*elapsedSec;
  // avg60 = (lockedSum + futureMean*remaining)/60  ->  futureMean to hit strike exactly:
  const reqFutureMean=(60*strike - lockedSum)/remaining;
  const sig=(volBps/1e4)*price;                 // $ per sqrt-second
  const moveCap=kk*sig*Math.sqrt(Math.max(remaining,1));
  let decidedLoss;
  if(side==='YES'){
    // YES wins if final avg>strike -> needs futureMean>reqFutureMean. Best case = price+moveCap.
    decidedLoss=(price+moveCap) <= reqFutureMean;
  } else {
    // NO wins if final avg<=strike -> needs futureMean<=reqFutureMean. Best case = price-moveCap.
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
const STATE={pos:null,pendingMaker:null,lastReversal:null,cooldownUntil:0,fairStreak:0,fairStreakTicker:'',trades:[],reconcile:[],lastStatus:null,lastErr:null,ticks:0,lastSkipKey:'',skips:[],phantoms:[],revCondSince:0,recentMargins:[]};
function pushRegimeMargin(absMargin){
  if(absMargin==null||!Number.isFinite(absMargin))return;
  STATE.recentMargins.push(absMargin);
  const cap=Math.max(CFG.REGIME_LOOKBACK*3,30);
  while(STATE.recentMargins.length>cap)STATE.recentMargins.shift();
}
function regimeMean(){
  const n=CFG.REGIME_LOOKBACK;
  if(STATE.recentMargins.length<n)return null;
  const w=STATE.recentMargins.slice(-n);
  return w.reduce((a,b)=>a+b,0)/n;
}
function regimeViolent(){
  if(!CFG.REGIME_ON||CFG.REGIME_MARGIN_MAX<=0)return false;
  const m=regimeMean();
  return m!=null && m>CFG.REGIME_MARGIN_MAX;
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
  if(settled&&extra&&extra.margin!=null)pushRegimeMargin(Math.abs(extra.margin));
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
async function tick(){
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
      const won=use!==null?(STATE.pos.side==='YES'?use>STATE.pos.strike:use<=STATE.pos.strike):null;
      closePos('settlement ('+CFG.SETTLE_METRIC+' '+round(use,2)+')',null,true,!!won,
        {settleAvg60:round(avg,2),settleLast:round(lastPx,2),settleUsed:metric!==null?CFG.SETTLE_METRIC:'fallback',
         margin:use!==null?round(use-STATE.pos.strike,2):null,strike:STATE.pos.strike});
    }
    // v4.3.1 F16 FIX: evaluate the late-window salvage exit against the POSITION'S OWN clock,
    // independent of discoverMarket (which rolls to the next slot in the final ~60s, leaving the
    // open position unmanaged — the -$4.92 292315 bug). tau is computed from STATE.pos.closeTs.
    if(STATE.pos&&CFG.LATE_EXIT_ON){
      const posTau=(STATE.pos.closeTs-Date.now())/1000;
      if(posTau<=CFG.LATE_EXIT_TAU&&posTau>=CFG.LATE_EXIT_MIN_TAU){
        const elapsed=Math.max(0,60-posTau);
        const lockedAvg=tapeAvg(STATE.pos.closeTs-60000, Date.now());
        const px=tapeNow();
        if(Number.isFinite(lockedAvg)&&Number.isFinite(px)){
          // fetch a book for the position's own ticker (not the discovered mkt) for the salvage bid
          let pbook=null;
          try{ pbook=await getBook(STATE.pos.ticker,null); }catch(_){}
          const lx=decideLateExit({side:STATE.pos.side,strike:STATE.pos.strike,tauSec:posTau,lockedAvg,
            elapsedSec:elapsed,price:px,volBps:tapeVolBps(),book:pbook||{},K:CFG.LATE_EXIT_K,minSalvage:CFG.LATE_EXIT_MIN_SALVAGE});
          logLine({ev:'LATE_EVAL',ticker:STATE.pos.ticker,posTau:round(posTau,0),lockedAvg:round(lockedAvg,1),
            price:round(px,1),strike:STATE.pos.strike,side:STATE.pos.side,decided:!!lx.exit,reason:lx.reason});
          if(lx.exit){
            if(CFG.LIVE&&liveReady())placeCloseOrder(STATE.pos,lx.salvagePx).catch(()=>{});
            closePos(lx.reason,lx.salvagePx,false,null,{lateExit:true});
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
        if(tauSec<8||Math.abs((fair??0)-pm.fairAtPost)>0.12){STATE.pendingMaker=null;logLine({ev:'MAKER_CANCEL',ticker:pm.ticker,why:'stale/fair moved'});}
        else if(Number.isFinite(book.yesAsk)&&book.yesAsk<=pm.px){
          STATE.pendingMaker=null;openPos(mkt,'YES','maker',pm.px,fair,tauSec);
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
          const conf=Math.max(fair,1-fair);
          const clears=(conf>=CFG.FAIR_MIN_HI)||(Math.min(fair,1-fair)<=CFG.FAIR_MAX_LO&&CFG.FAIR_MAX_LO>0);
          if(mkt.ticker!==STATE.fairStreakTicker){STATE.fairStreakTicker=mkt.ticker;STATE.fairStreak=0;}
          STATE.fairStreak = clears ? STATE.fairStreak+1 : 0;
        })();
        decision=decideEntry({fair,rawFair,book,tauSec,fairStreak:STATE.fairStreak,inHV:w.inHV,sentPressure:sent.pressure||0,haveOpen:!!STATE.pos,ticker:mkt.ticker,lockout:STATE.lastReversal,cooldownUntil:STATE.cooldownUntil,driftBps:tapeDrift(),price,strike:mkt.strike,volBps:tapeVolBps()});
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
        if(decision.action==='BUY_YES')openPos(mkt,'YES','taker',decision.px,fair,tauSec);
        else if(decision.action==='BUY_NO')openPos(mkt,'NO','taker',decision.px,fair,tauSec);
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
  const w1=computeFair({price:62200,strike:62050,tauSec:10,volBps:0.6,driftBps:0,knownAvg:62200,knownDur:50});
  C.push({name:'locked avg: near-certain win → fair>0.99',pass:w1>0.99,got:round(w1,4)});
  const l1=computeFair({price:61900,strike:62050,tauSec:10,volBps:0.6,driftBps:0,knownAvg:61900,knownDur:50});
  C.push({name:'locked avg: near-certain loss → fair<0.01',pass:l1<0.01,got:round(l1,4)});
  const m1=computeFair({price:62050,strike:62050,tauSec:300,volBps:0.6,driftBps:0,knownAvg:null,knownDur:0});
  C.push({name:'ATM mid-window → fair≈0.5',pass:m1>0.4&&m1<0.6,got:round(m1,3)});
  const f=takerFee(0.5,1);
  C.push({name:'taker fee @0.50 = 0.0175',pass:Math.abs(f-0.0175)<1e-9,got:round(f,4)});
  const d1=decideEntry({fair:0.96,book:{yesAsk:0.84,noAsk:0.2,yesBid:0.8,noBid:0.14},tauSec:40,inHV:false,sentPressure:0,haveOpen:false});
  C.push({name:'fair .96 vs ask .84 → BUY_YES',pass:d1.action==='BUY_YES',got:d1.action+' '+(d1.netEdge??'')});
  const d2=decideEntry({fair:0.87,book:{yesAsk:0.84,noAsk:0.2,yesBid:0.8,noBid:0.14},tauSec:400,inHV:false,sentPressure:0,haveOpen:false});
  C.push({name:'thin edge → no trade (selectivity)',pass:d2.action==='NONE',got:d2.action});
  const d3=decideEntry({fair:0.92,book:{yesAsk:0.84,noAsk:0.2,yesBid:0.8,noBid:0.14},tauSec:40,inHV:true,sentPressure:0,haveOpen:false});
  C.push({name:'same edge blocked in high-variance window',pass:d3.action==='NONE',got:d3.action});
  const d4=decideEntry({fair:0.96,book:{yesAsk:0.84,noAsk:0.2,yesBid:0.8,noBid:0.14},tauSec:40,inHV:false,sentPressure:-55,haveOpen:false});
  C.push({name:'perp pressure down vetoes YES buy',pass:d4.action==='NONE',got:d4.action});
  const d5=decideEntry({fair:0.62,book:{yesAsk:0.6,noAsk:0.5,yesBid:0.42,noBid:0.4},tauSec:120,inHV:false,sentPressure:0,haveOpen:false});
  C.push({name:'late window → panic-capture bid below fair',pass:d5.action==='POST_YES_BID'&&d5.px<0.62,got:d5.action+' @'+d5.px});
  const posA={side:'YES',entryFair:0.9};
  const revOff = CFG.EXIT_SENT>=100;  // reversal exits disabled (EXIT_SENT=999) — expected on live/shadow
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
  // use a per-loss size small enough not to trip DAILY_LOSS_LIMIT first, so we isolate the consec-loss halt
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
  const f_hi=decideEntry({fair:0.94,book:{yesAsk:0.80,noAsk:0.14,yesBid:0.78,noBid:0.1},tauSec:400,inHV:false,sentPressure:0,haveOpen:false});
  C.push({name:'v2 filter PASSES fair>=0.85 favorite',pass:f_hi.action==='BUY_YES',got:f_hi.action});
  const inBandMid=(!CFG.FILTER_ON)||(0.84>=CFG.FAIR_MIN_HI||0.84<=CFG.FAIR_MAX_LO);
  C.push({name:'v2 filter: fair 0.84 OUTSIDE trade band',pass:inBandMid===false,got:'inBand='+inBandMid});
  const f_lo=decideEntry({fair:0.18,book:{yesAsk:0.07,noAsk:0.9,yesBid:0.05,noBid:0.88},tauSec:400,inHV:false,sentPressure:0,haveOpen:false});
  C.push({name:'v2.3 filter REJECTS longshots',pass:f_lo.action==='NONE',got:f_lo.action+' '+f_lo.reason});
  const badTrade=decideEntry({fair:0.973,book:{yesAsk:0.80,noAsk:0.19,yesBid:0.78,noBid:0.17},
    tauSec:427,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.015,price:65711,strike:65718.69,volBps:0.286,fairStreak:99});
  C.push({name:'v3.3 BLOCKS drift-manufactured trade',pass:badTrade.action==='NONE'&&/real cushion/.test(badTrade.reason),got:badTrade.action+' '+(badTrade.reason||'')});
  const goodTrade=decideEntry({fair:0.92,book:{yesAsk:0.80,noAsk:0.12,yesBid:0.78,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.02,price:66150,strike:66000,volBps:0.3,fairStreak:99});
  C.push({name:'v3.3 ALLOWS genuinely cushioned favorite',pass:goodTrade.action==='BUY_YES',got:goodTrade.action+' '+(goodTrade.reason||'')});
  const goodNo=decideEntry({fair:0.08,book:{yesAsk:0.90,noAsk:0.80,yesBid:0.88,noBid:0.78},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.02,price:65850,strike:66000,volBps:0.3,fairStreak:99});
  C.push({name:'v3.3 ALLOWS cushioned NO',pass:goodNo.action==='BUY_NO',got:goodNo.action+' '+(goodNo.reason||'')});
  const flicker=decideEntry({fair:0.92,book:{yesAsk:0.80,noAsk:0.12,yesBid:0.78,noBid:0.10},
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
  const vFloor=decideEntry({fair:0.92,rawFair:0.94,book:{yesAsk:0.80,noAsk:0.12,yesBid:0.78,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.10,fairStreak:99});
  C.push({name:'v4.1 F8 vol floor BLOCKS dead-calm 0.10',pass:vFloor.action==='NONE'&&/dead-calm/.test(vFloor.reason),got:vFloor.action+' '+(vFloor.reason||'')});
  const vOk=decideEntry({fair:0.92,rawFair:0.94,book:{yesAsk:0.80,noAsk:0.12,yesBid:0.78,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.22,fairStreak:99});
  C.push({name:'v4.1 F8 vol floor PASSES moderate 0.22',pass:vOk.action==='BUY_YES',got:vOk.action+' '+(vOk.reason||'')});
  // v4.2 F13 VOL CEILING — the fix for the -$4.92 63540 blowup
  const vCeil=decideEntry({fair:0.90,rawFair:0.92,book:{yesAsk:0.82,noAsk:0.12,yesBid:0.80,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.16,price:66150,strike:66000,volBps:0.72,fairStreak:99});
  C.push({name:'v4.2 F13 vol CEILING BLOCKS hot 0.72 (the -$4.92 63540 trade)',pass:vCeil.action==='NONE'&&/hot tape/.test(vCeil.reason),got:vCeil.action+' '+(vCeil.reason||'')});
  const vCeil2=decideEntry({fair:0.10,rawFair:0.08,book:{yesAsk:0.90,noAsk:0.82,yesBid:0.88,noBid:0.80},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.16,price:65850,strike:66000,volBps:0.65,fairStreak:99});
  C.push({name:'v4.2 F13 vol CEILING BLOCKS hot NO side (0.65)',pass:vCeil2.action==='NONE'&&/hot tape/.test(vCeil2.reason),got:vCeil2.action+' '+(vCeil2.reason||'')});
  const vCeilOk=decideEntry({fair:0.92,rawFair:0.94,book:{yesAsk:0.80,noAsk:0.12,yesBid:0.78,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.30,fairStreak:99});
  C.push({name:'v4.2 F13 vol ceiling PASSES calm 0.30 (edge zone intact)',pass:vCeilOk.action==='BUY_YES',got:vCeilOk.action+' '+(vCeilOk.reason||'')});
  // v4.2 F14 — drift zeroed in hot tape: counter-trend/F9 no longer force a side
  const dTrust=decideEntry({fair:0.92,rawFair:0.94,book:{yesAsk:0.80,noAsk:0.12,yesBid:0.78,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.20,price:66150,strike:66000,volBps:0.40,fairStreak:99});
  C.push({name:'v4.2 F14 hot-tape (0.40) zeroes drift: YES not blocked by F9',pass:dTrust.action==='BUY_YES',got:dTrust.action+' '+(dTrust.reason||'')});
  const dTrustCalm=decideEntry({fair:0.92,rawFair:0.94,book:{yesAsk:0.80,noAsk:0.12,yesBid:0.78,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.05,price:66150,strike:66000,volBps:0.22,fairStreak:99});
  C.push({name:'v4.2 F14 calm-tape (0.22) still trusts drift: opposing-drift YES blocked',pass:dTrustCalm.action==='NONE'&&/opposes drift/.test(dTrustCalm.reason),got:dTrustCalm.action+' '+(dTrustCalm.reason||'')});
  const tailExempt=decideEntry({fair:0.97,rawFair:0.97,book:{yesAsk:0.93,noAsk:0.08,yesBid:0.92,noBid:0.06},
    tauSec:30,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.10,price:66300,strike:66000,volBps:0.72});
  C.push({name:'v4.2 tail-snipe EXEMPT from vol ceiling',pass:tailExempt.action==='BUY_YES'&&/tail-snipe/.test(tailExempt.reason),got:tailExempt.action+' '+(tailExempt.reason||'')});
  const doY=decideEntry({fair:0.92,rawFair:0.94,book:{yesAsk:0.80,noAsk:0.12,yesBid:0.78,noBid:0.10},
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
    const cgN=makeCage();cgN.record(NaN);cgN.record(-30);cgN.record(NaN);cgN.adjust(NaN);cgN.record(-30);cgN.record(-30);cgN.record(-30);
    C.push({name:'v4.1 F10 cage survives NaN',pass:Number.isFinite(cgN.realized)&&cgN.realized===-120&&cgN.halted()!==null,got:'realized='+cgN.realized});
  })();
  C.push({name:'v3.0 defaults to DRY RUN',pass:CFG.LIVE===false||process.env.LIVE!==undefined,got:'LIVE='+CFG.LIVE});
  const tp=truthPnl({mode:'taker',entryPx:0.79,qty:10},false);
  C.push({name:'truthPnl flips phantom win to real loss',pass:Math.abs(tp-(-8.02))<0.02,got:tp});
  // ---- v4.4 F17 GAP GATE ----
  // gap in [0.12,0.20] trades; the two live -$5 losses had gap ~0.09 -> must be BLOCKED.
  const gLoss=decideEntry({fair:0.94,rawFair:0.94,book:{yesAsk:0.85,noAsk:0.12,yesBid:0.83,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:64100,strike:64000,volBps:0.30,fairStreak:99});
  C.push({name:'v4.4 F17 BLOCKS thin gap (the -$5 YES @0.85, gap 0.09)',pass:gLoss.action==='NONE'&&/gap/.test(gLoss.reason),got:gLoss.action+' '+(gLoss.reason||'')});
  // gap in the sweet spot -> trades
  const gGood=decideEntry({fair:0.94,rawFair:0.94,book:{yesAsk:0.80,noAsk:0.12,yesBid:0.78,noBid:0.10},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.30,fairStreak:99});
  C.push({name:'v4.4 F17 PASSES sweet-spot gap 0.14',pass:gGood.action==='BUY_YES',got:gGood.action+' '+(gGood.reason||'')});
  // gap too big (model hallucinating) -> blocked
  const gBig=decideEntry({fair:0.96,rawFair:0.96,book:{yesAsk:0.70,noAsk:0.22,yesBid:0.68,noBid:0.20},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:66150,strike:66000,volBps:0.30,fairStreak:99});
  C.push({name:'v4.4 F17 BLOCKS oversized gap 0.26 (model hallucinating)',pass:gBig.action==='NONE'&&/gap/.test(gBig.reason),got:gBig.action+' '+(gBig.reason||'')});
  // NO side sweet spot
  const gNo=decideEntry({fair:0.06,rawFair:0.06,book:{yesAsk:0.90,noAsk:0.80,yesBid:0.88,noBid:0.78},
    tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:-0.03,price:65850,strike:66000,volBps:0.30,fairStreak:99});
  C.push({name:'v4.4 F17 NO-side sweet-spot gap 0.14 trades',pass:gNo.action==='BUY_NO',got:gNo.action+' '+(gNo.reason||'')});
  // GAP_MIN=0 disables
  (function(){const sv=CFG.GAP_MIN;CFG.GAP_MIN=0;
    const off=decideEntry({fair:0.94,rawFair:0.94,book:{yesAsk:0.85,noAsk:0.12,yesBid:0.83,noBid:0.10},
      tauSec:400,inHV:false,sentPressure:0,haveOpen:false,driftBps:0.03,price:64100,strike:64000,volBps:0.30,fairStreak:99});
    C.push({name:'v4.4 F17 GAP_MIN=0 disables gate',pass:!/gap/.test(off.reason||''),got:off.action+' '+(off.reason||'')});
    CFG.GAP_MIN=sv;})();
  // ---- v4.3 F16 late-window salvage exit ----
  // Decided loss: YES held, 50s of 60 locked at $120 BELOW strike, only 10s left, vol 0.3.
  // Even a big favorable move can't drag the 60s avg above strike -> must fire.
  const lx1=decideLateExit({side:'YES',strike:66000,tauSec:10,lockedAvg:65880,elapsedSec:50,
    price:65885,volBps:0.30,book:{yesBid:0.18,noBid:0.80},K:2.0,minSalvage:0.03});
  C.push({name:'v4.3 F16 FIRES on decided YES loss (locked avg below strike, 10s left)',pass:lx1.exit===true&&/locked avg decides/.test(lx1.reason),got:(lx1.exit)+' '+(lx1.reason||'')});
  // Recoverable: same but 55s left and locked only $5 below — plenty of room -> must NOT fire.
  const lx2=decideLateExit({side:'YES',strike:66000,tauSec:55,lockedAvg:65995,elapsedSec:5,
    price:65996,volBps:0.30,book:{yesBid:0.4,noBid:0.6},K:2.0,minSalvage:0.03});
  C.push({name:'v4.3 F16 does NOT fire when recoverable (55s left, near strike)',pass:lx2.exit===false,got:lx2.exit+' '+(lx2.reason||'')});
  // Winning position: locked avg ABOVE strike for a YES -> never a loss -> must NOT fire.
  const lx3=decideLateExit({side:'YES',strike:66000,tauSec:10,lockedAvg:66200,elapsedSec:50,
    price:66210,volBps:0.30,book:{yesBid:0.95,noBid:0.05},K:2.0,minSalvage:0.03});
  C.push({name:'v4.3 F16 NEVER fires on a winning position',pass:lx3.exit===false,got:lx3.exit+' '+(lx3.reason||'')});
  // Decided NO loss: NO held, locked avg well ABOVE strike, little time -> fires.
  const lx4=decideLateExit({side:'NO',strike:66000,tauSec:10,lockedAvg:66150,elapsedSec:50,
    price:66155,volBps:0.30,book:{yesBid:0.85,noBid:0.14},K:2.0,minSalvage:0.03});
  C.push({name:'v4.3 F16 FIRES on decided NO loss (locked avg above strike)',pass:lx4.exit===true,got:lx4.exit+' '+(lx4.reason||'')});
  // Decided loss but NO salvage bid -> do not "exit into the void"
  const lx5=decideLateExit({side:'YES',strike:66000,tauSec:10,lockedAvg:65880,elapsedSec:50,
    price:65885,volBps:0.30,book:{yesBid:0.01,noBid:0.98},K:2.0,minSalvage:0.03});
  C.push({name:'v4.3 F16 holds if decided loss but no salvage bid',pass:lx5.exit===false&&/no salvage/.test(lx5.reason),got:lx5.exit+' '+(lx5.reason||'')});
  // Genuinely recoverable: only 15s locked (45s remaining weight), locked avg $8 below strike, decent vol.
  // The 45 remaining seconds carry 75% of the average weight -> a normal move CAN win -> must NOT fire.
  const lx6=decideLateExit({side:'YES',strike:66000,tauSec:45,lockedAvg:65992,elapsedSec:15,
    price:65997,volBps:0.5,book:{yesBid:0.4,noBid:0.6},K:2.0,minSalvage:0.03});
  C.push({name:'v4.3 F16 recoverable (45s of weight left) -> does NOT fire',pass:lx6.exit===false,got:lx6.exit+' '+(lx6.reason||'')});
  // Leverage check: SAME locked deficit but late (50s locked, 10s left) -> now decided -> fires.
  const lx7=decideLateExit({side:'YES',strike:66000,tauSec:10,lockedAvg:65992,elapsedSec:50,
    price:65997,volBps:0.5,book:{yesBid:0.3,noBid:0.7},K:2.0,minSalvage:0.03});
  C.push({name:'v4.3 F16 same deficit but 10s left -> leverage decides loss -> fires',pass:lx7.exit===true,got:lx7.exit+' '+(lx7.reason||'')});
  const failed=C.filter(c=>!c.pass);
  return{ok:failed.length===0,version:VERSION,passed:C.length-failed.length,total:C.length,checks:C};
}

/* --------------------- HTTP --------------------- */
const server=http.createServer(async(req,res)=>{
  const u=new URL(req.url,`http://${req.headers.host}`);
  if(req.method==='OPTIONS'){cors(res);res.statusCode=204;return res.end();}
  try{
    if(u.pathname==='/health')return send(res,200,{ok:true,version:VERSION,service:'btc-shadow-trader',
      mode:CFG.LIVE?'LIVE (real orders)':'SHADOW (no real orders)',tapeLen:TAPE.length,sentinel:SENT.read&&SENT.read.ok?'live':'warming',
      halt:cage.halted(),live:{configured:liveReady(),armed:CFG.LIVE,halted:liveHalted(),lastErr:LIVE.lastErr},ts:Date.now()});
    if(u.pathname==='/selftest'){const r=runSelfTest();return send(res,r.ok?200:500,r);}
    if(u.pathname==='/status')return send(res,200,STATE.lastStatus||{ok:false,error:'first tick pending'});
    if(u.pathname==='/report')return send(res,200,report());
    if(u.pathname==='/radar')return send(res,200,{url:CFG.RADAR_URL||null,fetches:RADAR.fetches,
      ageSec:RADAR.lastTs?Math.round((Date.now()-RADAR.lastTs)/1000):null,err:RADAR.err,
      parsed:radarSnapshot(),raw:RADAR.last});
    if(u.pathname==='/live')return send(res,200,{configured:liveReady(),armed:CFG.LIVE,
      halted:liveHalted(),dailyRealized:round(LIVE.realizedToday,2),lastErr:LIVE.lastErr,
      riskDollars:CFG.RISK_DOLLARS,maxContracts:CFG.LIVE_MAX_CONTRACTS,recentOrders:LIVE.orders.slice(-10)});
    if(u.pathname==='/livecheck'){
      if(!liveReady())return send(res,200,{ok:false,error:'KALSHI_KEY_ID / KALSHI_PRIVATE_KEY not set'});
      return kalshiAuthed('GET','/portfolio/balance').then(j=>send(res,200,{ok:true,balance:j}))
        .catch(e=>send(res,200,{ok:false,error:String(e.message||e)}));
    }
    if(u.pathname==='/log'){cors(res);res.setHeader('Content-Type','text/plain');
      try{return res.end(fs.readFileSync(LOG_PATH,'utf8'));}catch(_){return res.end('');}}
    if(u.pathname==='/halt'){const on=u.searchParams.get('on');cage.manualHalt=on==='1'||on==='true';
      return send(res,200,{ok:true,manualHalt:cage.manualHalt});}
    return send(res,404,{ok:false,error:'NOT_FOUND'});
  }catch(e){return send(res,500,{ok:false,error:String(e.message||e)});}
});
if(require.main===module){
  server.listen(PORT,()=>console.log(VERSION+' on '+PORT+' | F13 vol-ceiling '+CFG.VOL_MAX_ENTER+' F14 drift-trust '+CFG.VOL_DRIFT_TRUST+' px '+CFG.MIN_ENTRY_PX+'-'+CFG.MAX_ENTRY_PX));
  const t=setInterval(()=>tick().catch(e=>{STATE.lastErr=String(e.message||e);}),2000);
  if(t.unref)t.unref();
  tick().catch(()=>{});
}
module.exports={computeFair,decideEntry,decideExit,decideLateExit,takerFee,makerFee,makeCage,runSelfTest,windowState,sessionTag,tapeAvg,calFair,sessionSkipped,truthPnl,pushRegimeMargin,regimeMean,regimeViolent};
