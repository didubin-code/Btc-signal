'use strict';
// Independent audit: retain each engine's own lock history between decisions.
// All external observations still come from the supplied tape; no network/listener.
process.env.PINRADAR_REPLAY='1'; process.env.ENABLE_WS='0'; process.env.PR11_MODE='gate';
const fs=require('fs'),path=require('path');
const P=path.resolve(process.argv[2]), tag=process.argv[3];
if(!['I2','B9'].includes(tag)) throw new Error('usage: node sequential_audit.js PACKAGE I2|B9 [OUTDIR]');
const OUT=path.resolve(process.argv[4] || './audit_results');fs.mkdirSync(OUT,{recursive:true});
const S=require(path.join(P,'sources',tag==='I2'?'pinradar_server_I2_3125bbc0.js':'pinradar_server_PR11_b9_c03385dc.js'));
const RT=require(path.join(P,'scripts/round7/replay_tape28.js'));
const all=[]; for(const t of ['T1','T2','T3']) for(const l of fs.readFileSync(path.join(P,'data/unpacked',t+'.ndjson'),'utf8').trim().split('\n')) all.push(JSON.parse(l));
const sm=new Map(),rm=new Map(),bm=new Set();
for(const r of all){if(r.k==='s')sm.set(r.t,[r.t,r.v]); else if(r.k==='d')rm.set(r.kal.ticker+'|'+r.ts,r);else if(r.k==='boot')bm.add(r.ts);}
const samples=[...sm.values()].sort((a,b)=>a[0]-b[0]),boots=[...bm].sort((a,b)=>a-b),recs=[...rm.values()].sort((a,b)=>a.ts-b.ts);
const supplied=new Map();for(const t of ['T1','T2','T3'])for(const l of fs.readFileSync(path.join(P,'data/unpacked/d3',tag+'_'+t+'.ndjson'),'utf8').trim().split('\n')){const r=JSON.parse(l);supplied.set(r.ticker+'|'+r.ts,r);}
const own=new Map(),diffs=[],entries={},initial=[];let prevTs=null;
const rows=[];
for(const original of recs){
 const r=JSON.parse(JSON.stringify(original)),tk=r.kal.ticker;
 if(own.has(tk))r.lock25=own.get(tk);
 else initial.push({ticker:tk,tau:(r.kal.closeMs-r.ts)/1000,initialLockedSide:r.lock25.lockedSide});
 const sn=RT.restoreAndDecide(S,r,samples,boots),sg=sn.signal;
 own.set(tk,JSON.parse(JSON.stringify(S.LOCK25)));
 const old=supplied.get(tk+'|'+r.ts),tau=(r.kal.closeMs-r.ts)/1000;
 const locked=['LOCKED','PROVEN LOCKED'].includes(sg.state);
 const out={ticker:tk,ts:r.ts,tau,state:sg.state,side:sg.side,pFlip:sg.pFlip,action:sg.trade?.action,pr11:sg.pr11,lockedSide:sg.lockedSide};rows.push(out);
 if(old && (old.state!==sg.state || old.side!==sg.side || old.lockedSide!==sg.lockedSide))diffs.push({ticker:tk,ts:r.ts,tau,restoredState:old.state,seqState:sg.state,restoredSide:old.side,seqSide:sg.side,restoredLockedSide:old.lockedSide,seqLockedSide:sg.lockedSide,pFlip:sg.pFlip,action:sg.trade?.action});
 if(!entries[tk]&&tau>0&&tau<=120&&locked&&sg.pFlip<=.002)entries[tk]=out;
 prevTs=r.ts;
}
const result={engine:tag,rows:rows.length,initial,entries,differenceCount:diffs.length,differences:diffs};
fs.writeFileSync(path.join(OUT,tag+'_sequential.json'),JSON.stringify(result,null,2));
fs.writeFileSync(path.join(OUT,tag+'_sequential.ndjson'),rows.map(r=>JSON.stringify(r)).join('\n')+'\n');
console.log(JSON.stringify({engine:tag,rows:rows.length,entries:Object.keys(entries).length,differenceCount:diffs.length,examples:diffs.slice(0,4)}));
process.exit(0);
