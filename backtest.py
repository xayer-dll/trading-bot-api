# backtest.py — RSI stratejisini geçmiş verilerle test eder.
#
# "Bu strateji geçmişte çalışsaydı ne olurdu?" sorusunu cevaplar.
# Gerçek Binance API'sinden tarihsel veri çeker (para gerektirmez).
#
# Hesaplanan metrikler:
#   Win Rate     → Kârlı işlem / toplam işlem
#   Total P&L    → Tüm işlemlerin toplam kârı/zararı
#   Max Drawdown → En kötü dönemdeki maksimum düşüş %'si
#   Sharpe Ratio → Risk/Ödül oranı (>1 iyi, >2 çok iyi)

import pandas as pd
import numpy as np
from binance.client import Client
from ta.momentum import RSIIndicator
import config


def _fetch_historical(symbol: str, interval: str, days: int) -> pd.DataFrame:
    """
    Gerçek Binance'tan (testnet değil) tarihsel OHLCV çeker.
    Market verisi herkese açık, API key gerekmez.
    """
    client = Client("", "")   # Boş key — sadece public endpoint kullanıyoruz
    start  = f"{days} days ago UTC"
    klines = client.get_historical_klines(symbol, interval, start)

    df = pd.DataFrame(klines, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_buy_base", "taker_buy_quote", "ignore"
    ])
    df["close"]     = pd.to_numeric(df["close"])
    df["high"]      = pd.to_numeric(df["high"])
    df["low"]       = pd.to_numeric(df["low"])
    df["volume"]    = pd.to_numeric(df["volume"])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df.set_index("open_time", inplace=True)
    return df


def run_backtest(
    symbol:         str   = "BTCUSDT",
    interval:       str   = "1h",
    days:           int   = 30,
    rsi_period:     int   = 14,
    rsi_oversold:   float = 30.0,
    rsi_overbought: float = 70.0,
    trade_amount:   float = 100.0,   # USDT cinsinden
    stop_loss_pct:  float = 0.02,
    take_profit_pct:float = 0.03,
) -> dict:
    """Backtest çalıştırır ve sonuç dict'i döndürür."""

    # 1. Veri çek + RSI hesapla
    df = _fetch_historical(symbol, interval, days)
    rsi_ind = RSIIndicator(close=df["close"], window=rsi_period)
    df["rsi"] = rsi_ind.rsi()
    df.dropna(inplace=True)

    # 2. Simülasyon
    balance   = trade_amount * 10   # Başlangıç bakiyesi (trade_amount × 10)
    position  = None                 # {"entry": price, "qty": float, "time": ts}
    trades    = []
    equity    = []

    for ts, row in df.iterrows():
        price = float(row["close"])
        rsi   = float(row["rsi"])

        # Bakiye snapshot (downsample: her N mumda bir)
        equity.append({"t": ts.strftime("%m/%d %H:%M"), "balance": round(balance, 2)})

        if position is None:
            # BUY sinyali
            if rsi < rsi_oversold:
                qty = trade_amount / price
                position = {"entry": price, "qty": qty, "time": ts}
        else:
            entry   = position["entry"]
            qty     = position["qty"]
            chg_pct = (price - entry) / entry

            reason = None
            if chg_pct <= -stop_loss_pct:   reason = "STOP-LOSS"
            elif chg_pct >= take_profit_pct: reason = "TAKE-PROFIT"
            elif rsi > rsi_overbought:        reason = "RSI-SELL"

            if reason:
                pnl      = (price - entry) * qty
                balance += pnl
                trades.append({
                    "time":   ts.strftime("%Y-%m-%d %H:%M"),
                    "action": "SELL",
                    "price":  round(price, 2),
                    "entry":  round(entry, 2),
                    "rsi":    round(rsi, 2),
                    "pnl":    round(pnl, 4),
                    "reason": reason,
                })
                position = None

    # 3. Açık pozisyon varsa zorla kapat
    if position:
        price = float(df["close"].iloc[-1])
        pnl   = (price - position["entry"]) * position["qty"]
        balance += pnl
        trades.append({
            "time": "KAPANIŞ", "action": "SELL", "price": round(price, 2),
            "entry": round(position["entry"], 2), "rsi": 50,
            "pnl": round(pnl, 4), "reason": "END"
        })

    # 4. İstatistikler
    sell_trades  = trades
    win_trades   = [t for t in sell_trades if t["pnl"] > 0]
    total_pnl    = sum(t["pnl"] for t in sell_trades)
    start_bal    = trade_amount * 10

    # Max Drawdown
    eq_vals = [e["balance"] for e in equity]
    peak, max_dd = eq_vals[0] if eq_vals else start_bal, 0.0
    for v in eq_vals:
        if v > peak: peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd: max_dd = dd

    # Sharpe Ratio (basit versiyon: günlük getiri ortalaması / std)
    if len(eq_vals) > 1:
        returns = pd.Series(eq_vals).pct_change().dropna()
        sharpe  = (returns.mean() / returns.std() * np.sqrt(252)).round(2) if returns.std() > 0 else 0.0
    else:
        sharpe = 0.0

    # Equity'i 100 noktaya indir (grafik için)
    step   = max(1, len(equity) // 100)
    equity_sampled = equity[::step]

    return {
        "symbol":          symbol,
        "interval":        interval,
        "days":            days,
        "total_candles":   len(df),
        "total_trades":    len(sell_trades),
        "win_trades":      len(win_trades),
        "win_rate":        round(len(win_trades) / len(sell_trades) * 100, 1) if sell_trades else 0,
        "total_pnl":       round(total_pnl, 4),
        "total_pnl_pct":   round(total_pnl / start_bal * 100, 2),
        "max_drawdown":    round(max_dd, 2),
        "sharpe_ratio":    float(sharpe),
        "best_trade":      round(max((t["pnl"] for t in sell_trades), default=0), 4),
        "worst_trade":     round(min((t["pnl"] for t in sell_trades), default=0), 4),
        "final_balance":   round(balance, 2),
        "start_balance":   start_bal,
        "trades":          sell_trades[-30:],   # Son 30 işlem
        "equity":          equity_sampled,
    }


if __name__ == "__main__":
    print("[Backtest] BTCUSDT 30 günlük 1h...")
    result = run_backtest()
    print(f"  Toplam işlem : {result['total_trades']}")
    print(f"  Win Rate     : %{result['win_rate']}")
    print(f"  Toplam P&L   : {result['total_pnl']} USDT (%{result['total_pnl_pct']})")
    print(f"  Max Drawdown : %{result['max_drawdown']}")
    print(f"  Sharpe Ratio : {result['sharpe_ratio']}")
