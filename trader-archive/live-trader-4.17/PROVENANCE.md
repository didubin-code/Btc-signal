# Archive: BTC live trader v4.17 (the trader being replaced)

Archived from origin/main commit: 4426774b8531741b5b67813b95c17562e9f7f97b

Archived 2026-10-16 before any work on its replacement. **Nothing in the original location was changed, renamed or deleted.** The originals stay where they are on `main`: `live-trader-4.17.js`, `live_trader_radar.js`, `shadow_trader.js`, `shadow_trader_v2.js`. The Render service that runs v4.17 was not touched.

| File | Git blob on main | SHA-256 | Last change on main |
|---|---|---|---|
| live-trader-4.17.js | 821d5c4f666224bcaa0e2e2fa494494bf38e1001 | f06d1069d5034e7124381606b013263b536214173586a6d7bdbb883d958d4240 | e4a95a6, 2026-09-01: "Update and rename live-trader-4.16.js to live-trader-4.17.js" |
| live_trader_radar.js | e6fcc9fa50c56c1c0d8f824b5faff5cfeea85c93 | ec7ca25c8e6e85494d380c16f5234c596d5b54c1b04a8f07f820ff7647d5f957 | b01ccd1, 2026-07-23 |
| shadow_trader.js | 54bbad34930c6d5f40331d7bda4fe963d2867d56 | 5ec6b41118234c084dae03c6da8dc9024c626c49ea014e2577cbf1e3795ab790 | 2115484, 2026-07-21 |
| shadow_trader_v2.js | c3971fbda28279ad76ae46d695a4517d2c0868f0 | ac8e8874a6d3a7c64eee77258ab77bdc3e80316c84e560546da6566075d72246 | 47925aa, 2026-07-22 |

* **Byte identity.** Each archived file equals the blob on `main` and the working copy (`cmp`). `verify_archive.sh` re-checks both.
* **History.** `HISTORY_live-trader.txt` lists all 55 commits of the trader's lineage, from `shadow_trader_v2.js` (Jul 21) through `live_trader.js` and `live-trader-4.1` … `4.17`. Every earlier version is recoverable with `git show <commit>:<file>`.
* **Configuration.** v4.17 is configured entirely by environment variables in its Render service. `ENV_KEYS_v4.17.txt` lists the 95 keys it reads (names only). The values live in the Render dashboard and are not in any repository, so they were not copied; record them from the dashboard before any switch-over.
* **Runtime.** Zero dependencies, `node live-trader-4.17.js`, port `PORT` (default 10000). Endpoints: `/health /selftest /status /report /radar /live /livecheck /halt /log`. It trades only when `LIVE=1` and `KALSHI_KEY_ID` / `KALSHI_PRIVATE_KEY` are set.
