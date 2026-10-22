# Switching the existing Render "Live Trader" service from v4.17 to Trader 5.0

This runbook switches your existing Render service from v4.17 to Trader 5.0 and covers rollback to v4.17 on the same service.
* It uses one service and adds no second service.
* The only possible extra cost is a persistent disk, if the service does not have one yet (step 2). Render shows its price before you confirm.

**Release:** Btc-signal branch `claude/btc-pin-radar-research-xpe585`. The commit to deploy is the one named in the final report; Render shows the commit it built.

**Rollback reference:** v4.17 is `live-trader-4.17.js` on `main` at commit `4426774b8531741b5b67813b95c17562e9f7f97b`.
* A checksummed copy is in `trader-archive/live-trader-4.17/`; run `bash verify_archive.sh` there and expect `ARCHIVE_OK`.
* A `live-trader-4.17-final` tag could not be pushed from the build session because the git proxy refuses tag pushes. If you want one, create it in GitHub on that commit.

## Settings: v4.17 now vs. Trader 5.0

| Setting | v4.17 (record yours first) | Trader 5.0 |
|---|---|---|
| Branch | `main` | `claude/btc-pin-radar-research-xpe585` |
| Root Directory | (repository root) | `pinradar-trader` |
| Build Command | (as recorded; v4.17 has no dependencies) | `npm install` |
| Start Command | `node live-trader-4.17.js` | `node trader.js` |
| Health Check Path | (as recorded) | `/health` |
| Auto-Deploy | (as recorded) | **Off** |
| Instance | must not sleep | same instance |
| Disk | ? | **required**, e.g. mounted at `/data` |

**Environment.** These names were compared with the 95 names v4.17 reads (`trader-archive/live-trader-4.17/ENV_KEYS_v4.17.txt`). Only six are shared, and they mean the same in all three programs:

| Name | Meaning |
|---|---|
| `KALSHI_KEY_ID`, `KALSHI_PRIVATE_KEY` | Kalshi API key; same format. |
| `KALSHI_BASE` | Same URL format, including `/trade-api/v2`. |
| `EXCHANGE_INDEX` | -1 auto-routes each order by ticker. |
| `LIVE` | `LIVE=1` alone does **not** arm 5.0. |
| `PORT` | Set by Render. |

Every other v4.17 variable is ignored by 5.0. Keep them, because they make rollback a settings-only change.

## 1. Stop v4.17 (before changing anything)

1. Open the service in the Render dashboard and record the current settings in the left column of the table above. A screenshot of Settings and the names under Environment is enough.
2. Halt v4.17: open `<service-url>/halt?on=1`. v4.17's own `/status` should then show it halted.
3. In Kalshi → Portfolio, check that no KXBTC15M position is open. If one is, wait for it to settle; a window lasts at most 15 minutes.
4. Wait at least **20 minutes** after v4.17's last order before arming 5.0 (step 6). The guard in 5.0 halts trading if it sees KXBTC15M orders from another trader in the last 20 minutes. The dry-run period in step 5 covers this wait anyway.

## 2. Persistent disk

Open the service's **Disks** tab.

* **A disk exists:** note its mount path, e.g. `/var/data`, and use it below.
* **No disk:** adding one costs extra, and Render shows the price before you confirm. **Approve that cost before adding it.**
  * Without a disk, the ledger, the halts and the order reconciliation would not survive a redeploy or restart.
  * Trader 5.0 refuses to arm live trading without an explicit `TRADER_LEDGER_FILE`. Never point that variable at a path that is not on the disk.

A service with a disk deploys with a short downtime instead of running old and new instances side by side. That is what we want: two traders never run at once.

## 3. Change the service to Trader 5.0

Under **Settings**, set:
* Branch, Root Directory, Build Command, Start Command and Health Check Path as in the right column of the table;
* Auto-Deploy **Off**.

Under **Environment**:
* **Add** these:

  | Variable | Value |
  |---|---|
  | `TRADER_LEDGER_FILE` | `<mount>/trader_ledger.jsonl` |
  | `PINRADAR_STATE_FILE` | `<mount>/pinradar_state.json` |
  | `TRADER_ADMIN_TOKEN` | A long random value. Resume and `/livecheck` need it. |
  | `TRADER_VIEW_TOKEN` | A different long random value. The data pages need it. |
* **Set** `LIVE=0` for now, or remove it.
* **Do not** set `TRADER_LIVE_ARM` yet.
* Keep everything else as it is.

Then run **Manual Deploy → Deploy latest commit**.

## 4. Verify the dry-run deployment

`T` is your view token; `A` is your admin token.

| Check | Expected |
|---|---|
| `<url>/health` | `mode: "DRY-RUN"`, `ticks` increasing, `tickErrors: 0`, `ledgerErr: null`, `halted` empty |
| `<url>/selftest?token=T` | `ok: true`, 10/10 |
| `<url>/config?token=T` | engine `sha256` = `expected` (55d0555c…), `lockMaxFlip: 0.002`, `maxTradeUsd: 5`, `credentials` both set |
| `curl -H "X-Admin-Token: A" <url>/livecheck` | `ready: true`, your Kalshi balance, KXBTC15M positions (expected: none). This proves the key signs. |
| `<url>/ledger/verify?token=T` | `ok: true` |
| `<url>/engine/health?token=T` | the engine's own health: venues fresh, Kalshi market found |

The engine is warm about 15 minutes after a start. Its basis model needs 12 settled windows, about 3 hours, the first time. After that it is restored from `PINRADAR_STATE_FILE` on every restart.

## 5. Watch the dry run

Run it in dry run for as long as you are comfortable; at least several hours after warm-up is recommended. Watch `<url>/funnel?hours=24&token=T`:

| Field | Meaning |
|---|---|
| `windowsEvaluated` | Every 15-minute contract seen. |
| `locked` | The engine showed LOCKED (modelled flip risk ≤ 0.2 %) in that window. |
| `executable` | Some LOCKED second passed the data, timing and liquidity checks. |
| `positiveEv` | It also passed the expected-value checks. |
| `attempted`, `filled` | Orders sent, and orders confirmed filled. |
| `missedBy`, `topMissedReasons` | Why each LOCKED window was not traded, by the first gate that stopped it: data, timing, liquidity, ev, risk or unfilled. |
| `directional` | The settled result of **every** LOCKED window, traded or not. This is the prediction record. |
| `trading` | Paper and live P&L after fees, kept separately. |

Paper fills assume the shown offers were still there, so they are optimistic.

## 6. Arm real-money trading

Arm only once steps 4 and 5 are clean. Set these on the same service:
* `LIVE=1`
* `TRADER_LIVE_ARM=I-ACCEPT-REAL-MONEY-RISK`

Saving the environment restarts the service. Then check `<url>/health`:
* It must show `mode: "LIVE"`.
* If it still says DRY-RUN, `modeNote` names what is missing.
* `halted` must be empty. A guard halt here means another trader's orders, or an untracked position, are on the account. Resolve that first.

Live limits, all configurable without code changes:

| Limit | Setting |
|---|---|
| ≤ $5 per trade including the fee | `MAX_TRADE_USD`, capped by `ABSOLUTE_MAX_TRADE_USD=5` |
| ≤ $5 open | `MAX_OPEN_USD` |
| Halt at −$10 in a day | `DAILY_LOSS_LIMIT_USD` |
| Halt after the first loss | `HALT_AFTER_LOSSES=1` |
| One entry per window, up to 3 IOC attempts while the signal stays valid | `MAX_ATTEMPTS_PER_WINDOW`, `RETRY_SPACING_MS` |
| Halt after the **first live fill** for your review | `FIRST_FILL_HALT=1` |

## 7. The first real order

The trader stops after its first fill. Then:
1. Check the order in Kalshi → Portfolio and in `<url>/trades?token=T`. The contract, side, count and price must match, and the `FILL` record must show the cost.
2. Wait for the `SETTLED` record, which comes a few seconds after the window closes.
3. Resume with `curl -X POST -H "X-Admin-Token: A" <url>/halt?on=0`.

**Any other halt** (rejection, unknown outcome, loss, daily limit, ledger, guard): read `/status?token=T`, compare with `/livecheck`, fix the cause, then resume the same way. For an unknown outcome, wait for the `RECONCILED` record first.

## Emergency stop

Use any one of these:
* open `<url>/halt?on=1` (no token needed);
* set `TRADER_HALT=1` in Environment;
* suspend the service in Render.

Open positions settle by themselves at the close; 5.0 never sells early.

## Rollback to v4.17 on the same service

1. Halt 5.0 with `<url>/halt?on=1`.
2. Check that `<url>/status?token=T` shows no open positions. If it does, wait for them to settle (at most 15 minutes).
3. Under **Settings**, restore the v4.17 values you recorded: branch `main`, Root Directory empty, the recorded Build Command, Start `node live-trader-4.17.js`, and the recorded Health Check Path.
4. Under **Environment**:
   * remove `TRADER_LIVE_ARM`;
   * set `LIVE` back to what v4.17 had;
   * the 5.0-only variables can stay, because v4.17 ignores them.
5. Run **Manual Deploy** of `main`, which is commit `4426774`, then check v4.17's `/health` and `/selftest`. The disk can stay attached.

If `main` ever changes, deploy commit `4426774` explicitly. Alternatively, restore the file from the archive (`trader-archive/live-trader-4.17/files/`) after checking it with `verify_archive.sh`.
