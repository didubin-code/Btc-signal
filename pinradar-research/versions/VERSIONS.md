# BTC Pin Radar — preserved engine versions (provenance)

Verified 2026-10-14. Production is untouched: `main` of `btc-ai-backend` (commit `c9e0df6`) and
`main` of `Btc-signal` (commit `f3eb239`) still serve 2.3. Everything here lives only on the research
branch `claude/btc-pin-radar-research-xpe585`.

| Version | File | SHA-256 | Git blob | Source / provenance |
|---|---|---|---|---|
| 2.3 (production) | `2.3/pinradar_server.js` | `92363239c94efd6ce8181967e0ecbaf9489bdb85eb0e1cf5489c66fe4e8b3bf8` | `da0e07e` | `btc-ai-backend@c9e0df6` (= `39e8514`), live `main` HEAD. Byte-identical to `rollback/` in the 2.7 package. |
| 2.3 page (production) | `Btc-signal/pinradar-research/versions/2.3/btc_pin_radar.html` | `70a6aabf9d609ae9c0aca5e93b4496802d69b0fbbf3310b81e7cff3dc089bb21` | `92dfb17` | `Btc-signal@f3eb239`, live `main` HEAD. |
| 2.4 (abandoned) | `2.4/pinradar_server.js` | `6fbb2cbc4e9937350adc383fe4e782af4569c97de632ad572bcc535073a961e8` | — | `btc-ai-backend@2d59c75`, uploaded Oct 13 01:25 ET, reverted to 2.3 at 12:40 ET. |
| 2.4 page (abandoned) | `Btc-signal/pinradar-research/versions/2.4/btc_pin_radar.html` | `43657e550cce54171592d97be737f84d9f3439d02679bd422937cb38b8edbb6a` | — | `Btc-signal@cf64af9`, reverted at `f3eb239`. |
| 2.6 (validated baseline, never deployed) | `2.6/pinradar_server.js` | `141c0613cf3bda8ae1e0b2ca4011a2b8ede2b1c0b071d50f0cbee3e1a8bf3efd` | `6924f52` | `pinradar-2.7.zip:test/ref/pinradar_server_26.js`; matches the CP9 hash in `pkg27/research/CHECKPOINTS.md`. The 2.6 *page* was not in the package; the 2.7 page was built from it. |
| 2.7 (never deployed) | `2.7/pinradar_server.js` | `bd7cacbb7144edbe05b382486e33a7eb3ad1a553b0f315c99dc0cddd1386c598` | `fe375c9` | `pinradar-2.7.zip:upload/btc-ai-backend/pinradar_server.js`; `SHA256SUMS.txt` verifies. |
| 2.7 page | `Btc-signal/pinradar-research/versions/2.7/btc_pin_radar_27.html` | `804638ddafb40f8a870e4a3651fbd842193ca6a83dd9bebb4b283b75348d893a` | `d8f6dcf` | `pinradar-2.7.zip:upload/Btc-signal/btc_pin_radar_27.html`. |

The full 2.7 package (research scripts, result tables, tests, BRTI history tool, prior session's
checkpoint log) is preserved unmodified under `../pkg27/` (`SHA256SUMS_2.7.txt` covers the shipped files).

## What was NOT recoverable

* The raw research data behind the 2.6/2.7 backtests (Coinbase/Kraken trade tapes Jul 22 – Oct 13 2026,
  Kalshi KXBTC15M market records and final-200 s trade tapes, `sec_all.npz`, `windows.npz`,
  `settle_eval.npz`). They lived in the prior session's container (`/home/claude/pr25`) and were not
  in the package or in either GitHub repo. Only aggregate result tables and two small real samples
  (`pkg27/test/data/replay_sample.ndjson`: 42 holdout contracts; `consecutive_sample.ndjson`: 16 contracts)
  survive.
* Scripts the analysis imports but the package omits (`model.py`, `predict.py`, `kexec.py`,
  `actionable.py`, `build_index.py`, `build_windows.py`, …).
* `Archive_2.zip` (the user's real-money LIVE_FILL archive used in CP10).

Consequence: the headline backtest numbers (2.6 holdout 3/1,879, dev 13/3,484 first-LOCKED losses)
can be checked for internal consistency but cannot be re-computed from data in this environment.
