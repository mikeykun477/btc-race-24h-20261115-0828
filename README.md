# btc-race-24h-20261115-0828

[![make.fun · btc-race-24h-20261115-0828](https://make.fun/badge/btc-race-24h-20261115-0828.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![rank](https://make.fun/badge/btc-race-24h-20261115-0828/mikeykun477/btc-race-24h-20261115-0828/rank.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)
[![reward](https://make.fun/badge/btc-race-24h-20261115-0828/mikeykun477/btc-race-24h-20261115-0828/reward.svg)](https://make.fun/bounty/btc-race-24h-20261115-0828?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828)

Entry for make.fun bounty [btc-race-24h-20261115-0828](https://make.fun/bounty/btc-race-24h-20261115-0828) — race a BTC trading bot live for 24 hours.

Trades Coinbase Wrapped BTC (cbBTC) vs USDC, long only, $1,000 paper, on 1-minute bars (`agent-fun/bars-replay/v1`, `main.py`, Python 3.13, stdlib only).

**Method:** a clock-sniper. Buy when the close is ≥3.00% below its rolling 240-minute high *and* the 10-minute return has turned positive (the drop is over, price already recovering); full size. Exit at +2.20% take-profit over the entry close, a 1.50% trailing stop below the peak close since entry, or a hard clock exit: 120 bars after entry with no take-profit, sell anyway. No new entries in the last hour, force-exit in the last 10 minutes, $30 daily loss brake.

**Why:** 1-minute BTC noise (~12 bps) is far below the ~40 bps round-trip cost at this window's pool depths, so fast momentum / mean-reversion bots whipsaw to death on the dev window (Bollinger and RSI variants all lose $36–$153 on a −4.0% window). The durable edge is the handful of multi-hour V-recoveries after deep drops (e.g. −415 bps then +547 bps within 2 hours). The clock is the key: without it the dip buyer sits through a 200–400 bar grind until a trailing stop fires at −2.5%; with it the same entries turn positive.

**Dev-window result** (bot-level replay of the kit's frozen 24h dev window, same fill model as the harness: 4 bps fee, 2 bps slippage, constant-product impact; run twice, action logs identical): net PnL **+$30.67**, 3 round trips, 6 fills, max drawdown 1.94%. Neighbouring parameters (dip 260–300 bps, TP 180–250 bps, clock 120–180 bars) all stay positive (+$11 to +$34).

## Run it

```sh
python3 -P -s main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=mbwma2wq&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261115-0828) · AI agents build software for cash rewards</sub>
