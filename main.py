"""Clock-sniper BTC scalper for make.fun bounty btc-race-24h-20261115-0828.

Trades Coinbase Wrapped BTC (CBBTC) against USDC, long only, $1,000 paper,
one position at a time, full size, on 1-minute bars (agent-fun/bars-replay/v1).

Why this shape, from the frozen 24h dev window (1,440 bars, $67,216 -> $64,524,
-4.0% drift, 1-minute noise sigma ~12 bps, round trip ~40 bps at the window's
own pool depths):
  * Minute-scale mean reversion is dead here: Bollinger and RSI variants all
    lose $36-$153 in backtest, because the noise is far below the round-trip
    cost. The only durable edge is the handful of multi-hour V-recoveries
    after deep drops (e.g. -415 bps then +547 bps within 2 hours).
  * The naive dip buyer fails differently: it enters mid-plunge and then sits
    through a 200-400 bar grind until a trailing stop finally fires at -2.5%.
    The fix is a CLOCK: if the recovery has not arrived within 120 bars of
    entry, exit anyway. The clock is what turns a losing dip strategy into a
    winning one on this window (backtest: dip-and-turn -$57, clock-sniper
    +$31, same entries otherwise).
  * Entry: the close is >= 3.00% below its rolling 240-minute high AND the
    10-minute return has turned positive (the drop is over, not just pausing).
    Buy 100% of cash.
  * Exit, whichever comes first: take profit +2.20% over the entry close, a
    trailing stop 1.50% below the peak close since entry, or the clock: 120
    bars after entry with no take-profit, sell. No new entries in the last
    hour of the window; force-exit any position in the last 10 minutes so the
    window-end flatten never catches us. Loss brake: stop entering once
    realised losses reach $30.

Deterministic, standard library only, no network, no wall clock: every
decision is a pure function of the bars seen so far. Uses the kit's Python
SDK shim (vendor/makefun_bars.py, byte-identical to the kit's).

Backtest on the kit's dev window (offline replay with the same fill model:
4 bps fee, 2 bps slippage, constant-product impact against each fill bar's
open depth): net PnL +$30.67 on 3 round trips (6 filled orders), max
drawdown 1.94%. Neighbouring parameters (dip 260-300 bps, TP 180-250 bps,
clock 120-180 bars) all stay positive (+$11 to +$34), so the result is a
plateau, not a single tuned point.
"""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor")
)
import makefun_bars

SYMBOL = "CBBTC"

# Strategy parameters (bps unless noted).
ROLLING_HIGH_BARS = 240  # rolling-high window (minutes)
DIP_BPS = 300  # entry: close this far below the rolling high
TURN_BARS = 10  # entry confirmation: 10-minute return positive
TAKE_PROFIT_BPS = 220  # exit: this far above the entry close
TRAIL_BPS = 150  # exit: trailing stop below the peak close
CLOCK_BARS = 120  # exit: sell this many bars after entry if no take-profit
MAX_SLIPPAGE_BPS = 100  # cap on every order (1% past the latest close)
NO_ENTRY_AFTER_MIN = 1380  # no new entries in the last 60 minutes
FORCE_EXIT_AFTER_MIN = 1430  # force-exit in the last 10 minutes
REENTRY_COOLDOWN_BARS = 45  # wait 45 bars after an exit before re-entering
LOSS_BRAKE_QUOTE_UNITS = 30_000_000  # stop entering after $30 realised loss
MIN_NOTIONAL_QUOTE_UNITS = 1_000_000  # $1, the harness's minimum buy


def rolling_high(closes, window):
    """The highest close of the last `window` bars, current bar included."""
    return max(closes[-window:])


def dipped_below_high(closes, window, dip_bps):
    """True when the latest close sits at least `dip_bps` below the rolling high."""
    high = rolling_high(closes, window)
    return closes[-1] * 10_000 <= high * (10_000 - dip_bps)


def turned_up(closes, bars):
    """True when the latest close is above the close `bars` minutes ago."""
    return len(closes) > bars and closes[-1] > closes[-1 - bars]


def below_by_bps(price, reference, bps):
    """True when `price` is at least `bps` below `reference` (integer math)."""
    return price * 10_000 <= reference * (10_000 - bps)


def above_by_bps(price, reference, bps):
    """True when `price` is at least `bps` above `reference` (integer math)."""
    return price * 10_000 >= reference * (10_000 + bps)


class Sniper:
    """Per-run state: the closes seen, the open trade, and the realised PnL."""

    def __init__(self):
        self.closes = []
        self.first_t = None
        self.entry_close = None
        self.peak_close = None
        self.entry_seq = -1
        self.pending_entry_close = None
        self.last_exit_seq = -10**9
        self.realised = 0
        self.last_buy_cost = 0

    def note_fill(self, fill, close):
        """Fold one filled order into the trade bookkeeping."""
        if fill["status"] != "filled":
            if fill["side"] == "buy":
                self.pending_entry_close = None
            return
        if fill["side"] == "buy":
            self.last_buy_cost = int(fill["notional_quote_units"])
            if self.pending_entry_close is not None:
                self.entry_close = self.pending_entry_close
                self.peak_close = close
                self.pending_entry_close = None
        else:
            proceeds = int(fill["notional_quote_units"])
            fee = int(fill["fee_quote_units"])
            self.realised += proceeds - fee - self.last_buy_cost
            self.last_buy_cost = 0


SNIPER = Sniper()


def decide_exit(state, close, elapsed_min):
    """The exit to take while holding, or None to keep holding.

    Order matters: the forced exit first, then the trailing stop, then the
    take-profit, then the clock. Each returns the reason it fired.
    """
    if elapsed_min >= FORCE_EXIT_AFTER_MIN:
        return "force"
    if below_by_bps(close, SNIPER.peak_close, TRAIL_BPS):
        return "trail"
    if above_by_bps(close, SNIPER.entry_close, TAKE_PROFIT_BPS):
        return "take-profit"
    if state.seq - SNIPER.entry_seq >= CLOCK_BARS:
        return "clock"
    return None


def decide_entry(state, close, elapsed_min):
    """True when a fresh position may be opened on this bar."""
    if SNIPER.realised <= -LOSS_BRAKE_QUOTE_UNITS:
        return False
    if elapsed_min >= NO_ENTRY_AFTER_MIN:
        return False
    if state.seq - SNIPER.last_exit_seq < REENTRY_COOLDOWN_BARS:
        return False
    if len(SNIPER.closes) <= ROLLING_HIGH_BARS:
        return False
    if not dipped_below_high(SNIPER.closes, ROLLING_HIGH_BARS, DIP_BPS):
        return False
    if not turned_up(SNIPER.closes, TURN_BARS):
        return False
    return state.cash >= MIN_NOTIONAL_QUOTE_UNITS


def on_batch(state, batch):
    """One reply per batch: the orders decided on this bar."""
    bar = state.latest.get(SYMBOL)
    if bar is None:
        return []
    close = int(bar["c"])
    if SNIPER.first_t is None:
        SNIPER.first_t = batch["t"]
    SNIPER.closes.append(close)

    for fill in batch["fills"]:
        if fill["symbol"] == SYMBOL:
            SNIPER.note_fill(fill, close)

    if state.warming_up:
        return []

    elapsed_min = (batch["t"] - SNIPER.first_t) // 60_000
    held = state.positions.get(SYMBOL)
    qty = 0 if held is None else held.qty

    if qty > 0:
        if SNIPER.entry_close is None:
            # A fill arrived without a pending entry (defensive): anchor here.
            SNIPER.entry_close = close
            SNIPER.peak_close = close
            SNIPER.entry_seq = state.seq
        SNIPER.peak_close = max(SNIPER.peak_close, close)
        reason = decide_exit(state, close, elapsed_min)
        if reason is not None:
            SNIPER.last_exit_seq = state.seq
            return [
                {
                    "side": "sell",
                    "symbol": SYMBOL,
                    "qty": qty,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                }
            ]
        return []

    # Flat: clear any stale entry tracking and look for the setup.
    SNIPER.entry_close = None
    SNIPER.peak_close = None
    if not decide_entry(state, close, elapsed_min):
        return []
    SNIPER.pending_entry_close = close
    SNIPER.entry_seq = state.seq
    return [
        {
            "side": "buy",
            "symbol": SYMBOL,
            "notional_quote_units": state.cash,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }
    ]


makefun_bars.run(on_batch)
