# strategy.py -- RSI + MACD + Bollinger birlesik strateji
#
# TEK INDIKATOR vs COK INDIKATOR:
#   Tek RSI:  Cok fazla yanlis sinyal (fake signal)
#   3 birden: Sinyaller birbirini dogrularsa → guclu sinyal
#
# SINYAL GUCU:
#   STRONG_BUY:  3/3 indikator AL diyor  → buyuk pozisyon
#   BUY:         2/3 indikator AL diyor  → normal pozisyon
#   STRONG_SELL: 3/3 indikator SAT diyor → hemen sat
#   SELL:        2/3 indikator SAT diyor → normal sat
#   HOLD:        sinyaller uyusmuyor     → bekle

from colorama import init, Fore, Style
import config

init(autoreset=True)

SIGNAL_BUY        = "BUY"
SIGNAL_SELL       = "SELL"
SIGNAL_STRONG_BUY = "STRONG_BUY"
SIGNAL_STRONG_SELL= "STRONG_SELL"
SIGNAL_HOLD       = "HOLD"


def get_signal(rsi: float, current_price: float,
               oversold: float = None, overbought: float = None,
               symbol: str = None,
               macd: dict = None, bb: dict = None,
               trend: dict = None, volume: dict = None) -> str:
    """
    Birlesik sinyal uret.

    macd/bb verilmezse sadece RSI kullanir (geriye uyumlu).
    trend (EMA200) ve volume verilirse AL sinyali filtrelenir:
      - Fiyat EMA200 altindaysa ALMA (dusen bicagi tutma)
      - Hacim ortalamanin altindaysa ALMA (likit degil)
    """
    ov_sold = oversold if oversold is not None else config.RSI_OVERSOLD
    ov_bought = overbought if overbought is not None else config.RSI_OVERBOUGHT
    sym = symbol or config.SYMBOL

    # Eger MACD ve BB verilmemisse → sadece RSI (eski davranis)
    if macd is None or bb is None:
        if rsi < ov_sold:
            signal = SIGNAL_BUY
        elif rsi > ov_bought:
            signal = SIGNAL_SELL
        else:
            signal = SIGNAL_HOLD

        _print_signal(sym, current_price, rsi, signal, [f"RSI={rsi:.1f}"])
        return signal

    # ─── 3 INDIKATOR BIRLESIK ────────────────────────────────────────
    buy_count = 0
    sell_count = 0
    reasons = []

    # 1. RSI
    if rsi < ov_sold:
        buy_count += 1
        reasons.append(f"RSI={rsi:.1f}<{ov_sold}")
    elif rsi > ov_bought:
        sell_count += 1
        reasons.append(f"RSI={rsi:.1f}>{ov_bought}")
    else:
        reasons.append(f"RSI={rsi:.1f} notr")

    # 2. MACD
    if macd.get("bullish"):
        buy_count += 1
        reasons.append("MACD+")
    else:
        sell_count += 1
        reasons.append("MACD-")

    # 3. Bollinger
    if bb.get("below_lower"):
        buy_count += 1
        reasons.append("BB_alt")
    elif bb.get("above_upper"):
        sell_count += 1
        reasons.append("BB_ust")
    else:
        reasons.append("BB_notr")

    # Karar
    if buy_count >= 3:
        signal = SIGNAL_STRONG_BUY
    elif buy_count >= 2:
        signal = SIGNAL_BUY
    elif sell_count >= 3:
        signal = SIGNAL_STRONG_SELL
    elif sell_count >= 2:
        signal = SIGNAL_SELL
    else:
        signal = SIGNAL_HOLD

    # ─── AKILLI FILTRELER (sadece AL sinyallerini filtreler) ─────────
    # Satis sinyallerine dokunmuyoruz — elinde pozisyon varsa cikabilmeli.
    if signal in (SIGNAL_BUY, SIGNAL_STRONG_BUY):
        # MACD ZORUNLULUGU: Learner verisi: MACD+=%75 win, MACD-=%22 win
        # MACD onaylamadan asla alma — en guclu tek filtre
        if config.REQUIRE_MACD_FOR_BUY and not macd.get("bullish"):
            reasons.append("X MACD onaysiz (%22 win skip)")
            signal = SIGNAL_HOLD

        # TREND FILTRESI: Fiyat EMA200 altindaysa = dusus trendi = ALMA
        if signal in (SIGNAL_BUY, SIGNAL_STRONG_BUY) and config.USE_TREND_FILTER and trend is not None and trend.get("available"):
            if not trend.get("above_ema"):
                reasons.append("X EMA200 alti (dusus)")
                signal = SIGNAL_HOLD

        # HACIM FILTRESI: Hacim ortalamanin altindaysa = zayif hareket = ALMA
        if signal != SIGNAL_HOLD and config.USE_VOLUME_FILTER and volume is not None and volume.get("available"):
            if not volume.get("volume_ok"):
                reasons.append("X dusuk hacim")
                signal = SIGNAL_HOLD

    _print_signal(sym, current_price, rsi, signal, reasons)
    return signal


def _print_signal(sym, price, rsi, signal, reasons):
    """Terminal ciktisi."""
    colors = {
        SIGNAL_STRONG_BUY: Fore.GREEN + Style.BRIGHT,
        SIGNAL_BUY:        Fore.GREEN,
        SIGNAL_STRONG_SELL:Fore.RED + Style.BRIGHT,
        SIGNAL_SELL:       Fore.RED,
        SIGNAL_HOLD:       Fore.YELLOW,
    }
    color = colors.get(signal, Fore.WHITE)
    reason_str = " | ".join(reasons)
    print(
        color
        + f"  [{sym}] ${price:.2f} | {signal}"
        + Style.RESET_ALL
        + Fore.WHITE + f"  ({reason_str})"
    )
