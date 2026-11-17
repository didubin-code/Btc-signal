/* run a server file's own self-test in replay mode (no listener): node run_selftest_generic.js <server.js> */
process.env.PINRADAR_REPLAY = '1'; process.env.ENABLE_WS = '0';
const m = require(require('path').resolve(process.argv[2])); const r = m.runSelfTest(); const fails = r.checks.filter(c => !c.pass);
console.log('TOTAL', r.checks.length, 'checks; failed', fails.length, fails.map(c => c.name)); console.log('ok flag', r.ok); process.exit(fails.length ? 1 : 0);
