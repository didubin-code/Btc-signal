# BTC Pin Radar 2.8.1 page (research branch; not deployed)

`btc_pin_radar_281.html` is the 2.8 page plus:

* an action line at the top of the call card:
  * TRADE NOW — BUY YES/NO, with the last moment to place the order;
  * PREDICTED LOCKED — NOT TRADABLE NOW, with the reason;
  * TOO LATE TO TRADE;
  * SIT OUT, with a GET READY note when LOCKED is projected within about 20 s;
  * WINDOW CLOSED — FINAL / SETTLEMENT;
* a restart / warm-up banner;
* an "order time" setting (default 10 s). TRADE NOW needs at least 3 s plus that time.

It needs the 2.8.1 server (`btc-ai-backend`, branch `claude/btc-pin-radar-research-xpe585`, `pinradar-research/2.8.1/dist/pinradar_server.js`). Against a 2.8 server the action line says NO ACTION DATA.

The investigation and install steps are in that branch: `pinradar-research/research28/late_lock/REPORT_LATE_LOCKED.md` and `pinradar-research/2.8.1/README_2.8.1.md`.
