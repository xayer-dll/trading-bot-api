# indicators.py — Teknik indikatörleri hesaplar.
#
# RSI (Relative Strength Index) NEDİR?
#   0–100 arasında değer alan bir momentum göstergesidir.
#   Son N mumun yükseliş/düşüş hızını ölçer.
#
#   • RSI < 30  → Aşırı SATILMIŞ (oversold): fiyat çok düştü, toparlanabilir → BUY fırsatı
#   • RSI > 70  → Aşırı ALINMIŞ  (overbought): fiyat çok yükseldi, düşebilir → SELL fırsatı
#   • 30–70 arası → Nötr bölge → HOLD (bekle)
#
#   Formül özeti: RSI = 100 - 100 / (1 + (Ort. Yükseliş / Ort. Düşüş))

import pandas as pd
import ta  # "Technical Analysis" kütüphanesi — 130+ indikatörü hazır sunar
import config


def add_rsi(df: pd.DataFrame, period: int = config.RSI_PERIOD) -> pd.DataFrame:
    """
    DataFrame'e 'rsi' sütunu ekler.
    ta.momentum.RSIIndicator → Wilder smoothing yöntemiyle RSI hesaplar.
    """
    rsi_indicator = ta.momentum.RSIIndicator(close=df["close"], window=period)
    df["rsi"] = rsi_indicator.rsi()
    return df


def get_latest_rsi(df: pd.DataFrame) -> float:
    """En son tamamlanan mumun RSI değerini döndürür."""
    # -2: son mum henüz kapanmamış olabilir; bir öncekini al
    return float(df["rsi"].iloc[-2])


if __name__ == "__main__":
    from connection import get_client
    from data import get_ohlcv

    client = get_client()
    df = get_ohlcv(client)
    df = add_rsi(df)

    print(df[["close", "rsi"]].tail(5))
    print(f"\nGüncel RSI: {get_latest_rsi(df):.2f}")
