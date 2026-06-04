# strategy.py -- RSI degerine gore al/sat/bekle karari uretir.
#
# Strateji mantigi:
#   RSI < RSI_OVERSOLD  (35) -> "BUY"  -- fiyat dip yapti, alim firsati
#   RSI > RSI_OVERBOUGHT (65) -> "SELL" -- fiyat zirve yapti, satim firsati
#   Aradaysa           -> "HOLD" -- bekle, acele etme

from colorama import init, Fore, Style
import config

init(autoreset=True)

SIGNAL_BUY  = "BUY"
SIGNAL_SELL = "SELL"
SIGNAL_HOLD = "HOLD"


def get_signal(rsi: float, current_price: float,
               oversold: float = None, overbought: float = None,
               symbol: str = None) -> str:
    """
    RSI degerine bakarak sinyal uretir.

    oversold/overbought parametreleri verilirse onlari kullanir,
    verilmezse config'deki degerleri kullanir.
    """
    ov_sold = oversold if oversold is not None else config.RSI_OVERSOLD
    ov_bought = overbought if overbought is not None else config.RSI_OVERBOUGHT
    sym = symbol or config.SYMBOL

    if rsi < ov_sold:
        signal = SIGNAL_BUY
        color  = Fore.GREEN
        reason = f"RSI={rsi:.2f} < {ov_sold} -> AL"

    elif rsi > ov_bought:
        signal = SIGNAL_SELL
        color  = Fore.RED
        reason = f"RSI={rsi:.2f} > {ov_bought} -> SAT"

    else:
        signal = SIGNAL_HOLD
        color  = Fore.YELLOW
        reason = f"RSI={rsi:.2f} -> Notr"

    print(
        color + Style.BRIGHT
        + f"  [{sym}]  Fiyat: {current_price:.2f} USDT"
        + f"  Sinyal: {signal}"
        + Style.RESET_ALL
        + Fore.WHITE + f"  ({reason})"
    )

    return signal
