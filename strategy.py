# strategy.py — RSI değerine göre al/sat/bekle kararı üretir.
#
# Strateji mantığı:
#   RSI < RSI_OVERSOLD  (30) → "BUY"  — fiyat dip yaptı, alım fırsatı
#   RSI > RSI_OVERBOUGHT (70) → "SELL" — fiyat zirve yaptı, satım fırsatı
#   Aradaysa           → "HOLD" — bekle, acele etme

from colorama import init, Fore, Style
import config

init(autoreset=True)

# Sinyal sabitleri — string yerine sabit kullanmak yazım hatalarını önler
SIGNAL_BUY  = "BUY"
SIGNAL_SELL = "SELL"
SIGNAL_HOLD = "HOLD"


def get_signal(rsi: float, current_price: float) -> str:
    """
    RSI değerine bakarak sinyal üretir ve terminale renkli çıktı basar.
    Döndürdüğü değer: "BUY", "SELL" veya "HOLD"
    """
    if rsi < config.RSI_OVERSOLD:
        signal = SIGNAL_BUY
        color  = Fore.GREEN
        reason = f"RSI={rsi:.2f} < {config.RSI_OVERSOLD} → Aşırı satılmış"

    elif rsi > config.RSI_OVERBOUGHT:
        signal = SIGNAL_SELL
        color  = Fore.RED
        reason = f"RSI={rsi:.2f} > {config.RSI_OVERBOUGHT} → Aşırı alınmış"

    else:
        signal = SIGNAL_HOLD
        color  = Fore.YELLOW
        reason = f"RSI={rsi:.2f} → Nötr bölge"

    # Terminale renkli sinyal çıktısı
    print(
        color + Style.BRIGHT
        + f"  [{config.SYMBOL}]  Fiyat: {current_price:.2f} USDT"
        + f"  Sinyal: {signal}"
        + Style.RESET_ALL
        + Fore.WHITE + f"  ({reason})"
    )

    return signal


if __name__ == "__main__":
    # Hızlı test: farklı RSI değerleri için sinyalleri göster
    for test_rsi in [25.0, 50.0, 75.0]:
        get_signal(test_rsi, current_price=67000.0)
