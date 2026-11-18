/* run the server's own self-test in replay mode (no listener, no network) and print only the PR11 lines + totals */
const path = process.argv[2]; process.env.PINRADAR_REPLAY = '1';
const m = require(path); const r = m.runSelfTest();
const pr10 = r.checks.filter(c => /PR11/.test(c.name));
for (const c of pr10) console.log((c.pass ? 'PASS' : 'FAIL') + '  ' + c.name + '  => ' + (typeof c.got === 'string' ? c.got : JSON.stringify(c.got)));
const fails = r.checks.filter(c => !c.pass);
console.log('TOTAL', r.checks.length, 'checks; failed', fails.length, fails.map(c => c.name)); console.log('ok flag', r.ok, 'mode', m.PR11_MODE, 'table', m.PR11_RSTAR.length);
process.exit(fails.length ? 1 : 0);
