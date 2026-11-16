
const http=require('http'),fs=require('fs');const {chromium}=require('playwright');
const page_html=fs.readFileSync(process.argv[2],'utf8'),payload=fs.readFileSync(process.argv[3],'utf8');
const srv=http.createServer((q,r)=>{r.setHeader('Access-Control-Allow-Origin','*');r.setHeader('Access-Control-Allow-Headers','Content-Type');if(q.method==='OPTIONS'){r.writeHead(204);return r.end();}if(q.url.startsWith('/radar')){r.writeHead(200,{'Content-Type':'application/json'});return r.end(payload);}r.writeHead(200,{'Content-Type':'text/html'});r.end(page_html);});
srv.listen(0,'127.0.0.1',async()=>{const base='http://127.0.0.1:'+srv.address().port;const b=await chromium.launch();const p=await (await b.newContext({viewport:{width:1180,height:1500}})).newPage();
await p.addInitScript(u=>{localStorage.setItem('pinradar28',JSON.stringify({u,lf:false,c:10}));},base);await p.goto(base+'/');const btn=p.locator('button',{hasText:/^start/i}).first();if(await btn.count())await btn.click();
await p.waitForFunction(()=>{const h=document.getElementById('callHead');return h&&h.textContent.trim()&&h.textContent.trim()!=='NO CALL';},null,{timeout:15000});await p.waitForTimeout(1200);
const t=await p.evaluate(()=>{const g=id=>{const e=document.getElementById(id);return e?e.textContent.trim().replace(/\s+/g,' '):null;};const cl=id=>{const e=document.querySelector('#'+id+' b');return e?e.className:null;};return {v28o:g('v28o'),v28v:g('v28v'),v28vClass:cl('v28v'),v28x:g('v28x'),v28xClass:cl('v28x'),v28dz:g('v28dz')};});
console.log(JSON.stringify(t));await b.close();srv.close();});
