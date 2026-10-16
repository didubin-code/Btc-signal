# BTC Pin Radar 2.8.1 page (research branch; not deployed)

`btc_pin_radar_281.html` is the 2.8 page, with the same layout, plus the following.

* **One action line at the top of the call card:**
  * **TRADE NOW — BUY YES/NO**, **SIT OUT** or **TOO LATE**;
  * then the reversal risk (%) and one reason.
  * Examples:
    * "LOCKED UP, but no edge at 99.8¢ (worth it only at ≤ 97.1¢)"; the price includes the fee at that price and the stress test;
    * "LOCKED UP with 9 s left: an order needs 15 s".
  * It also shows the last moment to place an order.
  * A GET READY note appears only when LOCKED is projected within about 20 s and could actually be shown.
  * If the server goes stale or the window closes, the line drops to STALE — DO NOT TRADE or WINDOW CLOSED.
  * TRADE NOW turns into TOO LATE at the last order moment, and into STALE when the reading may be more than 1.5 s old (counted from when the page requested it, so a slow connection never shows an old TRADE NOW as current). The trade box, card and alert sound follow the action line.
* **A restart / warm-up banner.**
* **An "order time" setting** (default 12 s). TRADE NOW needs at least 3 s plus that time, so 15 s by default.

The outcome headline (PREDICTED LOCKED — UP / DOWN) is unchanged and separate from the trade line.

It needs the 2.8.1 server: `btc-ai-backend`, branch `claude/btc-pin-radar-research-xpe585`, file `pinradar-research/2.8.1/dist/pinradar_server.js`. Against a 2.8 server the action line says NO ACTION DATA.

The investigation and install steps are on that branch:
* `pinradar-research/research28/late_lock/REPORT_LATE_LOCKED.md`;
* `pinradar-research/2.8.1/README_2.8.1.md`.
